# tests/unit/core/test_bet_tracker.py
"""Тесты валидации ставок"""

import pytest
from uuid import uuid4

from src.core.engine.bet_tracker import BetTracker
from src.core.models.match import Match, MatchType, MatchStatus, TurnState
from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice


@pytest.fixture
def tracker():
    return BetTracker()


@pytest.fixture
def manager_id():
    return uuid4()


@pytest.fixture
def match_with_team(manager_id):
    """Матч с командой"""
    match = Match(
        match_type=MatchType.VS_BOT,
        manager1_id=manager_id,
        status=MatchStatus.IN_PROGRESS,
        current_turn=TurnState(turn_number=1, current_manager_id=manager_id)
    )
    
    players = [
        Player(name="Вратарь", position=Position.GOALKEEPER, number=1, is_on_field=True),
        Player(name="Защитник 1", position=Position.DEFENDER, number=2, is_on_field=True),
        Player(name="Защитник 2", position=Position.DEFENDER, number=3, is_on_field=True),
        Player(name="Защитник 3", position=Position.DEFENDER, number=4, is_on_field=True),
        Player(name="Защитник 4", position=Position.DEFENDER, number=5, is_on_field=True),
        Player(name="Полузащитник 1", position=Position.MIDFIELDER, number=6, is_on_field=True),
        Player(name="Полузащитник 2", position=Position.MIDFIELDER, number=7, is_on_field=True),
        Player(name="Полузащитник 3", position=Position.MIDFIELDER, number=8, is_on_field=True),
        Player(name="Полузащитник 4", position=Position.MIDFIELDER, number=9, is_on_field=True),
        Player(name="Форвард 1", position=Position.FORWARD, number=10, is_on_field=True),
        Player(name="Форвард 2", position=Position.FORWARD, number=11, is_on_field=True),
    ]
    
    match.team1 = Team(manager_id=manager_id, name="Test", players=players)
    
    return match


class TestGoalkeeperBets:
    """Тесты ставок на вратаря"""
    
    def test_goalkeeper_can_only_bet_even_odd(self, tracker, match_with_team, manager_id):
        """Вратарь может иметь только ставку на чёт/нечёт"""
        match = match_with_team
        gk = match.team1.players[0]
        
        # Чёт/нечёт — OK
        bet = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=gk.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        tracker.validate_bet(match, manager_id, gk, bet)  # Не выбрасывает
        
        # Больше/меньше — ошибка
        bet2 = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=gk.id,
            turn_number=1,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=HighLowChoice.HIGH
        )
        with pytest.raises(ValueError, match="чёт/нечёт"):
            tracker.validate_bet(match, manager_id, gk, bet2)
        
        # Точное число — ошибка
        bet3 = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=gk.id,
            turn_number=1,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=5
        )
        with pytest.raises(ValueError):
            tracker.validate_bet(match, manager_id, gk, bet3)


class TestForwardBets:
    """Тесты ставок на форвардов"""
    
    def test_forward_cannot_bet_even_odd(self, tracker, match_with_team, manager_id):
        """Форварды не могут иметь ставку на чёт/нечёт"""
        match = match_with_team
        forward = match.team1.players[9]  # Форвард 1
        
        bet = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=forward.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.ODD
        )
        
        with pytest.raises(ValueError, match="Форварды"):
            tracker.validate_bet(match, manager_id, forward, bet)


class TestGoalBetLimits:
    """Тесты лимитов ставок на гол"""
    
    def test_only_one_defender_can_have_goal_bet(self, tracker, match_with_team, manager_id):
        """Только 1 защитник может иметь ставку на гол"""
        match = match_with_team
        
        def1 = match.team1.players[1]
        def2 = match.team1.players[2]
        
        # Первый защитник — OK
        bet1 = Bet(
            id=uuid4(),
            match_id=match.id,
            manager_id=manager_id,
            player_id=def1.id,
            turn_number=1,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=6
        )
        match.bets.append(bet1)
        
        # Второй защитник — ошибка
        bet2 = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=def2.id,
            turn_number=1,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=5
        )
        
        with pytest.raises(ValueError, match="1 защитник"):
            tracker.validate_bet(match, manager_id, def2, bet2)


class TestAvailableBetTypes:
    """Тесты доступных типов ставок"""
    
    def test_goalkeeper_available_types(self, tracker, match_with_team, manager_id):
        """Доступные типы для вратаря"""
        match = match_with_team
        gk = match.team1.players[0]
        
        types = tracker.get_available_bet_types(match, manager_id, gk)
        
        assert BetType.EVEN_ODD in types
        assert BetType.HIGH_LOW not in types
        assert BetType.EXACT_NUMBER not in types
    
    def test_defender_available_types(self, tracker, match_with_team, manager_id):
        """Доступные типы для защитника"""
        match = match_with_team
        defender = match.team1.players[1]
        
        types = tracker.get_available_bet_types(match, manager_id, defender)
        
        assert BetType.EVEN_ODD in types
        assert BetType.HIGH_LOW in types
        assert BetType.EXACT_NUMBER in types
    
    def test_forward_available_types(self, tracker, match_with_team, manager_id):
        """Доступные типы для форварда"""
        match = match_with_team
        forward = match.team1.players[9]
        
        types = tracker.get_available_bet_types(match, manager_id, forward)
        
        assert BetType.EVEN_ODD not in types
        assert BetType.HIGH_LOW in types
        assert BetType.EXACT_NUMBER in types
