# src/core/models/user.py
"""Модель пользователя"""

from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field


class UserPlan(str, Enum):
    FREE = "free"
    PREMIUM = "premium"
    PRO = "pro"


class PlatformIds(BaseModel):
    """ID пользователя на разных платформах"""
    telegram_id: Optional[int] = None
    vk_id: Optional[int] = None
    discord_id: Optional[int] = None


class UserStats(BaseModel):
    """Статистика пользователя"""
    matches_played: int = Field(default=0, ge=0)
    matches_won: int = Field(default=0, ge=0)
    matches_lost: int = Field(default=0, ge=0)
    matches_draw: int = Field(default=0, ge=0)
    tournaments_won: int = Field(default=0, ge=0)
    goals_scored: int = Field(default=0, ge=0)
    goals_conceded: int = Field(default=0, ge=0)
    win_streak: int = Field(default=0, ge=0)
    best_win_streak: int = Field(default=0, ge=0)


class DailyLimits(BaseModel):
    """Дневные лимиты"""
    matches_today: int = Field(default=0, ge=0)
    last_match_date: Optional[date] = None


class User(BaseModel):
    """Пользователь системы"""
    id: UUID = Field(default_factory=uuid4)
    username: str = Field(min_length=1, max_length=50)
    platform_ids: PlatformIds = Field(default_factory=PlatformIds)
    
    plan: UserPlan = Field(default=UserPlan.FREE)
    plan_expires_at: Optional[datetime] = None
    
    stats: UserStats = Field(default_factory=UserStats)
    daily_limits: DailyLimits = Field(default_factory=DailyLimits)
    
    rating: int = Field(default=1000, ge=0)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active_at: datetime = Field(default_factory=datetime.utcnow)
    is_banned: bool = Field(default=False)
    ban_reason: Optional[str] = None

    def can_play_match(self) -> bool:
        """Проверить, может ли играть (лимиты)"""
        if self.is_banned:
            return False
        
        # Сбросить лимиты если новый день
        today = date.today()
        if self.daily_limits.last_match_date != today:
            self.daily_limits.matches_today = 0
            self.daily_limits.last_match_date = today
        
        # Лимиты по плану
        limits = {
            UserPlan.FREE: 3,
            UserPlan.PREMIUM: 10,
            UserPlan.PRO: 999,
        }
        max_matches = limits.get(self.plan, 3)
        
        return self.daily_limits.matches_today < max_matches

    def increment_daily_matches(self) -> None:
        """Увеличить счётчик матчей за день"""
        today = date.today()
        if self.daily_limits.last_match_date != today:
            self.daily_limits.matches_today = 0
        self.daily_limits.matches_today += 1
        self.daily_limits.last_match_date = today

    def update_stats_after_match(self, won: bool, goals_scored: int, goals_conceded: int) -> None:
        """Обновить статистику после матча"""
        self.stats.matches_played += 1
        self.stats.goals_scored += goals_scored
        self.stats.goals_conceded += goals_conceded
        
        if won:
            self.stats.matches_won += 1
            self.stats.win_streak += 1
            self.stats.best_win_streak = max(self.stats.best_win_streak, self.stats.win_streak)
        else:
            self.stats.matches_lost += 1
            self.stats.win_streak = 0

    def get_win_rate(self) -> float:
        """Получить процент побед"""
        if self.stats.matches_played == 0:
            return 0.0
        return self.stats.matches_won / self.stats.matches_played * 100
