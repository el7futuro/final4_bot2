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


class TestTurnBasedAvailability:
    """Тесты доступности по номеру хода"""
    
    def test_turn_1_only_goalkeeper(self, tracker, match_with_team, manager_id):
        """На первом ходу доступен только вратарь"""
        match = match_with_team
        gk = match.team1.players[0]
        defender = match.team1.players[1]
        
        # Вратарь на 1-м ходу — OK
        bet_gk = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=gk.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        tracker.validate_bet(match, manager_id, gk, bet_gk)  # Не выбрасывает
        
        # Защитник на 1-м ходу — ошибка
        bet_def = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=defender.id,
            turn_number=1,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=HighLowChoice.HIGH
        )
        with pytest.raises(ValueError, match="первом ходу.*только вратарь"):
            tracker.validate_bet(match, manager_id, defender, bet_def)
    
    def test_turn_2_no_goalkeeper(self, tracker, match_with_team, manager_id):
        """На втором ходу вратарь недоступен"""
        match = match_with_team
        match.current_turn = TurnState(turn_number=2, current_manager_id=manager_id)
        
        gk = match.team1.players[0]
        defender = match.team1.players[1]
        
        # Вратарь на 2-м ходу — ошибка
        bet_gk = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=gk.id,
            turn_number=2,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        with pytest.raises(ValueError, match="Вратарь.*только на первом"):
            tracker.validate_bet(match, manager_id, gk, bet_gk)
        
        # Защитник на 2-м ходу — OK
        bet_def = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=defender.id,
            turn_number=2,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=HighLowChoice.HIGH
        )
        tracker.validate_bet(match, manager_id, defender, bet_def)  # Не выбрасывает


class TestUsedPlayers:
    """Тесты использованных игроков"""
    
    def test_player_marked_as_used(self, match_with_team, manager_id):
        """Игрок помечается как использованный"""
        match = match_with_team
        defender = match.team1.players[1]
        
        # Изначально не использован
        assert not match.is_player_used(manager_id, defender.id)
        
        # Помечаем как использованного
        match.mark_player_used(manager_id, defender.id)
        
        # Теперь использован
        assert match.is_player_used(manager_id, defender.id)
    
    def test_used_player_cannot_bet(self, tracker, match_with_team, manager_id):
        """Использованный игрок не может делать ставку"""
        match = match_with_team
        match.current_turn = TurnState(turn_number=2, current_manager_id=manager_id)
        
        defender = match.team1.players[1]
        
        # Помечаем как использованного
        match.mark_player_used(manager_id, defender.id)
        
        # Пытаемся сделать ставку — ошибка
        bet = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=defender.id,
            turn_number=2,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=HighLowChoice.HIGH
        )
        with pytest.raises(ValueError, match="уже делал ставку"):
            tracker.validate_bet(match, manager_id, defender, bet)
    
    def test_available_players_decreases(self, match_with_team, manager_id):
        """Количество доступных игроков уменьшается"""
        match = match_with_team
        match.current_turn = TurnState(turn_number=2, current_manager_id=manager_id)
        
        # Изначально 10 полевых доступно (все кроме вратаря)
        available = match.get_available_players_for_betting(manager_id)
        assert len(available) == 10
        
        # Помечаем 3 игроков как использованных
        match.mark_player_used(manager_id, match.team1.players[1].id)
        match.mark_player_used(manager_id, match.team1.players[2].id)
        match.mark_player_used(manager_id, match.team1.players[3].id)
        
        # Теперь 7 доступно
        available = match.get_available_players_for_betting(manager_id)
        assert len(available) == 7


class TestGoalkeeperBets:
    """Тесты ставок на вратаря"""
    
    def test_goalkeeper_can_only_bet_even_odd(self, tracker, match_with_team, manager_id):
        """Вратарь может делать только ставку на чёт/нечёт"""
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
    
    def test_goalkeeper_only_one_bet_per_match(self, tracker, match_with_team, manager_id):
        """Вратарь может сделать только 1 ставку за весь матч"""
        match = match_with_team
        gk = match.team1.players[0]
        
        # Первая ставка — OK
        bet1 = Bet(
            id=uuid4(),
            match_id=match.id,
            manager_id=manager_id,
            player_id=gk.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        match.bets.append(bet1)
        
        # Вторая ставка — ошибка
        bet2 = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=gk.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.ODD
        )
        with pytest.raises(ValueError, match="Вратарь уже сделал"):
            tracker.validate_bet(match, manager_id, gk, bet2)


class TestForwardBets:
    """Тесты ставок на форвардов"""
    
    def test_forward_cannot_bet_even_odd(self, tracker, match_with_team, manager_id):
        """Форварды не могут делать ставку на чёт/нечёт"""
        match = match_with_team
        match.current_turn = TurnState(turn_number=2, current_manager_id=manager_id)
        forward = match.team1.players[9]  # Форвард 1
        
        bet = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=forward.id,
            turn_number=2,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.ODD
        )
        
        with pytest.raises(ValueError, match="Форварды не могут"):
            tracker.validate_bet(match, manager_id, forward, bet)


class TestGoalBetLimits:
    """Тесты лимитов ставок на гол"""
    
    def test_only_one_defender_can_have_goal_bet(self, tracker, match_with_team, manager_id):
        """Только 1 защитник может иметь ставку на гол"""
        match = match_with_team
        match.current_turn = TurnState(turn_number=2, current_manager_id=manager_id)
        
        def1 = match.team1.players[1]
        def2 = match.team1.players[2]
        
        # Первый защитник — OK
        bet1 = Bet(
            id=uuid4(),
            match_id=match.id,
            manager_id=manager_id,
            player_id=def1.id,
            turn_number=2,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=6
        )
        match.bets.append(bet1)
        
        # Второй защитник — ошибка
        bet2 = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=def2.id,
            turn_number=2,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=5
        )
        
        with pytest.raises(ValueError, match="1 защитник"):
            tracker.validate_bet(match, manager_id, def2, bet2)
    
    def test_max_3_goal_bets_from_midfielders(self, tracker, match_with_team, manager_id):
        """Максимум 3 ставки на гол от полузащитников"""
        match = match_with_team
        match.current_turn = TurnState(turn_number=2, current_manager_id=manager_id)
        
        mf1 = match.team1.players[5]
        mf2 = match.team1.players[6]
        
        # Добавляем 3 ставки от одного полузащитника (это считается как 3 ставки)
        for i in range(3):
            bet = Bet(
                id=uuid4(),
                match_id=match.id,
                manager_id=manager_id,
                player_id=mf1.id,
                turn_number=2,
                bet_type=BetType.EXACT_NUMBER,
                exact_number=i + 1
            )
            match.bets.append(bet)
        
        # 4-я ставка от другого полузащитника — ошибка
        bet4 = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=mf2.id,
            turn_number=2,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=4
        )
        
        with pytest.raises(ValueError, match="3 ставки.*полузащитников"):
            tracker.validate_bet(match, manager_id, mf2, bet4)


class TestMaxBetsPerTurn:
    """Тесты максимума ставок за ход"""
    
    def test_goalkeeper_max_1_bet_per_turn(self, tracker, match_with_team, manager_id):
        """Вратарь: максимум 1 ставка за ход (и за матч)"""
        match = match_with_team
        gk = match.team1.players[0]
        
        # Первая ставка
        bet1 = Bet(
            id=uuid4(),
            match_id=match.id,
            manager_id=manager_id,
            player_id=gk.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        match.bets.append(bet1)
        match.current_turn.bets_placed.append(bet1.id)
        
        # Вторая ставка в том же ходе — ошибка (вратарь уже ставил в матче)
        bet2 = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=gk.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.ODD
        )
        
        # Ожидаем любую из двух ошибок
        with pytest.raises(ValueError, match="(Вратарь уже сделал|Максимум 1)"):
            tracker.validate_bet(match, manager_id, gk, bet2)
    
    def test_field_player_max_2_bets_per_turn(self, tracker, match_with_team, manager_id):
        """Полевой игрок: максимум 2 ставки за ход"""
        match = match_with_team
        match.current_turn = TurnState(turn_number=2, current_manager_id=manager_id)
        
        defender = match.team1.players[1]
        
        # Первые 2 ставки — OK
        for i in range(2):
            bet = Bet(
                id=uuid4(),
                match_id=match.id,
                manager_id=manager_id,
                player_id=defender.id,
                turn_number=2,
                bet_type=BetType.HIGH_LOW,
                high_low_choice=HighLowChoice.HIGH
            )
            match.bets.append(bet)
            match.current_turn.bets_placed.append(bet.id)
        
        # 3-я ставка — ошибка
        bet3 = Bet(
            match_id=match.id,
            manager_id=manager_id,
            player_id=defender.id,
            turn_number=2,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=HighLowChoice.LOW
        )
        
        with pytest.raises(ValueError, match="Максимум 2"):
            tracker.validate_bet(match, manager_id, defender, bet3)


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
        match.current_turn = TurnState(turn_number=2, current_manager_id=manager_id)
        defender = match.team1.players[1]
        
        types = tracker.get_available_bet_types(match, manager_id, defender)
        
        assert BetType.EVEN_ODD in types
        assert BetType.HIGH_LOW in types
        assert BetType.EXACT_NUMBER in types
    
    def test_forward_available_types(self, tracker, match_with_team, manager_id):
        """Доступные типы для форварда"""
        match = match_with_team
        match.current_turn = TurnState(turn_number=2, current_manager_id=manager_id)
        forward = match.team1.players[9]
        
        types = tracker.get_available_bet_types(match, manager_id, forward)
        
        assert BetType.EVEN_ODD not in types
        assert BetType.HIGH_LOW in types
        assert BetType.EXACT_NUMBER in types
