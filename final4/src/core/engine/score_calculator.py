# src/core/engine/score_calculator.py
"""Расчёт итогового счёта матча"""

from ..models.team import Team
from ..models.match import MatchScore


class ScoreCalculator:
    """Расчёт итогового счёта матча"""
    
    def calculate_score(self, team1: Team, team2: Team) -> MatchScore:
        """
        Рассчитать итоговый счёт.
        
        Алгоритм:
        1. Берём отбития соперника, вычитаем свои передачи
        2. Если передач >= отбитий — все голы засчитываются
        3. Если отбитий больше — голы тратятся на уничтожение отбитий (1 гол = 2 отбития)
        4. Оставшиеся голы засчитываются
        
        Args:
            team1: Команда менеджера 1
            team2: Команда менеджера 2
            
        Returns:
            MatchScore с голами обеих сторон
        """
        # Пересчитываем статистику команд
        team1.calculate_stats()
        team2.calculate_stats()
        
        # Голы team1 против обороны team2
        goals1 = self._calculate_goals_scored(
            own_passes=team1.stats.total_passes,
            own_goals=team1.stats.total_goals,
            opponent_saves=team2.stats.total_saves
        )
        
        # Голы team2 против обороны team1
        goals2 = self._calculate_goals_scored(
            own_passes=team2.stats.total_passes,
            own_goals=team2.stats.total_goals,
            opponent_saves=team1.stats.total_saves
        )
        
        return MatchScore(manager1_goals=goals1, manager2_goals=goals2)
    
    def _calculate_goals_scored(
        self,
        own_passes: int,
        own_goals: int,
        opponent_saves: int
    ) -> int:
        """
        Рассчитать забитые голы для одной команды.
        
        Формула:
        - remaining_saves = opponent_saves - own_passes
        - Если remaining_saves <= 0: все голы засчитываются
        - Иначе: goals_needed = ceil(remaining_saves / 2)
        - scored = max(0, own_goals - goals_needed)
        """
        # Остаточные отбития после применения передач
        remaining_saves = opponent_saves - own_passes
        
        if remaining_saves <= 0:
            # Оборона полностью взломана, все голы засчитываются
            return own_goals
        
        # Голы тратятся на уничтожение отбитий: 1 гол = 2 отбития
        # Округление вверх: (remaining_saves + 1) // 2
        goals_needed_to_clear = (remaining_saves + 1) // 2
        
        # Оставшиеся голы после уничтожения отбитий
        scored_goals = max(0, own_goals - goals_needed_to_clear)
        
        return scored_goals
    
    def get_score_explanation(
        self,
        own_passes: int,
        own_goals: int,
        opponent_saves: int
    ) -> str:
        """
        Получить объяснение расчёта счёта.
        
        Returns:
            Текстовое объяснение
        """
        remaining_saves = opponent_saves - own_passes
        
        if remaining_saves <= 0:
            return (
                f"Передачи ({own_passes}) >= Отбития соперника ({opponent_saves})\n"
                f"Оборона взломана! Все {own_goals} голов засчитаны."
            )
        
        goals_needed = (remaining_saves + 1) // 2
        scored = max(0, own_goals - goals_needed)
        
        return (
            f"Отбития соперника: {opponent_saves}\n"
            f"Ваши передачи: -{own_passes}\n"
            f"Остаток отбитий: {remaining_saves}\n"
            f"Голов на пробитие: {goals_needed} (1 гол = 2 отб.)\n"
            f"Ваши голы: {own_goals}\n"
            f"Забито: {scored}"
        )
