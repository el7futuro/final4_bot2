# src/core/engine/action_calculator.py
"""Расчёт полезных действий"""

from ..models.player import Player, Position
from ..models.bet import Bet, BetType, BetOutcome


class ActionCalculator:
    """Расчёт полезных действий при выигрыше ставки"""
    
    # Полезные действия при выигрыше ставки на чёт/нечёт
    SAVES_BY_POSITION = {
        Position.GOALKEEPER: 3,
        Position.DEFENDER: 2,
        Position.MIDFIELDER: 1,
        Position.FORWARD: 0,
    }
    
    # Полезные действия при выигрыше ставки на больше/меньше
    PASSES_BY_POSITION = {
        Position.GOALKEEPER: 0,
        Position.DEFENDER: 1,
        Position.MIDFIELDER: 2,
        Position.FORWARD: 1,
    }
    
    def apply_bet_result(self, player: Player, bet: Bet) -> None:
        """
        Применить результат выигранной ставки к игроку.
        
        Args:
            player: Игрок, на которого была ставка
            bet: Выигранная ставка
        """
        if bet.outcome != BetOutcome.WON:
            return
        
        if bet.bet_type == BetType.EVEN_ODD:
            # Чёт/нечёт -> отбития
            saves = self.SAVES_BY_POSITION.get(player.position, 0)
            player.add_saves(saves)
        
        elif bet.bet_type == BetType.HIGH_LOW:
            # Больше/меньше -> передачи
            passes = self.PASSES_BY_POSITION.get(player.position, 0)
            player.add_passes(passes)
        
        elif bet.bet_type == BetType.EXACT_NUMBER:
            # Точное число -> гол
            player.add_goals(1)
    
    def get_action_preview(self, player: Player, bet_type: BetType) -> str:
        """
        Получить превью действия при выигрыше.
        
        Returns:
            Строка с описанием награды
        """
        if bet_type == BetType.EVEN_ODD:
            saves = self.SAVES_BY_POSITION.get(player.position, 0)
            return f"+{saves} отбит." if saves > 0 else "—"
        
        elif bet_type == BetType.HIGH_LOW:
            passes = self.PASSES_BY_POSITION.get(player.position, 0)
            return f"+{passes} перед." if passes > 0 else "—"
        
        elif bet_type == BetType.EXACT_NUMBER:
            return "+1 гол"
        
        return "—"
