# src/core/interfaces/__init__.py
"""Core interfaces"""

from .repositories import (
    IUserRepository,
    ITeamRepository,
    IMatchRepository,
    IBetRepository
)

__all__ = [
    "IUserRepository",
    "ITeamRepository",
    "IMatchRepository",
    "IBetRepository",
]
