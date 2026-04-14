# src/platforms/telegram/bot.py
"""Инициализация Telegram бота (MVP без PostgreSQL/Redis)"""

import os
import logging
import asyncio
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

logger = logging.getLogger(__name__)


class Final4Bot:
    """Главный класс Telegram бота Final 4"""
    
    def __init__(self, token: str = None):
        self.token = token or os.environ.get("BOT_TOKEN")
        if not self.token:
            raise ValueError("BOT_TOKEN не установлен")
        
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
        from .handlers.game import router as game_router
        
        self.dp.include_router(start_router)
        self.dp.include_router(match_router)
        self.dp.include_router(game_router)
    
    async def start(self) -> None:
        """Запустить бота"""
        logger.info("Запуск Final 4 Telegram бота...")
        
        # Инициализируем БД
        from .storage import get_storage
        storage = get_storage()
        await storage.init_db()
        
        # Устанавливаем команды бота (кнопка Меню в Telegram)
        from aiogram.types import BotCommand
        await self.bot.set_my_commands([
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="menu", description="Главное меню"),
        ])
        
        # Запуск polling
        await self.dp.start_polling(
            self.bot,
            allowed_updates=self.dp.resolve_used_update_types()
        )
    
    async def stop(self) -> None:
        """Остановить бота"""
        logger.info("Остановка бота...")
        from .storage import get_storage
        storage = get_storage()
        await storage.close()
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


async def main():
    """Точка входа"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    bot = create_bot()
    
    try:
        await bot.start()
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
