# src/core/engine/score_calculator.py
"""Расчёт итогового счёта матча"""

from typing import Optional, TYPE_CHECKING

from ..models.team import Team
from ..models.match import MatchScore, MatchPhase

if TYPE_CHECKING:
    from ..models.match_history import MatchHistory


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
    
    def calculate_score_from_history(
        self,
        history: 'MatchHistory',
        manager1_id,
        manager2_id,
        phase: Optional[MatchPhase] = None
    ) -> MatchScore:
        """
        Рассчитать счёт на основе истории матча.
        
        Если указана фаза — считает ТОЛЬКО статистику этой фазы.
        Это критично для Дополнительного Времени, где победитель
        определяется ТОЛЬКО по действиям в ET, без учёта Main Time.
        
        Args:
            history: История матча
            manager1_id: ID менеджера 1
            manager2_id: ID менеджера 2
            phase: Фаза матча (если None — все фазы)
        """
        if phase is not None:
            stats1 = history.get_total_stats_by_phase(manager1_id, manager1_id, phase)
            stats2 = history.get_total_stats_by_phase(manager2_id, manager1_id, phase)
        else:
            stats1 = history.get_total_stats(manager1_id, manager1_id)
            stats2 = history.get_total_stats(manager2_id, manager1_id)
        
        # Голы team1 против обороны team2
        goals1 = self._calculate_goals_scored(
            own_passes=stats1["passes"],
            own_goals=stats1["goals"],
            opponent_saves=stats2["saves"]
        )
        
        # Голы team2 против обороны team1
        goals2 = self._calculate_goals_scored(
            own_passes=stats2["passes"],
            own_goals=stats2["goals"],
            opponent_saves=stats1["saves"]
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
        2. Каждый гол "съедает" до 2 отбитий, но сам НЕ проходит пока есть отбития
        3. Гол проходит ТОЛЬКО когда отбитий = 0
        
        Примеры:
        - 3 отбития, 1 гол + 1 передача: передача→2 отб, гол съедает 2→0 отб, гол НЕ прошёл = 0:0
        - 3 отбития, 2 гола: гол1 съедает 2→1 отб, гол2 съедает 1→0 отб = 0:0
        - 2 отбития, 3 гола: гол1 съедает 2→0 отб, гол2 проходит, гол3 проходит = 2:0
        """
        # Передачи пробивают отбития 1:1
        remaining_saves = max(0, opponent_saves - own_passes)
        
        if remaining_saves == 0:
            # Оборона полностью пробита — все голы проходят
            return own_goals
        
        # Каждый гол "съедает" до 2 отбитий, но сам не проходит
        # Нужно ceil(remaining_saves / 2) голов чтобы пробить оборону
        goals_needed_to_break = (remaining_saves + 1) // 2  # ceil division
        
        # Оставшиеся голы проходят
        return max(0, own_goals - goals_needed_to_break)
    
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
            blocked = remaining_saves // 2
            total = max(0, own_goals - blocked)
            lines.extend([
                f"Остаток отбитий: {remaining_saves}",
                f"Голы съедают отбития: {remaining_saves} // 2 = {blocked}",
                f"Ваши голы: {own_goals}",
                f"ИТОГО забито: max(0, {own_goals} - {blocked}) = {total}",
            ])
        
        return "\n".join(lines)
