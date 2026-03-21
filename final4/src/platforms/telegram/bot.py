# src/platforms/telegram/bot.py
"""Инициализация Telegram бота"""

import os
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from src.infrastructure.db.database import Database
from src.infrastructure.cache.redis_client import RedisClient
from src.infrastructure.events.event_bus import EventBus

logger = logging.getLogger(__name__)


class Final4Bot:
    """Главный класс Telegram бота Final 4"""
    
    def __init__(
        self,
        token: str = None,
        database: Database = None,
        redis: RedisClient = None,
        event_bus: EventBus = None
    ):
        self.token = token or os.environ.get("BOT_TOKEN")
        if not self.token:
            raise ValueError("BOT_TOKEN не установлен")
        
        # Инфраструктура
        self.database = database or Database()
        self.redis = redis or RedisClient()
        self.event_bus = event_bus or EventBus()
        
        # Aiogram
        self.bot = Bot(
            token=self.token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        
        # Регистрируем роутеры
        self._setup_routers()
    
    def _setup_routers(self) -> None:
        """Настроить роутеры (handlers)"""
        from .handlers.start import router as start_router
        from .handlers.match import router as match_router
        from .handlers.profile import router as profile_router
        from .handlers.game import router as game_router
        
        self.dp.include_router(start_router)
        self.dp.include_router(match_router)
        self.dp.include_router(profile_router)
        self.dp.include_router(game_router)
    
    async def start(self) -> None:
        """Запустить бота"""
        logger.info("Запуск Final 4 Telegram бота...")
        
        # Подключаем Redis
        await self.redis.connect()
        
        # Запуск polling
        await self.dp.start_polling(
            self.bot,
            allowed_updates=self.dp.resolve_used_update_types()
        )
    
    async def stop(self) -> None:
        """Остановить бота"""
        logger.info("Остановка бота...")
        await self.redis.close()
        await self.database.close()
        await self.bot.session.close()


# Фабрика для создания бота
def create_bot() -> Final4Bot:
    """Создать экземпляр бота"""
    return Final4Bot()


# Глобальный экземпляр (для хендлеров)
_bot_instance: Optional[Final4Bot] = None


def get_bot() -> Final4Bot:
    """Получить глобальный экземпляр бота"""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = create_bot()
    return _bot_instance
