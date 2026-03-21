# src/core/models/match.py
"""Модель матча"""

from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, List, Set
from pydantic import BaseModel, Field

from .team import Team
from .player import Position
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
    """
    Состояние текущего хода.
    
    ВАЖНО: В каждом ходу ОБА игрока делают ставки, затем ОДИН бросок кубика.
    """
    turn_number: int = Field(ge=1)
    
    # Ставки обоих игроков (ключ = manager_id как строка)
    # Каждый игрок делает 2 ставки на одного своего игрока (кроме хода 1 - вратарь 1 ставка)
    manager1_player_id: Optional[UUID] = None  # На кого ставит менеджер 1
    manager1_bets: List[UUID] = Field(default_factory=list)  # ID ставок менеджера 1
    manager1_ready: bool = Field(default=False)  # Менеджер 1 завершил ставки
    
    manager2_player_id: Optional[UUID] = None  # На кого ставит менеджер 2
    manager2_bets: List[UUID] = Field(default_factory=list)  # ID ставок менеджера 2
    manager2_ready: bool = Field(default=False)  # Менеджер 2 завершил ставки
    
    # Бросок кубика (один для обоих!)
    dice_rolled: bool = Field(default=False)
    dice_value: Optional[int] = Field(default=None, ge=1, le=6)
    
    # Карточки (каждый тянет свою при выигрыше)
    manager1_card_id: Optional[UUID] = None
    manager1_card_applied: bool = Field(default=False)
    manager2_card_id: Optional[UUID] = None
    manager2_card_applied: bool = Field(default=False)
    
    # Легаси поля для обратной совместимости
    current_manager_id: Optional[UUID] = None  # Deprecated, но оставляем
    bets_placed: List[UUID] = Field(default_factory=list)  # Все ставки хода
    card_drawn: bool = Field(default=False)
    card_id: Optional[UUID] = None
    card_applied: bool = Field(default=False)
    waiting_for_penalty_roll: bool = Field(default=False)
    
    def both_ready(self) -> bool:
        """Оба игрока сделали ставки"""
        return self.manager1_ready and self.manager2_ready
    
    def get_required_bets_count(self) -> int:
        """Сколько ставок требуется (1 для вратаря, 2 для полевых)"""
        return 1 if self.turn_number == 1 else 2


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
    
    # Отслеживание использованных игроков (по менеджерам)
    # Формат: {manager_id: set(player_ids)}
    used_players_main_m1: List[str] = Field(default_factory=list)  # UUID as str для сериализации
    used_players_main_m2: List[str] = Field(default_factory=list)
    used_players_extra_m1: List[str] = Field(default_factory=list)
    used_players_extra_m2: List[str] = Field(default_factory=list)
    
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
    
    # ========== Механизм использованных игроков ==========
    
    def get_used_players(self, manager_id: UUID) -> Set[UUID]:
        """Получить множество использованных игроков для менеджера"""
        if self.phase == MatchPhase.MAIN_TIME:
            if manager_id == self.manager1_id:
                return set(UUID(s) for s in self.used_players_main_m1)
            else:
                return set(UUID(s) for s in self.used_players_main_m2)
        else:
            # В дополнительное время учитываем И основное время
            if manager_id == self.manager1_id:
                main = set(UUID(s) for s in self.used_players_main_m1)
                extra = set(UUID(s) for s in self.used_players_extra_m1)
                return main | extra
            else:
                main = set(UUID(s) for s in self.used_players_main_m2)
                extra = set(UUID(s) for s in self.used_players_extra_m2)
                return main | extra
    
    def mark_player_used(self, manager_id: UUID, player_id: UUID) -> None:
        """Пометить игрока как использованного в текущей фазе"""
        player_str = str(player_id)
        
        if self.phase == MatchPhase.MAIN_TIME:
            if manager_id == self.manager1_id:
                if player_str not in self.used_players_main_m1:
                    self.used_players_main_m1.append(player_str)
            else:
                if player_str not in self.used_players_main_m2:
                    self.used_players_main_m2.append(player_str)
        else:
            if manager_id == self.manager1_id:
                if player_str not in self.used_players_extra_m1:
                    self.used_players_extra_m1.append(player_str)
            else:
                if player_str not in self.used_players_extra_m2:
                    self.used_players_extra_m2.append(player_str)
    
    def is_player_used(self, manager_id: UUID, player_id: UUID) -> bool:
        """Проверить, использован ли игрок"""
        return player_id in self.get_used_players(manager_id)
    
    def get_available_players_for_betting(self, manager_id: UUID) -> List:
        """
        Получить список доступных игроков для ставки в текущем ходе.
        
        Правила:
        - ВСЕ 16 игроков заявки доступны (не только 11 на поле!)
        - Ход 1: только вратарь
        - Ходы 2+: все кроме вратаря
        - Игрок уже использован в матче: недоступен
        """
        team = self.get_team(manager_id)
        if not team:
            return []
        
        turn_number = self.current_turn.turn_number if self.current_turn else 1
        used_players = self.get_used_players(manager_id)
        
        available = []
        # Используем ВСЮ команду (16 игроков), а не только field_players
        for player in team.players:
            # Игрок не доступен (удалён)
            if not player.is_available:
                continue
            
            # Игрок уже использован в этом матче
            if player.id in used_players:
                continue
            
            # Правило по номеру хода
            if turn_number == 1:
                # Первый ход — только вратарь
                if player.position != Position.GOALKEEPER:
                    continue
            else:
                # Ходы 2+ — все кроме вратаря
                if player.position == Position.GOALKEEPER:
                    continue
            
            available.append(player)
        
        return available
