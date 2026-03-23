# src/platforms/telegram/renderers/match_renderer.py
"""Рендеринг сообщений матча"""

from typing import List, Optional

from src.core.models.match import Match, MatchStatus, MatchPhase
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetOutcome
from src.core.models.whistle_card import WhistleCard


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
            lines.append(f"\n📊 Счёт: <b>{match.score.manager1_goals}:{match.score.manager2_goals}</b>")
            
            if match.current_turn:
                lines.append(f"🔄 Ход: {match.current_turn.turn_number}")
                
                # Чей ход
                if viewer_id:
                    if match.current_turn.current_manager_id == viewer_id:
                        lines.append("👉 <b>Ваш ход!</b>")
                    else:
                        lines.append("⏳ Ход соперника")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_team_stats(team: Team, is_opponent: bool = False) -> str:
        """Отрендерить статистику команды"""
        team.calculate_stats()
        
        prefix = "🔴 Соперник" if is_opponent else "🔵 Ваша команда"
        
        lines = [
            f"<b>{prefix}: {team.name}</b>",
            f"🛡 Отбития: {team.stats.total_saves}",
            f"🎯 Передачи: {team.stats.total_passes}",
            f"⚽ Голы: {team.stats.total_goals}",
        ]
        
        return "\n".join(lines)
    
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
        """Отрендерить результат матча"""
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
        """Отрендерить вытянутые карточки"""
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
                lines.append(f"🃏 Ваша карточка: <b>{card.get_display_name()}</b>")
        
        # Карточка соперника
        opp_card_id = turn.manager2_card_id if is_m1 else turn.manager1_card_id
        if opp_card_id:
            card = next((c for c in match.whistle_cards_drawn if c.id == opp_card_id), None)
            if card:
                lines.append(f"🔴 Карточка соперника: <b>{card.get_display_name()}</b>")
        
        return "\n".join(lines) if lines else ""
