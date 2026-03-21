# src/infrastructure/cache/redis_client.py
"""Клиент Redis"""

import os
import json
from typing import Optional, Any

import redis.asyncio as redis


class RedisClient:
    """Асинхронный клиент Redis"""
    
    def __init__(self, url: str = None):
        self.url = url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._redis: Optional[redis.Redis] = None
    
    async def connect(self) -> None:
        """Установить соединение"""
        if self._redis is None:
            self._redis = redis.from_url(self.url, decode_responses=True)
    
    @property
    def redis(self) -> redis.Redis:
        """Получить клиент Redis"""
        if self._redis is None:
            self._redis = redis.from_url(self.url, decode_responses=True)
        return self._redis
    
    async def get(self, key: str) -> Optional[str]:
        """Получить значение по ключу"""
        return await self.redis.get(key)
    
    async def set(
        self,
        key: str,
        value: str,
        expire: Optional[int] = None
    ) -> None:
        """Установить значение"""
        if expire:
            await self.redis.setex(key, expire, value)
        else:
            await self.redis.set(key, value)
    
    async def delete(self, key: str) -> None:
        """Удалить ключ"""
        await self.redis.delete(key)
    
    async def exists(self, key: str) -> bool:
        """Проверить существование ключа"""
        return await self.redis.exists(key) > 0
    
    async def get_json(self, key: str) -> Optional[dict]:
        """Получить JSON по ключу"""
        data = await self.get(key)
        return json.loads(data) if data else None
    
    async def set_json(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None
    ) -> None:
        """Установить JSON значение"""
        await self.set(key, json.dumps(value, default=str), expire)
    
    async def incr(self, key: str) -> int:
        """Инкремент ключа"""
        return await self.redis.incr(key)
    
    async def expire(self, key: str, seconds: int) -> None:
        """Установить TTL для ключа"""
        await self.redis.expire(key, seconds)
    
    async def close(self) -> None:
        """Закрыть соединение"""
        if self._redis:
            await self._redis.close()
            self._redis = None


# Глобальный экземпляр
redis_client = RedisClient()
