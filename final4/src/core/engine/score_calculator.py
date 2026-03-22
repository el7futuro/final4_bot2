# src/core/engine/score_calculator.py
"""Расчёт итогового счёта матча"""

from ..models.team import Team
from ..models.match import MatchScore


class ScoreCalculator:
    """Расчёт итогового счёта матча"""
    
    def calculate_score(self, team1: Team, team2: Team) -> MatchScore:
        """
        Рассчитать итоговый счёт.
        
        Алгоритм по правилам:
        1. Передачи атакующего пробивают отбития защитника
        2. Оставшиеся передачи / 2 = дополнительные голы (округление вниз)
        3. Голы атакующего засчитываются напрямую
        4. Если у защитника остались отбития — они гасят голы (2 отб = 1 гол)
        
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
        
        Формула по правилам:
        1. Передачи пробивают отбития (1:1)
        2. Если передачи >= отбития → все голы засчитываются
        3. Если отбития > передачи → оставшиеся отбития гасят голы (2 отб = 1 гол)
        
        Лишние передачи НЕ конвертируются в голы!
        """
        # Передачи пробивают отбития
        remaining_saves = opponent_saves - own_passes
        
        if remaining_saves <= 0:
            # Оборона пробита — все голы засчитываются
            return own_goals
        else:
            # Оборона устояла частично
            # Оставшиеся отбития гасят голы (2 отбития = 1 гол)
            goals_blocked = (remaining_saves + 1) // 2
            return max(0, own_goals - goals_blocked)
    
    def get_score_explanation(
        self,
        own_passes: int,
        own_goals: int,
        opponent_saves: int
    ) -> str:
        """
        Получить объяснение расчёта счёта.
        """
        remaining_saves = opponent_saves - own_passes
        
        lines = [
            f"Ваши передачи: {own_passes}",
            f"Отбития соперника: {opponent_saves}",
        ]
        
        if remaining_saves <= 0:
            lines.extend([
                f"Передачи пробили все отбития!",
                f"Ваши голы: {own_goals}",
                f"ИТОГО забито: {own_goals}",
            ])
        else:
            blocked = (remaining_saves + 1) // 2
            total = max(0, own_goals - blocked)
            lines.extend([
                f"Остаток отбитий: {remaining_saves}",
                f"Отбития гасят голы: ({remaining_saves} + 1) // 2 = {blocked}",
                f"Ваши голы: {own_goals}",
                f"ИТОГО забито: max(0, {own_goals} - {blocked}) = {total}",
            ])
        
        return "\n".join(lines)
