# src/core/engine/game_engine.py
"""Главный игровой движок"""

from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, List, Tuple
import random

from ..models.match import (
    Match, MatchStatus, MatchType, MatchPhase,
    TurnState, MatchResult, MatchScore
)
from ..models.team import Team, Formation
from ..models.player import Player, Position
from ..models.bet import Bet, BetType, BetOutcome
from ..models.whistle_card import WhistleCard

from .bet_tracker import BetTracker
from .action_calculator import ActionCalculator
from .score_calculator import ScoreCalculator
from .whistle_deck import WhistleDeck


# ID бота для матчей vs_bot
BOT_USER_ID = UUID('00000000-0000-0000-0000-000000000001')


class GameEngine:
    """Главный игровой движок Final 4"""
    
    def __init__(self):
        self.bet_tracker = BetTracker()
        self.action_calculator = ActionCalculator()
        self.score_calculator = ScoreCalculator()
    
    def create_match(
        self,
        manager_id: UUID,
        match_type: MatchType,
        platform: str = "telegram"
    ) -> Match:
        """Создать новый матч"""
        match = Match(
            id=uuid4(),
            match_type=match_type,
            manager1_id=manager_id,
            created_at=datetime.utcnow(),
            platform=platform,
            whistle_deck=WhistleDeck.create_deck()
        )
        
        if match_type == MatchType.VS_BOT:
            match.manager2_id = BOT_USER_ID
            match.status = MatchStatus.SETTING_LINEUP
        
        return match
    
    def join_match(self, match: Match, manager_id: UUID) -> Match:
        """Присоединиться к матчу"""
        if match.status != MatchStatus.WAITING_FOR_OPPONENT:
            raise ValueError("Матч не ожидает соперника")
        if match.manager2_id is not None:
            raise ValueError("Матч уже имеет соперника")
        if match.manager1_id == manager_id:
            raise ValueError("Нельзя играть против себя")
        
        match.manager2_id = manager_id
        match.status = MatchStatus.SETTING_LINEUP
        return match
    
    def set_team_lineup(
        self,
        match: Match,
        manager_id: UUID,
        team: Team,
        formation: Formation,
        player_ids: List[UUID]
    ) -> Match:
        """Установить состав команды"""
        if match.status != MatchStatus.SETTING_LINEUP:
            raise ValueError("Нельзя менять состав в текущем статусе")
        
        if not match.is_participant(manager_id):
            raise ValueError("Вы не участник этого матча")
        
        team.set_formation(formation)
        if not team.set_lineup(player_ids):
            raise ValueError("Невалидный состав для формации")
        
        if manager_id == match.manager1_id:
            match.team1 = team
        else:
            match.team2 = team
        
        # Проверяем, оба ли готовы
        if match.team1 and match.team2:
            match = self._start_match(match)
        
        return match
    
    def _start_match(self, match: Match) -> Match:
        """Начать матч"""
        match.status = MatchStatus.IN_PROGRESS
        match.started_at = datetime.utcnow()
        match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=match.manager1_id  # Создатель ходит первым
        )
        return match
    
    def place_bet(
        self,
        match: Match,
        manager_id: UUID,
        player_id: UUID,
        bet: Bet
    ) -> Tuple[Match, Bet]:
        """Разместить ставку"""
        if not match.is_manager_turn(manager_id):
            raise ValueError("Сейчас не ваш ход")
        
        if match.current_turn and match.current_turn.dice_rolled:
            raise ValueError("Кубик уже брошен, ставки закрыты")
        
        team = match.get_team(manager_id)
        if not team:
            raise ValueError("Команда не найдена")
        
        player = team.get_player_by_id(player_id)
        if not player:
            raise ValueError("Игрок не найден")
        
        if not player.is_on_field:
            raise ValueError("Игрок не на поле")
        
        # Валидация правил ставок
        self.bet_tracker.validate_bet(match, manager_id, player, bet)
        
        # Заполняем поля ставки
        bet.id = uuid4()
        bet.match_id = match.id
        bet.manager_id = manager_id
        bet.player_id = player_id
        bet.turn_number = match.current_turn.turn_number if match.current_turn else 1
        
        match.add_bet(bet)
        
        return match, bet
    
    def roll_dice(self, match: Match, manager_id: UUID) -> Tuple[Match, int, List[Bet]]:
        """Бросить кубик и определить результаты ставок"""
        if not match.is_manager_turn(manager_id):
            raise ValueError("Сейчас не ваш ход")
        
        if not match.current_turn:
            raise ValueError("Ход не начат")
        
        if match.current_turn.dice_rolled:
            raise ValueError("Кубик уже брошен в этот ход")
        
        # Бросок
        dice_value = random.randint(1, 6)
        match.current_turn.dice_rolled = True
        match.current_turn.dice_value = dice_value
        
        # Определяем результаты ставок этого хода
        turn_bets = match.get_turn_bets()
        won_bets = []
        
        team = match.get_team(manager_id)
        
        for bet in turn_bets:
            outcome = bet.resolve(dice_value)
            if outcome == BetOutcome.WON:
                won_bets.append(bet)
                # Начисляем действия
                if team:
                    player = team.get_player_by_id(bet.player_id)
                    if player:
                        self.action_calculator.apply_bet_result(player, bet)
        
        return match, dice_value, won_bets
    
    def draw_whistle_card(
        self,
        match: Match,
        manager_id: UUID
    ) -> Tuple[Match, Optional[WhistleCard]]:
        """Взять карточку Свисток (если есть выигравшие ставки)"""
        if not match.is_manager_turn(manager_id):
            raise ValueError("Сейчас не ваш ход")
        
        if not match.current_turn:
            raise ValueError("Ход не начат")
        
        if match.current_turn.card_drawn:
            raise ValueError("Карточка уже взята в этот ход")
        
        # Проверяем, есть ли выигравшие ставки
        turn_bets = match.get_turn_bets()
        won_any = any(b.outcome == BetOutcome.WON for b in turn_bets)
        
        match.current_turn.card_drawn = True
        
        if not won_any:
            return match, None
        
        if not match.whistle_deck:
            return match, None
        
        card = WhistleDeck.draw_card(match.whistle_deck)
        if card:
            card.applied_by_manager_id = manager_id
            card.turn_applied = match.current_turn.turn_number
            match.current_turn.card_id = card.id
            match.whistle_cards_drawn.append(card)
        
        return match, card
    
    def apply_whistle_card(
        self,
        match: Match,
        manager_id: UUID,
        card_id: UUID,
        target_player_id: Optional[UUID] = None
    ) -> Match:
        """Применить карточку Свисток"""
        if not match.is_manager_turn(manager_id):
            raise ValueError("Сейчас не ваш ход")
        
        # Находим карточку
        card = next((c for c in match.whistle_cards_drawn if c.id == card_id), None)
        if not card:
            raise ValueError("Карточка не найдена")
        
        if card.is_used:
            raise ValueError("Карточка уже использована")
        
        # Проверяем, нужна ли цель
        if card.requires_target() and not target_player_id:
            raise ValueError("Необходимо выбрать цель для карточки")
        
        # Получаем эффект и применяем
        effect = WhistleDeck.get_card_effect(card, match, manager_id, target_player_id)
        match = WhistleDeck.apply_effect(match, effect)
        
        card.is_used = True
        card.applied_to_player_id = target_player_id
        
        if match.current_turn:
            match.current_turn.card_applied = True
        
        return match
    
    def end_turn(self, match: Match, manager_id: UUID) -> Match:
        """Завершить ход и передать другому игроку"""
        if not match.is_manager_turn(manager_id):
            raise ValueError("Сейчас не ваш ход")
        
        if not match.current_turn:
            raise ValueError("Ход не начат")
        
        # Пересчитываем статистику команд
        if match.team1:
            match.team1.calculate_stats()
        if match.team2:
            match.team2.calculate_stats()
        
        # Увеличиваем счётчик ходов
        if match.phase == MatchPhase.MAIN_TIME:
            match.total_turns_main += 1
        else:
            match.total_turns_extra += 1
        
        # Проверяем, закончился ли матч
        # В основное время: 22 хода (11 каждый)
        if match.phase == MatchPhase.MAIN_TIME and match.total_turns_main >= 22:
            return self._end_main_time(match)
        
        # Дополнительное время: 10 ходов (5 каждый)
        if match.phase == MatchPhase.EXTRA_TIME and match.total_turns_extra >= 10:
            return self._end_extra_time(match)
        
        # Передаём ход сопернику
        next_manager = match.get_opponent_id(manager_id)
        if next_manager:
            match.current_turn = TurnState(
                turn_number=match.current_turn.turn_number + 1,
                current_manager_id=next_manager
            )
        
        return match
    
    def _end_main_time(self, match: Match) -> Match:
        """Завершить основное время"""
        if match.team1 and match.team2:
            score = self.score_calculator.calculate_score(match.team1, match.team2)
            match.score = score
            
            if score.manager1_goals != score.manager2_goals:
                return self._finish_match(match, MatchPhase.MAIN_TIME)
        
        # Ничья — дополнительное время
        match.phase = MatchPhase.EXTRA_TIME
        match.status = MatchStatus.EXTRA_TIME
        match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=match.manager1_id
        )
        return match
    
    def _end_extra_time(self, match: Match) -> Match:
        """Завершить дополнительное время"""
        if match.team1 and match.team2:
            score = self.score_calculator.calculate_score(match.team1, match.team2)
            match.score = score
            
            if score.manager1_goals != score.manager2_goals:
                return self._finish_match(match, MatchPhase.EXTRA_TIME)
        
        # Всё ещё ничья — пенальти
        match.phase = MatchPhase.PENALTIES
        match.status = MatchStatus.PENALTIES
        return self._start_penalties(match)
    
    def _start_penalties(self, match: Match) -> Match:
        """Начать серию пенальти"""
        match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=match.manager1_id
        )
        return match
    
    def execute_penalty_kick(
        self,
        match: Match,
        manager_id: UUID,
        player_id: UUID
    ) -> Tuple[Match, bool]:
        """Выполнить пенальти. Возвращает (match, забит ли гол)"""
        if match.phase != MatchPhase.PENALTIES:
            raise ValueError("Не фаза пенальти")
        
        team = match.get_team(manager_id)
        if not team:
            raise ValueError("Команда не найдена")
        
        player = team.get_player_by_id(player_id)
        if not player:
            raise ValueError("Игрок не найден")
        
        # Гол забивается если у игрока есть передача
        goal_scored = player.stats.passes > 0
        
        if goal_scored:
            if manager_id == match.manager1_id:
                match.score.manager1_goals += 1
            else:
                match.score.manager2_goals += 1
        
        return match, goal_scored
    
    def _finish_match(self, match: Match, decided_by: MatchPhase) -> Match:
        """Завершить матч с результатом"""
        match.status = MatchStatus.FINISHED
        match.finished_at = datetime.utcnow()
        
        if match.score.manager1_goals > match.score.manager2_goals:
            winner_id = match.manager1_id
            loser_id = match.manager2_id
        else:
            winner_id = match.manager2_id
            loser_id = match.manager1_id
        
        match.result = MatchResult(
            winner_id=winner_id,
            loser_id=loser_id,
            final_score=match.score,
            decided_by=decided_by
        )
        
        return match
    
    def finish_by_lottery(self, match: Match) -> Match:
        """Определить победителя жребием (после всех пенальти)"""
        winner_id = random.choice([match.manager1_id, match.manager2_id])
        loser_id = match.manager2_id if winner_id == match.manager1_id else match.manager1_id
        
        match.status = MatchStatus.FINISHED
        match.finished_at = datetime.utcnow()
        match.result = MatchResult(
            winner_id=winner_id,
            loser_id=loser_id,
            final_score=match.score,
            decided_by=MatchPhase.PENALTIES,
            decided_by_lottery=True
        )
        
        return match
    
    def cancel_match(self, match: Match, manager_id: UUID) -> Match:
        """Отменить матч"""
        if match.status not in [MatchStatus.WAITING_FOR_OPPONENT, MatchStatus.SETTING_LINEUP]:
            raise ValueError("Нельзя отменить матч в текущем статусе")
        
        if not match.is_participant(manager_id):
            raise ValueError("Вы не участник этого матча")
        
        match.status = MatchStatus.CANCELLED
        match.finished_at = datetime.utcnow()
        
        return match
    
    def get_available_bet_types(
        self,
        match: Match,
        manager_id: UUID,
        player_id: UUID
    ) -> List[BetType]:
        """Получить доступные типы ставок для игрока"""
        team = match.get_team(manager_id)
        if not team:
            return []
        
        player = team.get_player_by_id(player_id)
        if not player:
            return []
        
        return self.bet_tracker.get_available_bet_types(match, manager_id, player)
