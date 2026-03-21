# src/core/interfaces/repositories.py
"""Интерфейсы репозиториев"""

from abc import ABC, abstractmethod
from uuid import UUID
from typing import List, Optional
from datetime import datetime

from ..models.user import User
from ..models.match import Match, MatchStatus
from ..models.team import Team
from ..models.bet import Bet


class IUserRepository(ABC):
    """Интерфейс репозитория пользователей"""
    
    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Получить пользователя по ID"""
        pass
    
    @abstractmethod
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Получить пользователя по Telegram ID"""
        pass
    
    @abstractmethod
    async def get_by_vk_id(self, vk_id: int) -> Optional[User]:
        """Получить пользователя по VK ID"""
        pass
    
    @abstractmethod
    async def get_by_discord_id(self, discord_id: int) -> Optional[User]:
        """Получить пользователя по Discord ID"""
        pass
    
    @abstractmethod
    async def create(self, user: User) -> User:
        """Создать пользователя"""
        pass
    
    @abstractmethod
    async def update(self, user: User) -> User:
        """Обновить пользователя"""
        pass
    
    @abstractmethod
    async def get_leaderboard(self, limit: int = 100) -> List[User]:
        """Получить таблицу лидеров"""
        pass


class ITeamRepository(ABC):
    """Интерфейс репозитория команд"""
    
    @abstractmethod
    async def get_by_id(self, team_id: UUID) -> Optional[Team]:
        """Получить команду по ID"""
        pass
    
    @abstractmethod
    async def get_by_user_id(self, user_id: UUID) -> Optional[Team]:
        """Получить команду пользователя"""
        pass
    
    @abstractmethod
    async def create(self, team: Team) -> Team:
        """Создать команду"""
        pass
    
    @abstractmethod
    async def update(self, team: Team) -> Team:
        """Обновить команду"""
        pass
    
    @abstractmethod
    async def create_default_team(self, user_id: UUID, team_name: str) -> Team:
        """Создать команду с дефолтными игроками"""
        pass


class IMatchRepository(ABC):
    """Интерфейс репозитория матчей"""
    
    @abstractmethod
    async def get_by_id(self, match_id: UUID) -> Optional[Match]:
        """Получить матч по ID"""
        pass
    
    @abstractmethod
    async def create(self, match: Match) -> Match:
        """Создать матч"""
        pass
    
    @abstractmethod
    async def update(self, match: Match) -> Match:
        """Обновить матч"""
        pass
    
    @abstractmethod
    async def get_waiting_matches(self, platform: str) -> List[Match]:
        """Получить ожидающие матчи"""
        pass
    
    @abstractmethod
    async def get_user_active_match(self, user_id: UUID) -> Optional[Match]:
        """Получить активный матч пользователя"""
        pass
    
    @abstractmethod
    async def get_user_matches(
        self,
        user_id: UUID,
        status: Optional[MatchStatus] = None,
        limit: int = 10
    ) -> List[Match]:
        """Получить матчи пользователя"""
        pass
    
    @abstractmethod
    async def get_user_match_history(
        self,
        user_id: UUID,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Match]:
        """Получить историю матчей"""
        pass


class IBetRepository(ABC):
    """Интерфейс репозитория ставок"""
    
    @abstractmethod
    async def get_by_id(self, bet_id: UUID) -> Optional[Bet]:
        """Получить ставку по ID"""
        pass
    
    @abstractmethod
    async def create(self, bet: Bet) -> Bet:
        """Создать ставку"""
        pass
    
    @abstractmethod
    async def get_match_bets(self, match_id: UUID) -> List[Bet]:
        """Получить ставки матча"""
        pass
    
    @abstractmethod
    async def get_user_bets_in_match(self, match_id: UUID, user_id: UUID) -> List[Bet]:
        """Получить ставки пользователя в матче"""
        pass
