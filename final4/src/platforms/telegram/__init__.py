# src/platforms/telegram/__init__.py
"""Telegram platform adapter"""

from .bot import Final4Bot, create_bot, get_bot

__all__ = [
    "Final4Bot",
    "create_bot",
    "get_bot",
]
