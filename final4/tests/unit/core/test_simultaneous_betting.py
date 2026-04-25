# tests/unit/core/test_simultaneous_betting.py
"""Тесты одновременных ставок обоих менеджеров"""

import pytest
from uuid import uuid4

from src.core.engine.game_engine import GameEngine
from src.core.models.match import Match, MatchType, MatchStatus, TurnState
from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, BetOutcome, EvenOddChoice, HighLowChoice


@pytest.fixture
def engine():
    return GameEngine()


@pytest.fixture
def manager1_id():
    return uuid4()


@pytest.fixture
def manager2_id():
    return uuid4()


def create_test_team(manager_id, name: str) -> Team:
    """Создать тестовую команду"""
    players = [
        Player(name="Вратарь 1", position=Position.GOALKEEPER, number=1),
    ]
    for i in range(4):
        players.append(Player(name=f"Защитник {i+1}", position=Position.DEFENDER, number=2+i))
    for i in range(4):
        players.append(Player(name=f"Полузащитник {i+1}", position=Position.MIDFIELDER, number=6+i))
    for i in range(2):
        players.append(Player(name=f"Форвард {i+1}", position=Position.FORWARD, number=10+i))
    
    return Team(manager_id=manager_id, name=name, players=players)


@pytest.fixture
def match_in_progress(engine, manager1_id, manager2_id):
    """Матч в процессе с двумя командами"""
    match = engine.create_match(manager1_id, MatchType.RANDOM)
    match = engine.join_match(match, manager2_id)
    
    team1 = create_test_team(manager1_id, "Team1")
    team2 = create_test_team(manager2_id, "Team2")
    
    player_ids = [p.id for p in team1.players]
    match = engine.set_team_lineup(match, manager1_id, team1, Formation.F_4_4_2, player_ids)
    
    player_ids = [p.id for p in team2.players]
    match = engine.set_team_lineup(match, manager2_id, team2, Formation.F_4_4_2, player_ids)
    
    return match


class TestSimultaneousBetting:
    """Тесты одновременных ставок"""
    
    def test_both_managers_can_place_bets(self, match_in_progress, manager1_id, manager2_id):
        """Оба менеджера могут делать ставки в одном ходе"""
        match = match_in_progress
        engine = GameEngine()
        
        # Менеджер 1 делает ставку
        gk1 = match.team1.players[0]
        bet1 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=gk1.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        match, placed1 = engine.place_bet(match, manager1_id, gk1.id, bet1)
        
        # Менеджер 2 тоже делает ставку
        gk2 = match.team2.players[0]
        bet2 = Bet(
            match_id=match.id,
            manager_id=manager2_id,
            player_id=gk2.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.ODD
        )
        match, placed2 = engine.place_bet(match, manager2_id, gk2.id, bet2)
        
        # Проверяем, что обе ставки зарегистрированы
        assert len(match.bets) == 2
        assert match.current_turn.manager1_bets[0] == placed1.id
        assert match.current_turn.manager2_bets[0] == placed2.id
    
    def test_dice_requires_both_ready(self, match_in_progress, manager1_id, manager2_id):
        """Кубик можно бросить только когда оба готовы"""
        match = match_in_progress
        engine = GameEngine()
        
        # Только менеджер 1 делает ставку
        gk1 = match.team1.players[0]
        bet1 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=gk1.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        match, _ = engine.place_bet(match, manager1_id, gk1.id, bet1)
        engine.confirm_bets(match, manager1_id)
        
        # Пытаемся бросить кубик — должна быть ошибка
        can_roll, reason = engine.can_roll_dice(match)
        assert not can_roll
        assert "Менеджер 2" in reason
    
    def test_single_dice_roll_for_both(self, match_in_progress, manager1_id, manager2_id):
        """Один бросок кубика определяет результаты для обоих"""
        match = match_in_progress
        engine = GameEngine()
        
        # Оба делают ставки на вратарей
        gk1 = match.team1.players[0]
        gk2 = match.team2.players[0]
        
        bet1 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=gk1.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        match, _ = engine.place_bet(match, manager1_id, gk1.id, bet1)
        engine.confirm_bets(match, manager1_id)
        
        bet2 = Bet(
            match_id=match.id,
            manager_id=manager2_id,
            player_id=gk2.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.ODD
        )
        match, _ = engine.place_bet(match, manager2_id, gk2.id, bet2)
        engine.confirm_bets(match, manager2_id)
        
        # Бросаем кубик
        match, dice_value, won_bets = engine.roll_dice(match)
        
        # Проверяем, что результат определён для обоих
        assert dice_value >= 1 and dice_value <= 6
        
        # Один из них должен выиграть (чёт/нечёт противоположны)
        total_won = len(won_bets[manager1_id]) + len(won_bets[manager2_id])
        assert total_won == 1  # Ровно один выиграл


class TestDifferentBetTypes:
    """Тесты на правило разных типов ставок"""
    
    def test_two_bets_must_be_different_types(self, match_in_progress, manager1_id, manager2_id):
        """Две ставки должны быть разных типов"""
        match = match_in_progress
        engine = GameEngine()
        
        # Переходим к ходу 2 (полевые игроки)
        match.current_turn = TurnState(turn_number=2)
        
        defender = match.team1.players[1]
        
        # Первая ставка HIGH_LOW
        bet1 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=defender.id,
            turn_number=2,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=HighLowChoice.HIGH
        )
        match, _ = engine.place_bet(match, manager1_id, defender.id, bet1)
        
        # Вторая ставка того же типа — должна быть ошибка
        bet2 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=defender.id,
            turn_number=2,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=HighLowChoice.LOW
        )
        
        with pytest.raises(ValueError, match="РАЗНЫХ типов"):
            engine.place_bet(match, manager1_id, defender.id, bet2)
    
    def test_two_different_types_allowed(self, match_in_progress, manager1_id):
        """Разные типы ставок разрешены"""
        match = match_in_progress
        engine = GameEngine()
        
        # Переходим к ходу 2
        match.current_turn = TurnState(turn_number=2)
        
        defender = match.team1.players[1]
        
        # HIGH_LOW + EVEN_ODD — OK
        bet1 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=defender.id,
            turn_number=2,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=HighLowChoice.HIGH
        )
        match, _ = engine.place_bet(match, manager1_id, defender.id, bet1)
        
        bet2 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=defender.id,
            turn_number=2,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        match, placed = engine.place_bet(match, manager1_id, defender.id, bet2)
        
        assert placed is not None
        assert len(match.current_turn.manager1_bets) == 2


class TestAutoWhistleCard:
    """Тесты автоматического вытягивания карточки"""
    
    def test_card_drawn_automatically_on_win(self, match_in_progress, manager1_id, manager2_id):
        """Карточка вытягивается автоматически при выигрыше (полевые игроки)"""
        match = match_in_progress
        engine = GameEngine()
        
        # Ход 1 — вратари (карточки НЕ выпадают у вратарей)
        gk1 = match.team1.players[0]
        gk2 = match.team2.players[0]
        
        bet1 = Bet(
            match_id=match.id, manager_id=manager1_id, player_id=gk1.id,
            turn_number=1, bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.EVEN
        )
        match, _ = engine.place_bet(match, manager1_id, gk1.id, bet1)
        engine.confirm_bets(match, manager1_id)
        
        bet2 = Bet(
            match_id=match.id, manager_id=manager2_id, player_id=gk2.id,
            turn_number=1, bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.ODD
        )
        match, _ = engine.place_bet(match, manager2_id, gk2.id, bet2)
        engine.confirm_bets(match, manager2_id)
        
        match, _, _ = engine.roll_dice(match)
        # У вратарей карточки не выпадают
        assert len(match.whistle_cards_drawn) == 0
        
        # Переходим к ходу 2 — полевые игроки
        match = engine.end_turn(match)
        
        # Берём защитников (индекс 1 в players)
        def1 = match.team1.players[1]
        def2 = match.team2.players[1]
        
        # Менеджер 1: два разных типа ставок
        b1 = Bet(
            match_id=match.id, manager_id=manager1_id, player_id=def1.id,
            turn_number=2, bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.EVEN
        )
        match, _ = engine.place_bet(match, manager1_id, def1.id, b1)
        b1b = Bet(
            match_id=match.id, manager_id=manager1_id, player_id=def1.id,
            turn_number=2, bet_type=BetType.HIGH_LOW, high_low_choice=HighLowChoice.HIGH
        )
        match, _ = engine.place_bet(match, manager1_id, def1.id, b1b)
        engine.confirm_bets(match, manager1_id)
        
        # Менеджер 2: два разных типа ставок
        b2 = Bet(
            match_id=match.id, manager_id=manager2_id, player_id=def2.id,
            turn_number=2, bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.ODD
        )
        match, _ = engine.place_bet(match, manager2_id, def2.id, b2)
        b2b = Bet(
            match_id=match.id, manager_id=manager2_id, player_id=def2.id,
            turn_number=2, bet_type=BetType.HIGH_LOW, high_low_choice=HighLowChoice.LOW
        )
        match, _ = engine.place_bet(match, manager2_id, def2.id, b2b)
        engine.confirm_bets(match, manager2_id)
        
        cards_before = len(match.whistle_cards_drawn)
        
        match, dice_value, won_bets = engine.roll_dice(match)
        
        cards_after = len(match.whistle_cards_drawn)
        
        # Оба менеджера выиграли хотя бы одну ставку (одна из EVEN/ODD и одна из HIGH/LOW)
        # Значит минимум 1 карточка, максимум 2
        total_winners = sum(1 for v in won_bets.values() if v)
        assert cards_after == cards_before + total_winners
        assert total_winners >= 1  # Минимум один из двух всегда выигрывает


class TestPlayerAvailability:
    """Тесты доступности игроков"""
    
    def test_player_needs_two_bet_types(self, match_in_progress, manager1_id):
        """Игрок доступен только если есть минимум 2 типа ставок"""
        match = match_in_progress
        engine = GameEngine()
        
        # Переходим к ходу 2
        match.current_turn = TurnState(turn_number=2)
        
        # Форвард: только HIGH_LOW и EXACT_NUMBER (нет EVEN_ODD)
        forward = match.team1.players[9]
        
        available_types = engine.get_available_bet_types(match, manager1_id, forward.id)
        
        # Форвард должен иметь минимум 2 типа
        assert len(available_types) >= 2
        assert BetType.EVEN_ODD not in available_types
        assert BetType.HIGH_LOW in available_types
    
    def test_player_with_one_type_not_available(self, match_in_progress, manager1_id):
        """Игрок с 1 типом ставок недоступен для выбора"""
        match = match_in_progress
        engine = GameEngine()
        
        # Переходим к ходу 2
        match.current_turn = TurnState(turn_number=2)
        
        # Исчерпываем лимит голевых ставок для форвардов (4 макс)
        forward1 = match.team1.players[9]
        for i in range(4):
            bet = Bet(
                id=uuid4(),
                match_id=match.id,
                manager_id=manager1_id,
                player_id=forward1.id,
                turn_number=2,
                bet_type=BetType.EXACT_NUMBER,
                exact_number=i + 1
            )
            match.bets.append(bet)
        
        # Теперь у форварда 2 остаётся только HIGH_LOW (нет EVEN_ODD, нет EXACT_NUMBER)
        forward2 = match.team1.players[10]
        available_types = engine.get_available_bet_types(match, manager1_id, forward2.id)
        
        # Combo-aware: с 1 валидным типом (HIGH_LOW) нельзя сделать пару из 2,
        # поэтому возвращается пустой список — игрок объективно "не может ставить"
        assert available_types == []
        
        # Проверяем, что форвард 2 НЕ в списке доступных игроков
        available_players = engine.get_available_players(match, manager1_id)
        player_ids = [p.id for p in available_players]
        
        assert forward2.id not in player_ids


class TestEndTurn:
    """Тесты завершения хода"""
    
    def test_end_turn_marks_players_used(self, match_in_progress, manager1_id, manager2_id):
        """Завершение хода помечает игроков как использованных"""
        match = match_in_progress
        engine = GameEngine()
        
        gk1 = match.team1.players[0]
        gk2 = match.team2.players[0]
        
        # Оба делают ставки
        bet1 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=gk1.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        match, _ = engine.place_bet(match, manager1_id, gk1.id, bet1)
        engine.confirm_bets(match, manager1_id)
        
        bet2 = Bet(
            match_id=match.id,
            manager_id=manager2_id,
            player_id=gk2.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.ODD
        )
        match, _ = engine.place_bet(match, manager2_id, gk2.id, bet2)
        engine.confirm_bets(match, manager2_id)
        
        # Бросаем и завершаем
        match, _, _ = engine.roll_dice(match)
        match = engine.end_turn(match)
        
        # Проверяем, что вратари использованы
        assert match.is_player_used(manager1_id, gk1.id)
        assert match.is_player_used(manager2_id, gk2.id)
        
        # Номер хода увеличился
        assert match.current_turn.turn_number == 2
