# src/core/__init__.py
"""
Final 4 Core Module

Чистая бизнес-логика без зависимостей от фреймворков.
НЕ импортирует: aiogram, vkbottle, discord, sqlalchemy
"""

from .models.player import Player, Position, PlayerStats
from .models.team import Team, Formation, TeamStats
from .models.bet import Bet, BetType, BetOutcome, EvenOddChoice, HighLowChoice
from .models.whistle_card import WhistleCard, CardType, CardEffect
from .models.match import Match, MatchStatus, MatchType, MatchPhase, TurnState, MatchScore, MatchResult
from .models.user import User, UserPlan, UserStats, PlatformIds
from .engine import GameEngine, BOT_USER_ID
from .ai import Final4BotAI

__all__ = [
    # Models
    "Player", "Position", "PlayerStats",
    "Team", "Formation", "TeamStats",
    "Bet", "BetType", "BetOutcome", "EvenOddChoice", "HighLowChoice",
    "WhistleCard", "CardType", "CardEffect",
    "Match", "MatchStatus", "MatchType", "MatchPhase", "TurnState", "MatchScore", "MatchResult",
    "User", "UserPlan", "UserStats", "PlatformIds",
    # Engine
    "GameEngine", "BOT_USER_ID",
    # AI
    "Final4BotAI",
]
