# src/core/models/player.py
"""Модель футболиста"""

from enum import Enum
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class Position(str, Enum):
    """Позиции игроков"""
    GOALKEEPER = "goalkeeper"
    DEFENDER = "defender"
    MIDFIELDER = "midfielder"
    FORWARD = "forward"


class PlayerStats(BaseModel):
    """Полезные действия футболиста в матче"""
    saves: int = Field(default=0, ge=0, description="Отбития")
    passes: int = Field(default=0, ge=0, description="Передачи")
    goals: int = Field(default=0, ge=0, description="Голы")


class Player(BaseModel):
    """Футболист в команде"""
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=50)
    position: Position
    number: int = Field(ge=1, le=99)
    stats: PlayerStats = Field(default_factory=PlayerStats)
    is_on_field: bool = Field(default=False)
    is_available: bool = Field(default=True)
    yellow_cards: int = Field(default=0, ge=0, le=2)

    def add_saves(self, count: int) -> None:
        """Добавить отбития"""
        self.stats.saves += count

    def add_passes(self, count: int) -> None:
        """Добавить передачи"""
        self.stats.passes += count

    def add_goals(self, count: int) -> None:
        """Добавить голы"""
        self.stats.goals += count

    def remove_action(self, action_type: str) -> bool:
        """Удалить одно действие. Возвращает True если успешно."""
        if action_type == "save" and self.stats.saves > 0:
            self.stats.saves -= 1
            return True
        elif action_type == "pass" and self.stats.passes > 0:
            self.stats.passes -= 1
            return True
        elif action_type == "goal" and self.stats.goals > 0:
            self.stats.goals -= 1
            return True
        return False

    def clear_stats(self) -> None:
        """Обнулить все действия (удаление)"""
        self.stats = PlayerStats()
        self.is_available = False

    def get_total_actions(self) -> int:
        """Общее количество действий"""
        return self.stats.saves + self.stats.passes + self.stats.goals
