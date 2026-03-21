#!/usr/bin/env python3
"""Точка входа для Telegram бота Final 4"""

import asyncio
import logging
import os
import sys

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.platforms.telegram import create_bot


def setup_logging():
    """Настройка логирования"""
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Уменьшаем вывод от aiogram
    logging.getLogger("aiogram").setLevel(logging.WARNING)


async def main():
    """Главная функция"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Запуск Final 4 Telegram бота...")
    
    try:
        bot = create_bot()
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        raise
    finally:
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
