# src/infrastructure/repositories/user_repository.py
"""Реализация репозитория пользователей"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.user import User, UserPlan, PlatformIds, UserStats, DailyLimits
from src.core.interfaces.repositories import IUserRepository
from ..db.models import UserModel


class UserRepository(IUserRepository):
    """PostgreSQL репозиторий пользователей"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Получить пользователя по ID"""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Получить пользователя по Telegram ID"""
        result = await self.session.execute(
            select(UserModel).where(UserModel.telegram_id == telegram_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def get_by_vk_id(self, vk_id: int) -> Optional[User]:
        """Получить пользователя по VK ID"""
        result = await self.session.execute(
            select(UserModel).where(UserModel.vk_id == vk_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def get_by_discord_id(self, discord_id: int) -> Optional[User]:
        """Получить пользователя по Discord ID"""
        result = await self.session.execute(
            select(UserModel).where(UserModel.discord_id == discord_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def create(self, user: User) -> User:
        """Создать пользователя"""
        model = self._to_model(user)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_domain(model)
    
    async def update(self, user: User) -> User:
        """Обновить пользователя"""
        await self.session.execute(
            update(UserModel)
            .where(UserModel.id == user.id)
            .values(
                username=user.username,
                telegram_id=user.platform_ids.telegram_id,
                vk_id=user.platform_ids.vk_id,
                discord_id=user.platform_ids.discord_id,
                plan=user.plan.value,
                plan_expires_at=user.plan_expires_at,
                matches_played=user.stats.matches_played,
                matches_won=user.stats.matches_won,
                matches_lost=user.stats.matches_lost,
                matches_draw=user.stats.matches_draw,
                tournaments_won=user.stats.tournaments_won,
                goals_scored=user.stats.goals_scored,
                goals_conceded=user.stats.goals_conceded,
                win_streak=user.stats.win_streak,
                best_win_streak=user.stats.best_win_streak,
                rating=user.rating,
                matches_today=user.daily_limits.matches_today,
                last_match_date=user.daily_limits.last_match_date,
                last_active_at=datetime.now(timezone.utc),
                is_banned=user.is_banned,
                ban_reason=user.ban_reason
            )
        )
        await self.session.flush()
        return user
    
    async def get_leaderboard(self, limit: int = 100) -> List[User]:
        """Получить таблицу лидеров по рейтингу"""
        result = await self.session.execute(
            select(UserModel)
            .where(UserModel.is_banned.is_(False))
            .order_by(desc(UserModel.rating))
            .limit(limit)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]
    
    async def update_last_active(self, user_id: UUID) -> None:
        """Обновить время последней активности"""
        await self.session.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(last_active_at=datetime.now(timezone.utc))
        )
        await self.session.flush()
    
    def _to_domain(self, model: UserModel) -> User:
        """Преобразовать модель БД в доменную модель"""
        return User(
            id=model.id,
            username=model.username,
            platform_ids=PlatformIds(
                telegram_id=model.telegram_id,
                vk_id=model.vk_id,
                discord_id=model.discord_id
            ),
            plan=UserPlan(model.plan),
            plan_expires_at=model.plan_expires_at,
            stats=UserStats(
                matches_played=model.matches_played,
                matches_won=model.matches_won,
                matches_lost=model.matches_lost,
                matches_draw=model.matches_draw,
                tournaments_won=model.tournaments_won,
                goals_scored=model.goals_scored,
                goals_conceded=model.goals_conceded,
                win_streak=model.win_streak,
                best_win_streak=model.best_win_streak
            ),
            daily_limits=DailyLimits(
                matches_today=model.matches_today,
                last_match_date=model.last_match_date
            ),
            rating=model.rating,
            created_at=model.created_at,
            last_active_at=model.last_active_at,
            is_banned=model.is_banned,
            ban_reason=model.ban_reason
        )
    
    def _to_model(self, user: User) -> UserModel:
        """Преобразовать доменную модель в модель БД"""
        return UserModel(
            id=user.id,
            username=user.username,
            telegram_id=user.platform_ids.telegram_id,
            vk_id=user.platform_ids.vk_id,
            discord_id=user.platform_ids.discord_id,
            plan=user.plan.value,
            plan_expires_at=user.plan_expires_at,
            matches_played=user.stats.matches_played,
            matches_won=user.stats.matches_won,
            matches_lost=user.stats.matches_lost,
            matches_draw=user.stats.matches_draw,
            tournaments_won=user.stats.tournaments_won,
            goals_scored=user.stats.goals_scored,
            goals_conceded=user.stats.goals_conceded,
            win_streak=user.stats.win_streak,
            best_win_streak=user.stats.best_win_streak,
            rating=user.rating,
            matches_today=user.daily_limits.matches_today,
            last_match_date=user.daily_limits.last_match_date,
            created_at=user.created_at,
            last_active_at=user.last_active_at,
            is_banned=user.is_banned,
            ban_reason=user.ban_reason
        )
