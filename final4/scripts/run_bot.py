#!/usr/bin/env python3
"""Запуск Telegram бота Final 4"""

import sys
import os
import asyncio

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загружаем .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from src.platforms.telegram.bot import main

if __name__ == "__main__":
    asyncio.run(main())
