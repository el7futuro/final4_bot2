# src/infrastructure/repositories/__init__.py
"""Репозитории для работы с данными"""

from .user_repository import UserRepository
from .team_repository import TeamRepository
from .match_repository import MatchRepository

__all__ = [
    "UserRepository",
    "TeamRepository",
    "MatchRepository",
]
