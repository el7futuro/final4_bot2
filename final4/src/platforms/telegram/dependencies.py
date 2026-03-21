# src/platforms/telegram/dependencies.py
"""Зависимости для хендлеров"""

from src.infrastructure.db.database import Database
from src.infrastructure.repositories import UserRepository, TeamRepository, MatchRepository
from src.infrastructure.events.event_bus import EventBus
from src.application.services import UserService, MatchService

# Глобальные экземпляры
_db: Database = None
_event_bus: EventBus = None


def get_database() -> Database:
    """Получить экземпляр БД"""
    global _db
    if _db is None:
        _db = Database()
    return _db


def get_event_bus() -> EventBus:
    """Получить шину событий"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


async def get_user_service() -> UserService:
    """Получить сервис пользователей"""
    db = get_database()
    async with db.session() as session:
        user_repo = UserRepository(session)
        team_repo = TeamRepository(session)
        return UserService(user_repo, team_repo)


async def get_match_service() -> MatchService:
    """Получить сервис матчей"""
    db = get_database()
    event_bus = get_event_bus()
    async with db.session() as session:
        match_repo = MatchRepository(session)
        team_repo = TeamRepository(session)
        user_repo = UserRepository(session)
        return MatchService(match_repo, team_repo, user_repo, event_bus)
