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
        2. Если передачи >= отбития — все голы засчитываются
        3. Если отбития > передачи — оставшиеся гасят голы (2:1)
        
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
        
        # Расчёт голов команды 1
        remaining_saves2 = max(0, saves2 - passes1)  # Отбития после пробития передачами
        goals1 = max(0, goals1_raw - (remaining_saves2 // 2))  # 1 гол съедает 2 отбития
        
        # Расчёт голов команды 2
        remaining_saves1 = max(0, saves1 - passes2)
        goals2 = max(0, goals2_raw - (remaining_saves1 // 2))
        
        # Формируем детали
        details_parts = []
        
        # Детали для команды 1
        if passes1 > 0 or goals1_raw > 0:
            d1 = f"Вы: {goals1_raw}⚽"
            if passes1 > 0:
                d1 += f", {passes1}🎯"
            if saves2 > 0:
                blocked = min(passes1, saves2)
                d1 += f" (пробито {blocked} отб)"
            if remaining_saves2 > 0 and goals1_raw > 0:
                canceled = remaining_saves2 // 2
                if canceled > 0:
                    d1 += f", -{canceled}⚽ (голы съели {canceled*2} отб)"
            details_parts.append(d1)
        
        # Детали для команды 2
        if passes2 > 0 or goals2_raw > 0:
            d2 = f"Соп: {goals2_raw}⚽"
            if passes2 > 0:
                d2 += f", {passes2}🎯"
            if saves1 > 0:
                blocked = min(passes2, saves1)
                d2 += f" (пробито {blocked} отб)"
            if remaining_saves1 > 0 and goals2_raw > 0:
                canceled = remaining_saves1 // 2
                if canceled > 0:
                    d2 += f", -{canceled}⚽ (голы съели {canceled*2} отб)"
            details_parts.append(d2)
        
        details = " | ".join(details_parts) if details_parts else "0:0"
        
        return goals1, goals2, details
    
    @staticmethod
    def calculate_extra_time_score(match: Match) -> tuple:
        """
        Рассчитать счёт ТОЛЬКО для Extra Time.
        
        ВАЖНО: В ET учитываются ТОЛЬКО действия игроков, которые играли в ET!
        Статистика Main Time НЕ влияет на победителя ET.
        
        Возвращает: (голы_команды1, голы_команды2, детали_расчёта)
        """
        if not match.team1 or not match.team2:
            return 0, 0, ""
        
        from src.core.models.match import MatchPhase
        
        # Собираем статистику ТОЛЬКО игроков ET
        # Проверяем, в какой фазе играл каждый игрок
        passes1 = 0
        goals1_raw = 0
        saves1 = 0
        
        passes2 = 0
        goals2_raw = 0
        saves2 = 0
        
        # Команда 1 — ищем игроков ET
        for player in match.team1.players:
            # Проверяем, использован ли игрок в Extra Time
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
        goals1 = max(0, goals1_raw - (remaining_saves2 // 2))
        
        # Расчёт голов команды 2 (атакует команду 1)
        remaining_saves1 = max(0, saves1 - passes2)
        goals2 = max(0, goals2_raw - (remaining_saves1 // 2))
        
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
        """Отрендерить статистику команды с эффектами карточек"""
        team.calculate_stats()
        
        prefix = "🔴 Соперник" if is_opponent else "🔵 Ваша команда"
        
        lines = [
            f"<b>{prefix}: {team.name}</b>",
            f"🛡 Отбития: {team.stats.total_saves}",
            f"🎯 Передачи: {team.stats.total_passes}",
            f"⚽ Голы: {team.stats.total_goals}",
        ]
        
        # Показываем статистику каждого игравшего игрока
        played_players = [p for p in team.players if p.stats.saves > 0 or p.stats.passes > 0 or p.stats.goals > 0]
        
        # Сортируем по порядку ходов (используем историю матча)
        if match and played_players:
            # Получаем порядок из использованных игроков
            used_order = match.get_used_players(team.manager_id)
            
            def get_turn_order(player):
                try:
                    return used_order.index(player.id)
                except (ValueError, AttributeError):
                    return 999
            
            played_players = sorted(played_players, key=get_turn_order)
        
        if played_players:
            lines.append("\n<b>Игроки (по ходам):</b>")
            for i, p in enumerate(played_players, 1):
                stats_str = []
                if p.stats.saves > 0:
                    stats_str.append(f"{p.stats.saves} отб")
                if p.stats.passes > 0:
                    stats_str.append(f"{p.stats.passes} пер")
                if p.stats.goals > 0:
                    stats_str.append(f"{p.stats.goals} гол")
                
                player_line = f"  {i}. {p.name}: {', '.join(stats_str)}"
                
                # Добавляем эффекты карточек
                if match:
                    card_effects = MatchRenderer._get_player_card_effects(match, team.manager_id, p.id)
                    if card_effects:
                        player_line += f" [{card_effects}]"
                
                lines.append(player_line)
        
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
