# src/infrastructure/cache/rate_limiter.py
"""Rate limiting через Redis"""

from .redis_client import RedisClient


class RateLimiter:
    """Rate limiter для защиты от спама"""
    
    PREFIX = "ratelimit:"
    
    def __init__(self, redis: RedisClient):
        self.redis = redis
    
    async def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        """
        Проверить, разрешён ли запрос.
        
        Args:
            key: Уникальный ключ (например, user_id или ip)
            max_requests: Максимум запросов в окне
            window_seconds: Размер окна в секундах
            
        Returns:
            True если запрос разрешён
        """
        full_key = f"{self.PREFIX}{key}"
        
        current = await self.redis.incr(full_key)
        
        # Устанавливаем TTL только при первом запросе
        if current == 1:
            await self.redis.expire(full_key, window_seconds)
        
        return current <= max_requests
    
    async def get_remaining(
        self,
        key: str,
        max_requests: int
    ) -> int:
        """Получить оставшееся количество запросов"""
        full_key = f"{self.PREFIX}{key}"
        current = await self.redis.get(full_key)
        
        if current is None:
            return max_requests
        
        return max(0, max_requests - int(current))
    
    async def reset(self, key: str) -> None:
        """Сбросить счётчик"""
        await self.redis.delete(f"{self.PREFIX}{key}")


# Предустановленные лимиты
class RateLimits:
    """Стандартные лимиты"""
    
    # Команды бота
    COMMANDS_PER_MINUTE = (30, 60)  # 30 команд в минуту
    
    # Создание матчей
    MATCH_CREATE_PER_HOUR = (10, 3600)  # 10 матчей в час
    
    # Ставки
    BETS_PER_MINUTE = (60, 60)  # 60 ставок в минуту
