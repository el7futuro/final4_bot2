# src/core/models/team.py
"""Модель команды"""

from enum import Enum
from uuid import UUID, uuid4
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator

from .player import Player, Position


class Formation(str, Enum):
    """Допустимые расстановки"""
    F_5_3_2 = "1-5-3-2"
    F_5_2_3 = "1-5-2-3"
    F_4_4_2 = "1-4-4-2"
    F_4_3_3 = "1-4-3-3"
    F_3_5_2 = "1-3-5-2"
    F_3_4_3 = "1-3-4-3"
    F_3_3_4 = "1-3-3-4"


FORMATION_STRUCTURE = {
    Formation.F_5_3_2: {"goalkeeper": 1, "defender": 5, "midfielder": 3, "forward": 2},
    Formation.F_5_2_3: {"goalkeeper": 1, "defender": 5, "midfielder": 2, "forward": 3},
    Formation.F_4_4_2: {"goalkeeper": 1, "defender": 4, "midfielder": 4, "forward": 2},
    Formation.F_4_3_3: {"goalkeeper": 1, "defender": 4, "midfielder": 3, "forward": 3},
    Formation.F_3_5_2: {"goalkeeper": 1, "defender": 3, "midfielder": 5, "forward": 2},
    Formation.F_3_4_3: {"goalkeeper": 1, "defender": 3, "midfielder": 4, "forward": 3},
    Formation.F_3_3_4: {"goalkeeper": 1, "defender": 3, "midfielder": 3, "forward": 4},
}


class TeamStats(BaseModel):
    """Суммарная статистика команды"""
    total_saves: int = Field(default=0, ge=0)
    total_passes: int = Field(default=0, ge=0)
    total_goals: int = Field(default=0, ge=0)


class Team(BaseModel):
    """Команда менеджера"""
    id: UUID = Field(default_factory=uuid4)
    manager_id: UUID
    name: str = Field(min_length=1, max_length=100)
    players: List[Player] = Field(default_factory=list, max_length=16)
    formation: Optional[Formation] = None
    stats: TeamStats = Field(default_factory=TeamStats)

    @model_validator(mode='after')
    def validate_squad_size(self) -> 'Team':
        if len(self.players) > 16:
            raise ValueError("Максимум 16 футболистов в составе")
        return self

    def get_players_by_position(self, position: Position) -> List[Player]:
        """Получить игроков по позиции"""
        return [p for p in self.players if p.position == position]

    def get_field_players(self) -> List[Player]:
        """Получить игроков на поле"""
        return [p for p in self.players if p.is_on_field]

    def get_available_players(self) -> List[Player]:
        """Получить доступных игроков"""
        return [p for p in self.players if p.is_available]

    def get_goalkeeper(self) -> Optional[Player]:
        """Получить вратаря на поле"""
        gks = [p for p in self.players if p.position == Position.GOALKEEPER and p.is_on_field]
        return gks[0] if gks else None

    def get_player_by_id(self, player_id: UUID) -> Optional[Player]:
        """Получить игрока по ID"""
        for p in self.players:
            if p.id == player_id:
                return p
        return None

    def set_formation(self, formation: Formation) -> None:
        """Установить расстановку"""
        self.formation = formation

    def set_lineup(self, player_ids: List[UUID]) -> bool:
        """Выставить состав на поле. Возвращает True если валидно."""
        if not self.formation:
            return False
        
        # Сначала снимаем всех с поля
        for p in self.players:
            p.is_on_field = False
        
        # Выставляем выбранных
        selected = [p for p in self.players if p.id in player_ids and p.is_available]
        if len(selected) != 11:
            return False
        
        # Проверяем соответствие формации
        structure = FORMATION_STRUCTURE[self.formation]
        for position_str, count in structure.items():
            position = Position(position_str)
            pos_players = [p for p in selected if p.position == position]
            if len(pos_players) != count:
                return False
        
        for p in selected:
            p.is_on_field = True
        return True

    def calculate_stats(self) -> TeamStats:
        """Пересчитать суммарную статистику (все 16 игроков)"""
        self.stats = TeamStats(
            total_saves=sum(p.stats.saves for p in self.players),
            total_passes=sum(p.stats.passes for p in self.players),
            total_goals=sum(p.stats.goals for p in self.players)
        )
        return self.stats
