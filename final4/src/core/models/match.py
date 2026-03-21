# src/core/models/match.py
"""Модель матча"""

from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from .team import Team
from .bet import Bet
from .whistle_card import WhistleCard


class MatchStatus(str, Enum):
    WAITING_FOR_OPPONENT = "waiting_for_opponent"
    SETTING_LINEUP = "setting_lineup"
    IN_PROGRESS = "in_progress"
    EXTRA_TIME = "extra_time"
    PENALTIES = "penalties"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class MatchType(str, Enum):
    RANDOM = "random"
    VS_BOT = "vs_bot"
    TOURNAMENT = "tournament"


class MatchPhase(str, Enum):
    MAIN_TIME = "main_time"
    EXTRA_TIME = "extra_time"
    PENALTIES = "penalties"


class TurnState(BaseModel):
    """Состояние текущего хода"""
    turn_number: int = Field(ge=1)
    current_manager_id: UUID
    player_being_bet_on: Optional[UUID] = None
    bets_placed: List[UUID] = Field(default_factory=list)
    dice_rolled: bool = Field(default=False)
    dice_value: Optional[int] = Field(default=None, ge=1, le=6)
    card_drawn: bool = Field(default=False)
    card_id: Optional[UUID] = None
    card_applied: bool = Field(default=False)
    waiting_for_penalty_roll: bool = Field(default=False)


class MatchScore(BaseModel):
    """Счёт матча"""
    manager1_goals: int = Field(default=0, ge=0)
    manager2_goals: int = Field(default=0, ge=0)


class MatchResult(BaseModel):
    """Результат матча"""
    winner_id: Optional[UUID] = None
    loser_id: Optional[UUID] = None
    final_score: MatchScore = Field(default_factory=MatchScore)
    decided_by: MatchPhase = Field(default=MatchPhase.MAIN_TIME)
    decided_by_lottery: bool = Field(default=False)


class Match(BaseModel):
    """Матч между двумя менеджерами"""
    id: UUID = Field(default_factory=uuid4)
    match_type: MatchType
    status: MatchStatus = Field(default=MatchStatus.WAITING_FOR_OPPONENT)
    phase: MatchPhase = Field(default=MatchPhase.MAIN_TIME)
    
    # Участники
    manager1_id: UUID
    manager2_id: Optional[UUID] = None
    team1: Optional[Team] = None
    team2: Optional[Team] = None
    
    # Ход игры
    current_turn: Optional[TurnState] = None
    total_turns_main: int = Field(default=0)
    total_turns_extra: int = Field(default=0)
    
    # Ставки и карточки
    bets: List[Bet] = Field(default_factory=list)
    whistle_cards_drawn: List[WhistleCard] = Field(default_factory=list)
    whistle_deck: List[WhistleCard] = Field(default_factory=list)
    
    # Результат
    score: MatchScore = Field(default_factory=MatchScore)
    result: Optional[MatchResult] = None
    
    # Метаданные
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    platform: str = Field(default="telegram")

    def is_manager_turn(self, manager_id: UUID) -> bool:
        """Проверить, ход ли этого менеджера"""
        return self.current_turn is not None and self.current_turn.current_manager_id == manager_id

    def get_opponent_id(self, manager_id: UUID) -> Optional[UUID]:
        """Получить ID соперника"""
        if manager_id == self.manager1_id:
            return self.manager2_id
        elif manager_id == self.manager2_id:
            return self.manager1_id
        return None

    def get_team(self, manager_id: UUID) -> Optional[Team]:
        """Получить команду менеджера"""
        if manager_id == self.manager1_id:
            return self.team1
        elif manager_id == self.manager2_id:
            return self.team2
        return None

    def get_opponent_team(self, manager_id: UUID) -> Optional[Team]:
        """Получить команду соперника"""
        opponent_id = self.get_opponent_id(manager_id)
        return self.get_team(opponent_id) if opponent_id else None

    def is_participant(self, manager_id: UUID) -> bool:
        """Проверить, участвует ли менеджер в матче"""
        return manager_id == self.manager1_id or manager_id == self.manager2_id

    def get_turn_bets(self) -> List[Bet]:
        """Получить ставки текущего хода"""
        if not self.current_turn:
            return []
        return [b for b in self.bets if b.id in self.current_turn.bets_placed]

    def add_bet(self, bet: Bet) -> None:
        """Добавить ставку"""
        self.bets.append(bet)
        if self.current_turn:
            self.current_turn.bets_placed.append(bet.id)
