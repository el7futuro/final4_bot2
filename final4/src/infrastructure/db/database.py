# src/infrastructure/db/database.py
"""Подключение к базе данных"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)


class Database:
    """Управление подключением к PostgreSQL"""
    
    def __init__(self, url: str = None):
        self.url = url or os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://final4:final4_password@localhost:5432/final4"
        )
        self.engine = create_async_engine(
            self.url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Контекстный менеджер для сессии"""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    async def close(self) -> None:
        """Закрыть все соединения"""
        await self.engine.dispose()


# Глобальный экземпляр БД
db = Database()
