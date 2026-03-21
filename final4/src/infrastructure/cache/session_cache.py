# src/infrastructure/cache/session_cache.py
"""Кэш сессий пользователей"""

from typing import Optional
from uuid import UUID

from .redis_client import RedisClient


class SessionCache:
    """Кэш активных сессий и состояний пользователей"""
    
    PREFIX = "session:"
    TTL = 3600 * 24  # 24 часа
    
    def __init__(self, redis: RedisClient):
        self.redis = redis
    
    def _key(self, user_id: UUID, suffix: str = "") -> str:
        """Сформировать ключ"""
        key = f"{self.PREFIX}{user_id}"
        if suffix:
            key = f"{key}:{suffix}"
        return key
    
    async def get_active_match(self, user_id: UUID) -> Optional[UUID]:
        """Получить ID активного матча пользователя"""
        data = await self.redis.get_json(self._key(user_id))
        if data and data.get("active_match_id"):
            return UUID(data["active_match_id"])
        return None
    
    async def set_active_match(self, user_id: UUID, match_id: UUID) -> None:
        """Установить активный матч"""
        await self.redis.set_json(
            self._key(user_id),
            {"active_match_id": str(match_id)},
            self.TTL
        )
    
    async def clear_active_match(self, user_id: UUID) -> None:
        """Очистить активный матч"""
        await self.redis.delete(self._key(user_id))
    
    async def get_user_state(self, user_id: UUID) -> Optional[dict]:
        """Получить состояние пользователя (для FSM)"""
        return await self.redis.get_json(self._key(user_id, "state"))
    
    async def set_user_state(self, user_id: UUID, state: dict) -> None:
        """Установить состояние пользователя"""
        await self.redis.set_json(
            self._key(user_id, "state"),
            state,
            self.TTL
        )
    
    async def clear_user_state(self, user_id: UUID) -> None:
        """Очистить состояние"""
        await self.redis.delete(self._key(user_id, "state"))
    
    async def set_temp_data(
        self,
        user_id: UUID,
        key: str,
        data: dict,
        ttl: int = 300
    ) -> None:
        """Установить временные данные (5 мин по умолчанию)"""
        await self.redis.set_json(
            self._key(user_id, f"temp:{key}"),
            data,
            ttl
        )
    
    async def get_temp_data(self, user_id: UUID, key: str) -> Optional[dict]:
        """Получить временные данные"""
        return await self.redis.get_json(self._key(user_id, f"temp:{key}"))
