# src/application/services/match_service.py
"""Сервис управления матчами"""

from typing import Optional, List, Tuple
from uuid import UUID

from src.core.models.match import Match, MatchType, MatchStatus
from src.core.models.team import Team, Formation
from src.core.models.bet import Bet, BetType
from src.core.models.whistle_card import WhistleCard
from src.core.engine.game_engine import GameEngine
from src.core.interfaces.repositories import IMatchRepository, ITeamRepository, IUserRepository

from src.infrastructure.events.event_bus import (
    EventBus, MatchCreatedEvent, MatchJoinedEvent,
    MatchStartedEvent, BetPlacedEvent, DiceRolledEvent,
    CardDrawnEvent, TurnCompletedEvent, MatchFinishedEvent
)


class MatchService:
    """Сервис управления матчами"""
    
    def __init__(
        self,
        match_repo: IMatchRepository,
        team_repo: ITeamRepository,
        user_repo: IUserRepository,
        event_bus: EventBus,
        game_engine: GameEngine = None
    ):
        self.match_repo = match_repo
        self.team_repo = team_repo
        self.user_repo = user_repo
        self.event_bus = event_bus
        self.engine = game_engine or GameEngine()
    
    async def create_match(
        self,
        manager_id: UUID,
        match_type: MatchType,
        platform: str = "telegram"
    ) -> Match:
        """Создать новый матч"""
        # Проверяем, нет ли уже активного матча
        active = await self.match_repo.get_user_active_match(manager_id)
        if active:
            raise ValueError("У вас уже есть активный матч")
        
        # Создаём матч через движок
        match = self.engine.create_match(manager_id, match_type, platform)
        match = await self.match_repo.create(match)
        
        # Публикуем событие
        await self.event_bus.publish(
            MatchCreatedEvent(match.id, manager_id, platform)
        )
        
        return match
    
    async def find_or_create_random_match(
        self,
        manager_id: UUID,
        platform: str = "telegram"
    ) -> Tuple[Match, bool]:
        """
        Найти существующий матч или создать новый.
        
        Returns:
            (match, is_new) - матч и флаг, создан ли он
        """
        # Ищем ожидающие матчи
        waiting = await self.match_repo.get_waiting_matches(platform)
        
        for match in waiting:
            if match.manager1_id != manager_id:
                # Присоединяемся
                match = await self.join_match(match.id, manager_id)
                return match, False
        
        # Создаём новый
        match = await self.create_match(manager_id, MatchType.RANDOM, platform)
        return match, True
    
    async def join_match(self, match_id: UUID, manager_id: UUID) -> Match:
        """Присоединиться к матчу"""
        match = await self.match_repo.get_by_id(match_id)
        if not match:
            raise ValueError("Матч не найден")
        
        match = self.engine.join_match(match, manager_id)
        match = await self.match_repo.update(match)
        
        await self.event_bus.publish(
            MatchJoinedEvent(match.id, manager_id)
        )
        
        return match
    
    async def set_lineup(
        self,
        match_id: UUID,
        manager_id: UUID,
        formation: Formation,
        player_ids: List[UUID]
    ) -> Match:
        """Установить состав команды"""
        match = await self.match_repo.get_by_id(match_id)
        if not match:
            raise ValueError("Матч не найден")
        
        # Получаем команду пользователя
        team = await self.team_repo.get_by_user_id(manager_id)
        if not team:
            raise ValueError("Команда не найдена")
        
        # Устанавливаем состав через движок
        match = self.engine.set_team_lineup(
            match, manager_id, team, formation, player_ids
        )
        match = await self.match_repo.update(match)
        
        # Если матч начался, публикуем событие
        if match.status == MatchStatus.IN_PROGRESS:
            await self.event_bus.publish(
                MatchStartedEvent(match.id, match.manager1_id, match.manager2_id)
            )
        
        return match
    
    async def place_bet(
        self,
        match_id: UUID,
        manager_id: UUID,
        player_id: UUID,
        bet: Bet
    ) -> Tuple[Match, Bet]:
        """Разместить ставку"""
        match = await self.match_repo.get_by_id(match_id)
        if not match:
            raise ValueError("Матч не найден")
        
        match, bet = self.engine.place_bet(match, manager_id, player_id, bet)
        match = await self.match_repo.update(match)
        
        await self.event_bus.publish(
            BetPlacedEvent(match.id, manager_id, bet.id, player_id)
        )
        
        return match, bet
    
    async def roll_dice(
        self,
        match_id: UUID,
        manager_id: UUID
    ) -> Tuple[Match, int, List[Bet]]:
        """Бросить кубик"""
        match = await self.match_repo.get_by_id(match_id)
        if not match:
            raise ValueError("Матч не найден")
        
        match, dice_value, won_bets = self.engine.roll_dice(match, manager_id)
        match = await self.match_repo.update(match)
        
        await self.event_bus.publish(
            DiceRolledEvent(match.id, manager_id, dice_value, len(won_bets))
        )
        
        return match, dice_value, won_bets
    
    async def draw_card(
        self,
        match_id: UUID,
        manager_id: UUID
    ) -> Tuple[Match, Optional[WhistleCard]]:
        """Взять карточку Свисток"""
        match = await self.match_repo.get_by_id(match_id)
        if not match:
            raise ValueError("Матч не найден")
        
        match, card = self.engine.draw_whistle_card(match, manager_id)
        match = await self.match_repo.update(match)
        
        if card:
            await self.event_bus.publish(
                CardDrawnEvent(match.id, manager_id, card.card_type.value)
            )
        
        return match, card
    
    async def apply_card(
        self,
        match_id: UUID,
        manager_id: UUID,
        card_id: UUID,
        target_player_id: Optional[UUID] = None
    ) -> Match:
        """Применить карточку Свисток"""
        match = await self.match_repo.get_by_id(match_id)
        if not match:
            raise ValueError("Матч не найден")
        
        match = self.engine.apply_whistle_card(
            match, manager_id, card_id, target_player_id
        )
        match = await self.match_repo.update(match)
        
        return match
    
    async def end_turn(self, match_id: UUID, manager_id: UUID) -> Match:
        """Завершить ход"""
        match = await self.match_repo.get_by_id(match_id)
        if not match:
            raise ValueError("Матч не найден")
        
        turn_number = match.current_turn.turn_number if match.current_turn else 0
        
        match = self.engine.end_turn(match, manager_id)
        match = await self.match_repo.update(match)
        
        await self.event_bus.publish(
            TurnCompletedEvent(match.id, manager_id, turn_number)
        )
        
        # Если матч завершился
        if match.status == MatchStatus.FINISHED and match.result:
            await self._handle_match_finished(match)
        
        return match
    
    async def _handle_match_finished(self, match: Match) -> None:
        """Обработать завершение матча"""
        if not match.result:
            return
        
        score = f"{match.score.manager1_goals}:{match.score.manager2_goals}"
        
        await self.event_bus.publish(
            MatchFinishedEvent(
                match.id,
                match.result.winner_id,
                match.result.loser_id,
                score,
                match.result.decided_by.value
            )
        )
    
    async def cancel_match(self, match_id: UUID, manager_id: UUID) -> Match:
        """Отменить матч"""
        match = await self.match_repo.get_by_id(match_id)
        if not match:
            raise ValueError("Матч не найден")
        
        match = self.engine.cancel_match(match, manager_id)
        match = await self.match_repo.update(match)
        
        return match
    
    async def get_user_active_match(self, user_id: UUID) -> Optional[Match]:
        """Получить активный матч пользователя"""
        return await self.match_repo.get_user_active_match(user_id)
    
    async def get_match(self, match_id: UUID) -> Optional[Match]:
        """Получить матч по ID"""
        return await self.match_repo.get_by_id(match_id)
    
    async def get_available_bet_types(
        self,
        match_id: UUID,
        manager_id: UUID,
        player_id: UUID
    ) -> List[BetType]:
        """Получить доступные типы ставок для игрока"""
        match = await self.match_repo.get_by_id(match_id)
        if not match:
            return []
        
        return self.engine.get_available_bet_types(match, manager_id, player_id)
