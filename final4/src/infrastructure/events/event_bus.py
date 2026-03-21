# src/infrastructure/events/event_bus.py
"""Внутренняя шина событий"""

from typing import Callable, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Базовое событие"""
    event_type: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: Dict[str, Any] = field(default_factory=dict)


class MatchCreatedEvent(Event):
    """Событие создания матча"""
    def __init__(self, match_id: UUID, manager_id: UUID, platform: str):
        super().__init__(
            event_type='match_created',
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id),
                'platform': platform
            }
        )


class MatchJoinedEvent(Event):
    """Событие присоединения к матчу"""
    def __init__(self, match_id: UUID, manager_id: UUID):
        super().__init__(
            event_type='match_joined',
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id)
            }
        )


class MatchStartedEvent(Event):
    """Событие начала матча"""
    def __init__(self, match_id: UUID, manager1_id: UUID, manager2_id: UUID):
        super().__init__(
            event_type='match_started',
            data={
                'match_id': str(match_id),
                'manager1_id': str(manager1_id),
                'manager2_id': str(manager2_id)
            }
        )


class BetPlacedEvent(Event):
    """Событие размещения ставки"""
    def __init__(self, match_id: UUID, manager_id: UUID, bet_id: UUID, player_id: UUID):
        super().__init__(
            event_type='bet_placed',
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id),
                'bet_id': str(bet_id),
                'player_id': str(player_id)
            }
        )


class DiceRolledEvent(Event):
    """Событие броска кубика"""
    def __init__(self, match_id: UUID, manager_id: UUID, dice_value: int, won_bets_count: int):
        super().__init__(
            event_type='dice_rolled',
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id),
                'dice_value': dice_value,
                'won_bets_count': won_bets_count
            }
        )


class CardDrawnEvent(Event):
    """Событие вытягивания карточки"""
    def __init__(self, match_id: UUID, manager_id: UUID, card_type: str):
        super().__init__(
            event_type='card_drawn',
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id),
                'card_type': card_type
            }
        )


class TurnCompletedEvent(Event):
    """Событие завершения хода"""
    def __init__(self, match_id: UUID, manager_id: UUID, turn_number: int):
        super().__init__(
            event_type='turn_completed',
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id),
                'turn_number': turn_number
            }
        )


class MatchFinishedEvent(Event):
    """Событие завершения матча"""
    def __init__(
        self,
        match_id: UUID,
        winner_id: UUID,
        loser_id: UUID,
        score: str,
        decided_by: str
    ):
        super().__init__(
            event_type='match_finished',
            data={
                'match_id': str(match_id),
                'winner_id': str(winner_id),
                'loser_id': str(loser_id),
                'score': score,
                'decided_by': decided_by
            }
        )


class EventBus:
    """Внутренняя шина событий (in-memory pub/sub)"""
    
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._all_handlers: List[Callable] = []  # Обработчики всех событий
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Подписаться на конкретный тип события"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def subscribe_all(self, handler: Callable) -> None:
        """Подписаться на все события"""
        self._all_handlers.append(handler)
    
    async def publish(self, event: Event) -> None:
        """Опубликовать событие"""
        handlers = self._handlers.get(event.event_type, []) + self._all_handlers
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in event handler for {event.event_type}: {e}")
    
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Отписаться от события"""
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
    
    def clear(self) -> None:
        """Очистить все подписки"""
        self._handlers.clear()
        self._all_handlers.clear()


# Глобальный экземпляр
event_bus = EventBus()
