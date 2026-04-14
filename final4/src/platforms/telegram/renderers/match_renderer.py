# src/platforms/telegram/renderers/match_renderer.py
"""Рендеринг сообщений матча"""

from typing import List, Optional

from src.core.models.match import Match, MatchStatus, MatchPhase
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetOutcome
from src.core.models.whistle_card import WhistleCard, CardType


class MatchRenderer:
    """Рендерер сообщений для матча"""
    
    @staticmethod
    def render_match_status(match: Match, viewer_id=None) -> str:
        """Отрендерить статус матча"""
        status_emoji = {
            MatchStatus.WAITING_FOR_OPPONENT: "⏳",
            MatchStatus.SETTING_LINEUP: "📋",
            MatchStatus.IN_PROGRESS: "⚽",
            MatchStatus.EXTRA_TIME: "⏱",
            MatchStatus.PENALTIES: "🎯",
            MatchStatus.FINISHED: "🏁",
            MatchStatus.CANCELLED: "❌",
        }
        
        status_text = {
            MatchStatus.WAITING_FOR_OPPONENT: "Ожидание соперника",
            MatchStatus.SETTING_LINEUP: "Выбор состава",
            MatchStatus.IN_PROGRESS: "Матч идёт",
            MatchStatus.EXTRA_TIME: "Дополнительное время",
            MatchStatus.PENALTIES: "Серия пенальти",
            MatchStatus.FINISHED: "Матч завершён",
            MatchStatus.CANCELLED: "Матч отменён",
        }
        
        emoji = status_emoji.get(match.status, "❓")
        text = status_text.get(match.status, "Неизвестно")
        
        lines = [f"{emoji} <b>{text}</b>"]
        
        if match.status in [MatchStatus.IN_PROGRESS, MatchStatus.EXTRA_TIME]:
            # Рассчитываем текущий счёт
            if match.phase == MatchPhase.EXTRA_TIME:
                # В Extra Time показываем ТОЛЬКО счёт ET
                score1, score2, details = MatchRenderer.calculate_extra_time_score(match)
                lines.append(f"\n⏱ <b>Счёт ET: {score1}:{score2}</b>")
                lines.append(f"<i>{details}</i>")
                lines.append(f"<i>(Только статистика дополнительного времени!)</i>")
            else:
                score1, score2, details = MatchRenderer.calculate_current_score(match)
                lines.append(f"\n📊 <b>Счёт: {score1}:{score2}</b>")
                lines.append(f"<i>{details}</i>")
        
        return "\n".join(lines)
    
    @staticmethod
    def calculate_current_score(match: Match) -> tuple:
        """
        Рассчитать текущий счёт по формуле:
        1. Передачи пробивают отбития соперника (1:1)
        2. Каждый гол "съедает" до 2 отбитий, но сам НЕ проходит
        3. Гол проходит ТОЛЬКО когда отбитий = 0
        
        Возвращает: (голы_команды1, голы_команды2, детали_расчёта)
        """
        if not match.team1 or not match.team2:
            return 0, 0, ""
        
        match.team1.calculate_stats()
        match.team2.calculate_stats()
        
        # Команда 1 атакует команду 2
        passes1 = match.team1.stats.total_passes
        goals1_raw = match.team1.stats.total_goals
        saves2 = match.team2.stats.total_saves
        
        # Команда 2 атакует команду 1
        passes2 = match.team2.stats.total_passes
        goals2_raw = match.team2.stats.total_goals
        saves1 = match.team1.stats.total_saves
        
        # Расчёт голов команды 1 (атакует команду 2)
        remaining_saves2 = max(0, saves2 - passes1)
        if remaining_saves2 == 0:
            goals1 = goals1_raw
        else:
            goals_to_break = (remaining_saves2 + 1) // 2  # ceil
            goals1 = max(0, goals1_raw - goals_to_break)
        
        # Расчёт голов команды 2 (атакует команду 1)
        remaining_saves1 = max(0, saves1 - passes2)
        if remaining_saves1 == 0:
            goals2 = goals2_raw
        else:
            goals_to_break = (remaining_saves1 + 1) // 2  # ceil
            goals2 = max(0, goals2_raw - goals_to_break)
        
        # Формируем детали
        details_parts = []
        
        # Детали для команды 1
        if passes1 > 0 or goals1_raw > 0 or saves2 > 0:
            d1 = f"Вы: {goals1_raw}⚽"
            if passes1 > 0:
                d1 += f", {passes1}🎯"
            if saves2 > 0:
                d1 += f" vs {saves2}🛡"
                if passes1 > 0:
                    d1 += f" (перед съели {min(passes1, saves2)})"
                if remaining_saves2 > 0 and goals1_raw > 0:
                    goals_used = min(goals1_raw, (remaining_saves2 + 1) // 2)
                    d1 += f", голы съели {goals_used * 2 if goals_used * 2 <= remaining_saves2 else remaining_saves2}"
            details_parts.append(d1)
        
        # Детали для команды 2
        if passes2 > 0 or goals2_raw > 0 or saves1 > 0:
            d2 = f"Соп: {goals2_raw}⚽"
            if passes2 > 0:
                d2 += f", {passes2}🎯"
            if saves1 > 0:
                d2 += f" vs {saves1}🛡"
            details_parts.append(d2)
        
        details = " | ".join(details_parts) if details_parts else "0:0"
        
        return goals1, goals2, details
    
    @staticmethod
    def calculate_extra_time_score(match: Match) -> tuple:
        """
        Рассчитать счёт ТОЛЬКО для Extra Time.
        
        ВАЖНО: В ET учитываются ТОЛЬКО действия игроков, которые играли в ET!
        Статистика Main Time НЕ влияет на победителя ET.
        
        Формула:
        1. Передачи съедают отбития 1:1
        2. Каждый гол съедает до 2 отбитий, но сам НЕ проходит
        3. Гол проходит ТОЛЬКО когда отбитий = 0
        
        Возвращает: (голы_команды1, голы_команды2, детали_расчёта)
        """
        if not match.team1 or not match.team2:
            return 0, 0, ""
        
        from src.core.models.match import MatchPhase
        
        # Собираем статистику ТОЛЬКО игроков ET
        passes1 = 0
        goals1_raw = 0
        saves1 = 0
        
        passes2 = 0
        goals2_raw = 0
        saves2 = 0
        
        # Команда 1 — ищем игроков ET
        for player in match.team1.players:
            player_id_str = str(player.id)
            if player_id_str in match.used_players_extra_m1:
                passes1 += player.stats.passes
                goals1_raw += player.stats.goals
                saves1 += player.stats.saves
        
        # Команда 2 — ищем игроков ET
        for player in match.team2.players:
            player_id_str = str(player.id)
            if player_id_str in match.used_players_extra_m2:
                passes2 += player.stats.passes
                goals2_raw += player.stats.goals
                saves2 += player.stats.saves
        
        # Расчёт голов команды 1 (атакует команду 2)
        remaining_saves2 = max(0, saves2 - passes1)
        if remaining_saves2 == 0:
            goals1 = goals1_raw
        else:
            goals_to_break = (remaining_saves2 + 1) // 2  # ceil
            goals1 = max(0, goals1_raw - goals_to_break)
        
        # Расчёт голов команды 2 (атакует команду 1)
        remaining_saves1 = max(0, saves1 - passes2)
        if remaining_saves1 == 0:
            goals2 = goals2_raw
        else:
            goals_to_break = (remaining_saves1 + 1) // 2  # ceil
            goals2 = max(0, goals2_raw - goals_to_break)
        
        # Формируем детали
        details_parts = []
        
        if passes1 > 0 or goals1_raw > 0 or saves1 > 0:
            d1 = f"Вы ET: {goals1_raw}⚽, {passes1}🎯, {saves1}🛡"
            details_parts.append(d1)
        
        if passes2 > 0 or goals2_raw > 0 or saves2 > 0:
            d2 = f"Соп ET: {goals2_raw}⚽, {passes2}🎯, {saves2}🛡"
            details_parts.append(d2)
        
        details = " | ".join(details_parts) if details_parts else "0:0"
        
        return goals1, goals2, details
    
    @staticmethod
    def render_team_stats(team: Team, match: Match = None, is_opponent: bool = False) -> str:
        """Отрендерить статистику команды — только счёт и полезные действия"""
        team.calculate_stats()
        
        prefix = "🔴 Соперник" if is_opponent else "🔵 Ваша команда"
        
        lines = [f"<b>{prefix}</b>"]
        
        if match:
            is_m1 = team.manager_id == match.manager1_id
            used_mt = match.used_players_main_m1 if is_m1 else match.used_players_main_m2
            used_et = match.used_players_extra_m1 if is_m1 else match.used_players_extra_m2
            
            # Main Time
            mt_saves = mt_passes = mt_goals = 0
            for pid in used_mt:
                for p in team.players:
                    if str(p.id) == pid:
                        mt_saves += p.stats.saves
                        mt_passes += p.stats.passes
                        mt_goals += p.stats.goals
                        break
            lines.append(f"⏱ ОВ: 🛡{mt_saves} | 🎯{mt_passes} | ⚽{mt_goals}")
            
            # Extra Time
            if used_et:
                et_saves = et_passes = et_goals = 0
                for pid in used_et:
                    for p in team.players:
                        if str(p.id) == pid:
                            et_saves += p.stats.saves
                            et_passes += p.stats.passes
                            et_goals += p.stats.goals
                            break
                lines.append(f"⏱ ДВ: 🛡{et_saves} | 🎯{et_passes} | ⚽{et_goals}")
        else:
            lines.append(f"🛡{team.stats.total_saves} | 🎯{team.stats.total_passes} | ⚽{team.stats.total_goals}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _get_player_card_effects(match: Match, manager_id, player_id) -> str:
        """Получить список эффектов карточек для игрока"""
        effects = []
        
        for card in match.whistle_cards_drawn:
            if card.applied_to_player_id == player_id and card.is_used:
                card_name = card.get_display_name()
                
                # Определяем, позитивный или негативный эффект
                if card.card_type in [CardType.GOAL, CardType.DOUBLE, CardType.HAT_TRICK, 
                                      CardType.INTERCEPTION, CardType.TACKLE]:
                    effects.append(f"✅{card_name}")
                elif card.card_type in [CardType.FOUL, CardType.LOSS, CardType.YELLOW_CARD,
                                        CardType.OFFSIDE]:
                    effects.append(f"❌{card_name}")
                elif card.card_type == CardType.RED_CARD:
                    effects.append(f"🟥{card_name}")
                elif card.card_type == CardType.PENALTY:
                    if card.penalty_scored:
                        effects.append(f"⚽Пенальти")
                    else:
                        effects.append(f"❌Пенальти")
                else:
                    effects.append(card_name)
        
        return ", ".join(effects)
    
    @staticmethod
    def render_player_card(player: Player, show_stats: bool = True) -> str:
        """Отрендерить карточку игрока"""
        pos_emoji = {
            Position.GOALKEEPER: "🧤",
            Position.DEFENDER: "🛡",
            Position.MIDFIELDER: "🎯",
            Position.FORWARD: "⚡"
        }
        
        pos_name = {
            Position.GOALKEEPER: "Вратарь",
            Position.DEFENDER: "Защитник",
            Position.MIDFIELDER: "Полузащитник",
            Position.FORWARD: "Форвард"
        }
        
        emoji = pos_emoji.get(player.position, "")
        pos = pos_name.get(player.position, "")
        
        lines = [f"{emoji} <b>#{player.number} {player.name}</b> ({pos})"]
        
        if show_stats:
            stats = []
            if player.stats.saves > 0:
                stats.append(f"🛡 {player.stats.saves}")
            if player.stats.passes > 0:
                stats.append(f"🎯 {player.stats.passes}")
            if player.stats.goals > 0:
                stats.append(f"⚽ {player.stats.goals}")
            
            if stats:
                lines.append(" | ".join(stats))
            else:
                lines.append("—")
        
        if not player.is_available:
            lines.append("❌ Удалён")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_dice_result(
        dice_value: int,
        won_bets: List[Bet],
        lost_bets: List[Bet]
    ) -> str:
        """Отрендерить результат броска кубика"""
        dice_emoji = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
        
        lines = [
            f"🎲 Выпало: <b>{dice_emoji[dice_value]} {dice_value}</b>",
            "",
        ]
        
        if won_bets:
            lines.append(f"✅ Выиграно ставок: {len(won_bets)}")
            for bet in won_bets:
                lines.append(f"  • {bet.get_display_value()}")
        
        if lost_bets:
            lines.append(f"❌ Проиграно: {len(lost_bets)}")
        
        if not won_bets and not lost_bets:
            lines.append("Ставок не было")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_card_drawn(card: WhistleCard) -> str:
        """Отрендерить вытянутую карточку"""
        return f"🃏 Карточка: <b>{card.get_display_name()}</b>"
    
    @staticmethod
    def render_match_result(match: Match, viewer_id) -> str:
        """Отрендерить результат матча с статистикой карточек"""
        if not match.result:
            return "Результат не определён"
        
        is_winner = match.result.winner_id == viewer_id
        
        lines = [
            "🏁 <b>Матч завершён!</b>",
            "",
            f"📊 Счёт: <b>{match.score.manager1_goals}:{match.score.manager2_goals}</b>",
            "",
        ]
        
        if is_winner:
            lines.append("🎉 <b>Вы победили!</b>")
        else:
            lines.append("😔 <b>Вы проиграли</b>")
        
        phase_text = {
            MatchPhase.MAIN_TIME: "в основное время",
            MatchPhase.EXTRA_TIME: "в дополнительное время",
            MatchPhase.PENALTIES: "по пенальти",
        }
        lines.append(f"Решено {phase_text.get(match.result.decided_by, '')}")
        
        if match.result.decided_by_lottery:
            lines.append("(жребий)")
        
        # Статистика карточек Свисток
        lines.append("")
        lines.append("🃏 <b>Карточки Свисток:</b>")
        
        card_counts = {}
        for card in match.whistle_cards_drawn:
            card_name = card.get_display_name()
            card_counts[card_name] = card_counts.get(card_name, 0) + 1
        
        if card_counts:
            for card_name, count in sorted(card_counts.items(), key=lambda x: -x[1]):
                lines.append(f"   • {card_name}: {count}")
        else:
            lines.append("   Карточки не выпадали")
        
        lines.append(f"   <i>Всего вытянуто: {len(match.whistle_cards_drawn)}</i>")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_both_bets_before_roll(match: Match, viewer_id) -> str:
        """Отрендерить ставки ОБОИХ игроков перед броском кубика"""
        if not match.current_turn:
            return "Ход не начат"
        
        turn = match.current_turn
        lines = [
            f"🎲 <b>Ход {turn.turn_number} — Ставки сделаны!</b>",
            "",
        ]
        
        is_user_m1 = match.manager1_id == viewer_id
        
        # Ставки пользователя
        user_player_id = turn.manager1_player_id if is_user_m1 else turn.manager2_player_id
        user_bets_ids = turn.manager1_bets if is_user_m1 else turn.manager2_bets
        
        user_team = match.team1 if is_user_m1 else match.team2
        user_player = user_team.get_player_by_id(user_player_id) if user_team and user_player_id else None
        
        lines.append("🔵 <b>Ваши ставки:</b>")
        if user_player:
            lines.append(f"   Игрок: {user_player.name}")
        
        for bet_id in user_bets_ids:
            bet = next((b for b in match.bets if b.id == bet_id), None)
            if bet:
                lines.append(f"   • {bet.bet_type.value}: {bet.get_display_value()}")
        
        lines.append("")
        
        # Ставки соперника (бота)
        opp_player_id = turn.manager2_player_id if is_user_m1 else turn.manager1_player_id
        opp_bets_ids = turn.manager2_bets if is_user_m1 else turn.manager1_bets
        
        opp_team = match.team2 if is_user_m1 else match.team1
        opp_player = opp_team.get_player_by_id(opp_player_id) if opp_team and opp_player_id else None
        
        lines.append("🔴 <b>Ставки соперника:</b>")
        if opp_player:
            lines.append(f"   Игрок: {opp_player.name}")
        
        for bet_id in opp_bets_ids:
            bet = next((b for b in match.bets if b.id == bet_id), None)
            if bet:
                lines.append(f"   • {bet.bet_type.value}: {bet.get_display_value()}")
        
        lines.append("")
        lines.append("Нажмите кнопку, чтобы бросить кубик!")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_turn_info(match: Match, viewer_id) -> str:
        """Отрендерить информацию о текущем ходе (legacy)"""
        if not match.current_turn:
            return ""
        
        turn = match.current_turn
        is_my_turn = turn.current_manager_id == viewer_id
        
        lines = []
        
        if is_my_turn:
            lines.append("👉 <b>Ваш ход</b>")
            
            if not turn.bets_placed:
                lines.append("Сделайте ставки на игроков")
            elif not turn.dice_rolled:
                lines.append("Бросьте кубик или добавьте ещё ставки")
            elif not turn.card_drawn:
                lines.append("Возьмите карточку Свисток")
            else:
                lines.append("Завершите ход")
        else:
            lines.append("⏳ <b>Ход соперника</b>")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_turn_info_simultaneous(match: Match, viewer_id) -> str:
        """Отрендерить информацию о ходе (одновременные ставки)"""
        if not match.current_turn:
            return ""
        
        turn = match.current_turn
        is_m1 = match.manager1_id == viewer_id
        
        lines = [f"🔄 <b>Ход {turn.turn_number}</b>"]
        
        # Требуемое количество ставок
        required = turn.get_required_bets_count()
        
        # Статус своих ставок
        if is_m1:
            my_bets = len(turn.manager1_bets)
            my_ready = turn.manager1_ready
            opp_ready = turn.manager2_ready
        else:
            my_bets = len(turn.manager2_bets)
            my_ready = turn.manager2_ready
            opp_ready = turn.manager1_ready
        
        if not turn.dice_rolled:
            if not my_ready:
                lines.append(f"📝 Ваши ставки: {my_bets}/{required}")
                if my_bets < required:
                    lines.append("👉 <i>Сделайте ставки и подтвердите</i>")
                else:
                    lines.append("👉 <i>Подтвердите ставки</i>")
            else:
                lines.append("✅ Ваши ставки подтверждены")
                if not opp_ready:
                    lines.append("⏳ Ожидаем соперника...")
        else:
            lines.append("🎲 Кубик брошен!")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_dice_result_simultaneous(
        dice_value: int,
        won_bets_by_manager: dict,
        match: Match,
        viewer_id
    ) -> str:
        """Отрендерить результат броска для обоих игроков"""
        dice_emoji = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
        
        lines = [
            f"🎲 Выпало: <b>{dice_emoji[dice_value]} {dice_value}</b>",
            "",
        ]
        
        # Результаты для пользователя
        is_m1 = match.manager1_id == viewer_id
        my_won = won_bets_by_manager.get(viewer_id, [])
        
        if my_won:
            lines.append(f"✅ <b>Вы выиграли {len(my_won)} ставок!</b>")
            for bet in my_won:
                lines.append(f"  • {bet.get_display_value()}")
        else:
            lines.append("❌ Вы не выиграли ставки")
        
        # Результаты соперника
        opp_id = match.manager2_id if is_m1 else match.manager1_id
        opp_won = won_bets_by_manager.get(opp_id, [])
        
        lines.append("")
        if opp_won:
            lines.append(f"🔴 Соперник выиграл {len(opp_won)} ставок")
        else:
            lines.append("🔴 Соперник не выиграл ставки")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_cards_drawn(match: Match, viewer_id) -> str:
        """Отрендерить вытянутые карточки и их эффекты"""
        if not match.current_turn:
            return ""
        
        turn = match.current_turn
        is_m1 = match.manager1_id == viewer_id
        
        lines = []
        
        # Моя карточка
        my_card_id = turn.manager1_card_id if is_m1 else turn.manager2_card_id
        if my_card_id:
            card = next((c for c in match.whistle_cards_drawn if c.id == my_card_id), None)
            if card:
                card_text = f"🃏 Ваша карточка: <b>{card.get_display_name()}</b>"
                if card.is_used:
                    card_text += " ✅"
                    # Показываем результат пенальти
                    if card.penalty_scored is not None:
                        card_text += " ⚽ ГОЛ!" if card.penalty_scored else " ❌ Промах"
                lines.append(card_text)
        
        # Карточка соперника
        opp_card_id = turn.manager2_card_id if is_m1 else turn.manager1_card_id
        if opp_card_id:
            card = next((c for c in match.whistle_cards_drawn if c.id == opp_card_id), None)
            if card:
                card_text = f"🔴 Карточка соперника: <b>{card.get_display_name()}</b>"
                if card.is_used:
                    card_text += " ✅"
                    if card.penalty_scored is not None:
                        card_text += " ⚽ ГОЛ!" if card.penalty_scored else " ❌ Промах"
                lines.append(card_text)
        
        return "\n".join(lines) if lines else ""


    @staticmethod
    def render_match_history(match: Match, viewer_id) -> str:
        """Отрендерить полную историю ходов матча"""
        lines = ["📜 <b>ИСТОРИЯ МАТЧА</b>\n"]
        
        is_viewer_m1 = viewer_id == match.manager1_id
        
        # Получаем команды
        viewer_team = match.team1 if is_viewer_m1 else match.team2
        opponent_team = match.team2 if is_viewer_m1 else match.team1
        
        if not viewer_team or not opponent_team:
            return "История недоступна"
        
        # Собираем историю по ходам из ставок
        turns_data = {}
        
        for bet in match.bets:
            turn_num = bet.turn_number
            if turn_num not in turns_data:
                turns_data[turn_num] = {"viewer": [], "opponent": [], "dice": None}
            
            is_viewer_bet = bet.manager_id == viewer_id
            key = "viewer" if is_viewer_bet else "opponent"
            turns_data[turn_num][key].append(bet)
            
            # Сохраняем результат кубика из ставки (все ставки хода имеют один dice_result)
            if bet.dice_result:
                turns_data[turn_num]["dice"] = bet.dice_result
        
        # Получаем использованных игроков по порядку
        viewer_used_mt = match.used_players_main_m1 if is_viewer_m1 else match.used_players_main_m2
        opponent_used_mt = match.used_players_main_m1 if not is_viewer_m1 else match.used_players_main_m2
        viewer_used_et = match.used_players_extra_m1 if is_viewer_m1 else match.used_players_extra_m2
        opponent_used_et = match.used_players_extra_m1 if not is_viewer_m1 else match.used_players_extra_m2
        
        # Main Time
        if viewer_used_mt:
            lines.append("<b>⏱ ОСНОВНОЕ ВРЕМЯ</b>")
            for turn_idx, player_id_str in enumerate(viewer_used_mt, 1):
                # Кубик
                dice_val = turns_data.get(turn_idx, {}).get("dice", "?")
                turn_lines = [f"\n<b>Ход {turn_idx}</b> 🎲 {dice_val}"]
                
                # Находим игрока
                viewer_player = next((p for p in viewer_team.players if str(p.id) == player_id_str), None)
                opp_player_id = opponent_used_mt[turn_idx - 1] if turn_idx - 1 < len(opponent_used_mt) else None
                opp_player = next((p for p in opponent_team.players if str(p.id) == opp_player_id), None) if opp_player_id else None
                
                if viewer_player:
                    turn_lines.append(f"  🔵 {viewer_player.name}")
                    # Ставки
                    if turn_idx in turns_data:
                        for bet in turns_data[turn_idx]["viewer"]:
                            bet_str = MatchRenderer._format_bet(bet)
                            outcome = "✅" if bet.outcome == BetOutcome.WON else "❌"
                            turn_lines.append(f"      {bet_str} {outcome}")
                    # Итог
                    stats = MatchRenderer._format_player_stats(viewer_player)
                    turn_lines.append(f"      → {stats}")
                
                if opp_player:
                    turn_lines.append(f"  🔴 {opp_player.name}")
                    if turn_idx in turns_data:
                        for bet in turns_data[turn_idx]["opponent"]:
                            bet_str = MatchRenderer._format_bet(bet)
                            outcome = "✅" if bet.outcome == BetOutcome.WON else "❌"
                            turn_lines.append(f"      {bet_str} {outcome}")
                    stats = MatchRenderer._format_player_stats(opp_player)
                    turn_lines.append(f"      → {stats}")
                
                # Карточки этого хода
                for card in match.whistle_cards_drawn:
                    if card.turn_applied == turn_idx:
                        who = "🔵" if card.applied_by_manager_id == viewer_id else "🔴"
                        card_info = card.get_display_name()
                        # Результат пенальти
                        if card.card_type.value == "penalty" and card.penalty_scored is not None:
                            pen_result = "⚽ГОЛ" if card.penalty_scored else "❌МИМО"
                            card_info += f" ({pen_result})"
                        turn_lines.append(f"  🃏 {who} {card_info}")
                
                lines.extend(turn_lines)
        
        # Extra Time
        if viewer_used_et:
            lines.append("\n\n<b>⏱ ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ</b>")
            for turn_idx, player_id_str in enumerate(viewer_used_et, 1):
                et_turn_num = 11 + turn_idx
                dice_val = turns_data.get(et_turn_num, {}).get("dice", "?")
                turn_lines = [f"\n<b>Ход ET-{turn_idx}</b> 🎲 {dice_val}"]
                
                viewer_player = next((p for p in viewer_team.players if str(p.id) == player_id_str), None)
                opp_player_id = opponent_used_et[turn_idx - 1] if turn_idx - 1 < len(opponent_used_et) else None
                opp_player = next((p for p in opponent_team.players if str(p.id) == opp_player_id), None) if opp_player_id else None
                
                if viewer_player:
                    turn_lines.append(f"  🔵 {viewer_player.name}")
                    stats = MatchRenderer._format_player_stats(viewer_player)
                    turn_lines.append(f"      → {stats}")
                
                if opp_player:
                    turn_lines.append(f"  🔴 {opp_player.name}")
                    stats = MatchRenderer._format_player_stats(opp_player)
                    turn_lines.append(f"      → {stats}")
                
                # Карточки ET
                for card in match.whistle_cards_drawn:
                    if card.turn_applied == et_turn_num:
                        who = "🔵" if card.applied_by_manager_id == viewer_id else "🔴"
                        card_info = card.get_display_name()
                        if card.card_type.value == "penalty" and card.penalty_scored is not None:
                            pen_result = "⚽ГОЛ" if card.penalty_scored else "❌МИМО"
                            card_info += f" ({pen_result})"
                        turn_lines.append(f"  🃏 {who} {card_info}")
                
                lines.extend(turn_lines)
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_player_stats(player) -> str:
        """Форматировать статистику игрока"""
        stats = []
        if player.stats.saves > 0:
            stats.append(f"{player.stats.saves}🛡")
        if player.stats.passes > 0:
            stats.append(f"{player.stats.passes}🎯")
        if player.stats.goals > 0:
            stats.append(f"{player.stats.goals}⚽")
        return " ".join(stats) if stats else "—"
    
    @staticmethod
    def _format_bet(bet: Bet) -> str:
        """Форматировать ставку"""
        from src.core.models.bet import BetType
        
        if bet.bet_type == BetType.EVEN_ODD:
            choice = "Чёт" if bet.even_odd_choice and bet.even_odd_choice.value == "even" else "Нечёт"
            return f"Чёт/Нечёт: {choice}"
        elif bet.bet_type == BetType.HIGH_LOW:
            choice = "Больше" if bet.high_low_choice and bet.high_low_choice.value == "high" else "Меньше"
            return f"Б/М: {choice}"
        elif bet.bet_type == BetType.EXACT_NUMBER:
            return f"Точное: {bet.exact_number}"
        return str(bet.bet_type.value)
