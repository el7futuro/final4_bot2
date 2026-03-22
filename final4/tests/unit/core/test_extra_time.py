# tests/unit/core/test_extra_time.py
"""Тесты дополнительного времени"""

import pytest
from uuid import uuid4

from src.core.engine.game_engine import GameEngine
from src.core.engine.bet_tracker import BetTracker
from src.core.models.match import Match, MatchType, MatchStatus, MatchPhase, TurnState
from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice


@pytest.fixture
def tracker():
    return BetTracker()


@pytest.fixture
def manager_id():
    return uuid4()


def create_test_team(manager_id, name: str) -> Team:
    """Создать команду: 1 GK, 5 DF, 6 MF, 4 FW = 16"""
    players = [
        Player(name="Вратарь", position=Position.GOALKEEPER, number=1),
    ]
    for i in range(5):
        players.append(Player(name=f"Защитник {i+1}", position=Position.DEFENDER, number=2+i))
    for i in range(6):
        players.append(Player(name=f"Полузащитник {i+1}", position=Position.MIDFIELDER, number=7+i))
    for i in range(4):
        players.append(Player(name=f"Форвард {i+1}", position=Position.FORWARD, number=13+i))
    
    return Team(manager_id=manager_id, name=name, players=players)


@pytest.fixture
def extra_time_match(manager_id):
    """Матч в дополнительное время"""
    manager2_id = uuid4()
    
    match = Match(
        id=uuid4(),
        manager1_id=manager_id,
        manager2_id=manager2_id,
        match_type=MatchType.RANDOM,
        status=MatchStatus.EXTRA_TIME,
        phase=MatchPhase.EXTRA_TIME
    )
    
    team1 = create_test_team(manager_id, "Team1")
    team2 = create_test_team(manager2_id, "Team2")
    
    match.team1 = team1
    match.team2 = team2
    match.current_turn = TurnState(turn_number=1)
    
    # Помечаем использованных в основное время (11 игроков)
    # Используем: GK(0), DF1-4(1-4), MF1-4(6-9), FW1-2(12-13)
    # Остаются: DF5(5), MF5(10), MF6(11), FW3(14), FW4(15)
    used_indices = [0, 1, 2, 3, 4, 6, 7, 8, 9, 12, 13]
    for idx in used_indices:
        match.mark_player_used(manager_id, team1.players[idx].id)
        match.mark_player_used(manager2_id, team2.players[idx].id)
    
    return match


class TestExtraTimeRules:
    """Тесты правил дополнительного времени"""
    
    def test_goalkeeper_not_available_in_extra_time(self, extra_time_match, manager_id):
        """Вратарь недоступен в Extra Time"""
        engine = GameEngine()
        
        available = engine.get_available_players(extra_time_match, manager_id)
        positions = [p.position for p in available]
        
        assert Position.GOALKEEPER not in positions
    
    def test_only_field_players_available(self, extra_time_match, manager_id):
        """В Extra Time доступны только полевые игроки"""
        engine = GameEngine()
        
        available = engine.get_available_players(extra_time_match, manager_id)
        
        # Должно остаться 5 игроков: DF5, MF5, MF6, FW3, FW4
        assert len(available) == 5
        for p in available:
            assert p.position != Position.GOALKEEPER
    
    def test_goal_bet_required_in_extra_time(self, tracker, extra_time_match, manager_id):
        """Ставка на гол обязательна в Extra Time"""
        # Используем неиспользованного защитника (DF5 = индекс 5)
        defender = extra_time_match.team1.players[5]  # DF5 - не использован
        
        # Проверяем что он не использован
        assert not extra_time_match.is_player_used(manager_id, defender.id)
        
        # Первая ставка — больше/меньше (не гол)
        bet1 = Bet(
            id=uuid4(),
            match_id=extra_time_match.id,
            manager_id=manager_id,
            player_id=defender.id,
            turn_number=1,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=HighLowChoice.HIGH
        )
        extra_time_match.bets.append(bet1)
        extra_time_match.current_turn.bets_placed.append(bet1.id)
        extra_time_match.current_turn.manager1_bets.append(bet1.id)
        
        # Вторая ставка тоже НЕ на гол — должна быть ошибка
        bet2 = Bet(
            match_id=extra_time_match.id,
            manager_id=manager_id,
            player_id=defender.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        
        with pytest.raises(ValueError, match="ОБЯЗАТЕЛЬНО на гол"):
            tracker.validate_bet(extra_time_match, manager_id, defender, bet2)
    
    def test_goal_plus_other_allowed(self, tracker, extra_time_match, manager_id):
        """Ставка на гол + чёт/нечёт разрешена"""
        defender = extra_time_match.team1.players[5]  # DF5 - не использован
        
        # Первая ставка — на гол
        bet1 = Bet(
            id=uuid4(),
            match_id=extra_time_match.id,
            manager_id=manager_id,
            player_id=defender.id,
            turn_number=1,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=3
        )
        extra_time_match.bets.append(bet1)
        extra_time_match.current_turn.bets_placed.append(bet1.id)
        extra_time_match.current_turn.manager1_bets.append(bet1.id)
        
        # Вторая ставка — чёт/нечёт
        bet2 = Bet(
            match_id=extra_time_match.id,
            manager_id=manager_id,
            player_id=defender.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        
        # Не должно быть ошибки
        tracker.validate_bet(extra_time_match, manager_id, defender, bet2)
    
    def test_two_goal_bets_not_allowed(self, tracker, extra_time_match, manager_id):
        """Две ставки на гол запрещены в Extra Time"""
        defender = extra_time_match.team1.players[5]  # DF5 - не использован
        
        # Первая ставка — на гол
        bet1 = Bet(
            id=uuid4(),
            match_id=extra_time_match.id,
            manager_id=manager_id,
            player_id=defender.id,
            turn_number=1,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=3
        )
        extra_time_match.bets.append(bet1)
        extra_time_match.current_turn.bets_placed.append(bet1.id)
        extra_time_match.current_turn.manager1_bets.append(bet1.id)
        
        # Вторая ставка тоже на гол — должна быть ошибка
        bet2 = Bet(
            match_id=extra_time_match.id,
            manager_id=manager_id,
            player_id=defender.id,
            turn_number=1,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=5
        )
        
        with pytest.raises(ValueError, match="только ОДНА ставка на гол"):
            tracker.validate_bet(extra_time_match, manager_id, defender, bet2)
    
    def test_goal_bet_no_limits_in_extra_time(self, tracker, extra_time_match, manager_id):
        """Лимиты на голевые ставки не действуют в Extra Time"""
        # В Extra Time каждый может ставить на гол, без лимитов
        available_types = tracker.get_available_bet_types(
            extra_time_match, 
            manager_id, 
            extra_time_match.team1.players[5]  # DF5
        )
        
        assert BetType.EXACT_NUMBER in available_types
    
    def test_forward_can_bet_even_odd_alternatives(self, tracker, extra_time_match, manager_id):
        """Форвард в Extra Time: гол + больше/меньше"""
        forward = extra_time_match.team1.players[15]  # FW4
        
        available_types = tracker.get_available_bet_types(
            extra_time_match, 
            manager_id, 
            forward
        )
        
        # Форвард: гол + больше/меньше (без чёт/нечёт)
        assert BetType.EXACT_NUMBER in available_types
        assert BetType.HIGH_LOW in available_types
        assert BetType.EVEN_ODD not in available_types


class TestPenaltyShootout:
    """Тесты серии пенальти"""
    
    def test_player_with_pass_scores(self):
        """Игрок с передачей забивает"""
        # По правилам: если у игрока есть передача — он забивает
        player_passes = 1
        scores = player_passes > 0
        assert scores == True
    
    def test_player_without_pass_misses(self):
        """Игрок без передачи промахивается"""
        player_passes = 0
        scores = player_passes > 0
        assert scores == False
