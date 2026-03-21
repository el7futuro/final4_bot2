# src/application/services/user_service.py
"""Сервис работы с пользователями"""

from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from src.core.models.user import User, PlatformIds
from src.core.interfaces.repositories import IUserRepository, ITeamRepository


class UserService:
    """Сервис управления пользователями"""
    
    def __init__(
        self,
        user_repo: IUserRepository,
        team_repo: ITeamRepository
    ):
        self.user_repo = user_repo
        self.team_repo = team_repo
    
    async def get_or_create_telegram_user(
        self,
        telegram_id: int,
        username: str
    ) -> User:
        """
        Получить или создать пользователя Telegram.
        При создании автоматически создаётся команда.
        """
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        
        if user:
            # Обновляем время активности
            user.last_active_at = datetime.now(timezone.utc)
            await self.user_repo.update(user)
            return user
        
        # Создаём нового пользователя
        user = User(
            username=username or f"user_{telegram_id}",
            platform_ids=PlatformIds(telegram_id=telegram_id),
            created_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc)
        )
        user = await self.user_repo.create(user)
        
        # Создаём дефолтную команду
        await self.team_repo.create_default_team(
            user_id=user.id,
            team_name=f"Команда {username or telegram_id}"
        )
        
        return user
    
    async def get_or_create_vk_user(
        self,
        vk_id: int,
        username: str
    ) -> User:
        """Получить или создать пользователя VK"""
        user = await self.user_repo.get_by_vk_id(vk_id)
        
        if user:
            user.last_active_at = datetime.now(timezone.utc)
            await self.user_repo.update(user)
            return user
        
        user = User(
            username=username or f"vk_user_{vk_id}",
            platform_ids=PlatformIds(vk_id=vk_id),
            created_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc)
        )
        user = await self.user_repo.create(user)
        
        await self.team_repo.create_default_team(
            user_id=user.id,
            team_name=f"Команда {username or vk_id}"
        )
        
        return user
    
    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Получить пользователя по ID"""
        return await self.user_repo.get_by_id(user_id)
    
    async def get_user_team(self, user_id: UUID):
        """Получить команду пользователя"""
        return await self.team_repo.get_by_user_id(user_id)
    
    async def update_user_stats_after_match(
        self,
        user_id: UUID,
        won: bool,
        goals_scored: int,
        goals_conceded: int
    ) -> User:
        """Обновить статистику пользователя после матча"""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError(f"Пользователь {user_id} не найден")
        
        user.update_stats_after_match(won, goals_scored, goals_conceded)
        user.increment_daily_matches()
        
        # Обновляем рейтинг (простая формула)
        if won:
            user.rating += 25
        else:
            user.rating = max(0, user.rating - 15)
        
        return await self.user_repo.update(user)
    
    async def get_leaderboard(self, limit: int = 100):
        """Получить таблицу лидеров"""
        return await self.user_repo.get_leaderboard(limit)
    
    async def can_user_play(self, user_id: UUID) -> tuple[bool, str]:
        """
        Проверить, может ли пользователь играть.
        
        Returns:
            (can_play, reason)
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return False, "Пользователь не найден"
        
        if user.is_banned:
            return False, f"Вы заблокированы: {user.ban_reason or 'причина не указана'}"
        
        if not user.can_play_match():
            return False, "Достигнут дневной лимит матчей. Обновите подписку для увеличения лимита."
        
        return True, "OK"
