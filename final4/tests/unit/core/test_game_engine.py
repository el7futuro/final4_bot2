# tests/unit/core/test_game_engine.py
"""Тесты игрового движка"""

import pytest
from uuid import uuid4

from src.core.engine.game_engine import GameEngine
from src.core.models.match import Match, MatchType, MatchStatus, MatchPhase
from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice


@pytest.fixture
def engine():
    """Фикстура игрового движка"""
    return GameEngine()


@pytest.fixture
def manager1_id():
    return uuid4()


@pytest.fixture
def manager2_id():
    return uuid4()


@pytest.fixture
def sample_team(manager1_id):
    """Создать тестовую команду"""
    players = []
    
    # Вратарь
    players.append(Player(name="Вратарь 1", position=Position.GOALKEEPER, number=1))
    
    # Защитники
    for i in range(5):
        players.append(Player(name=f"Защитник {i+1}", position=Position.DEFENDER, number=2+i))
    
    # Полузащитники
    for i in range(5):
        players.append(Player(name=f"Полузащитник {i+1}", position=Position.MIDFIELDER, number=7+i))
    
    # Нападающие
    for i in range(4):
        players.append(Player(name=f"Нападающий {i+1}", position=Position.FORWARD, number=12+i))
    
    # Запасной вратарь
    players.append(Player(name="Вратарь 2", position=Position.GOALKEEPER, number=16))
    
    return Team(
        manager_id=manager1_id,
        name="Тестовая команда",
        players=players
    )


class TestMatchCreation:
    """Тесты создания матча"""
    
    def test_create_random_match(self, engine, manager1_id):
        """Создание матча против случайного соперника"""
        match = engine.create_match(manager1_id, MatchType.RANDOM)
        
        assert match.id is not None
        assert match.manager1_id == manager1_id
        assert match.manager2_id is None
        assert match.status == MatchStatus.WAITING_FOR_OPPONENT
        assert len(match.whistle_deck) == 40
    
    def test_create_bot_match(self, engine, manager1_id):
        """Создание матча против бота"""
        match = engine.create_match(manager1_id, MatchType.VS_BOT)
        
        assert match.manager2_id is not None  # Bot ID
        assert match.status == MatchStatus.SETTING_LINEUP
    
    def test_join_match(self, engine, manager1_id, manager2_id):
        """Присоединение к матчу"""
        match = engine.create_match(manager1_id, MatchType.RANDOM)
        match = engine.join_match(match, manager2_id)
        
        assert match.manager2_id == manager2_id
        assert match.status == MatchStatus.SETTING_LINEUP
    
    def test_cannot_join_own_match(self, engine, manager1_id):
        """Нельзя присоединиться к своему матчу"""
        match = engine.create_match(manager1_id, MatchType.RANDOM)
        
        with pytest.raises(ValueError, match="против себя"):
            engine.join_match(match, manager1_id)


class TestLineupSetup:
    """Тесты выбора состава"""
    
    def test_set_valid_lineup(self, engine, manager1_id, manager2_id, sample_team):
        """Установка валидного состава"""
        match = engine.create_match(manager1_id, MatchType.RANDOM)
        match = engine.join_match(match, manager2_id)
        
        # Формация 4-4-2: 1 вратарь, 4 защитника, 4 полузащитника, 2 нападающих
        formation = Formation.F_4_4_2
        
        player_ids = []
        # 1 вратарь
        player_ids.append(sample_team.players[0].id)
        # 4 защитника
        for i in range(1, 5):
            player_ids.append(sample_team.players[i].id)
        # 4 полузащитника
        for i in range(6, 10):
            player_ids.append(sample_team.players[i].id)
        # 2 нападающих
        for i in range(11, 13):
            player_ids.append(sample_team.players[i].id)
        
        match = engine.set_team_lineup(match, manager1_id, sample_team, formation, player_ids)
        
        assert match.team1 is not None
        assert match.team1.formation == formation
        assert len([p for p in match.team1.players if p.is_on_field]) == 11


class TestBetting:
    """Тесты системы ставок"""
    
    def test_even_odd_bet(self, engine, manager1_id):
        """Ставка на чёт/нечёт"""
        match = engine.create_match(manager1_id, MatchType.VS_BOT)
        
        # Создаём команду
        players = [
            Player(name="Вратарь", position=Position.GOALKEEPER, number=1),
        ]
        for i in range(4):
            players.append(Player(name=f"Защитник {i}", position=Position.DEFENDER, number=2+i))
        for i in range(4):
            players.append(Player(name=f"Полузащитник {i}", position=Position.MIDFIELDER, number=6+i))
        for i in range(2):
            players.append(Player(name=f"Форвард {i}", position=Position.FORWARD, number=10+i))
        
        team = Team(manager_id=manager1_id, name="Test", players=players)
        
        # Устанавливаем состав
        player_ids = [p.id for p in players]
        match = engine.set_team_lineup(match, manager1_id, team, Formation.F_4_4_2, player_ids)
        
        # Бот автоматически не устанавливает состав в этом тесте
        # Вручную запускаем матч
        match.status = MatchStatus.IN_PROGRESS
        from src.core.models.match import TurnState
        match.current_turn = TurnState(turn_number=1, current_manager_id=manager1_id)
        
        # Делаем ставку на вратаря
        gk = players[0]
        gk.is_on_field = True
        
        bet = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=gk.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        
        match, placed_bet = engine.place_bet(match, manager1_id, gk.id, bet)
        
        assert placed_bet.id is not None
        assert len(match.bets) == 1


class TestDiceRoll:
    """Тесты броска кубика"""
    
    def test_dice_roll_resolves_bets(self, engine, manager1_id):
        """Бросок кубика определяет результаты ставок"""
        from src.core.models.bet import BetOutcome
        
        match = engine.create_match(manager1_id, MatchType.VS_BOT)
        match.status = MatchStatus.IN_PROGRESS
        
        # Создаём минимальную команду
        gk = Player(name="Вратарь", position=Position.GOALKEEPER, number=1, is_on_field=True)
        team = Team(manager_id=manager1_id, name="Test", players=[gk])
        match.team1 = team
        
        from src.core.models.match import TurnState
        match.current_turn = TurnState(turn_number=1, current_manager_id=manager1_id)
        
        # Ставка на чётное
        bet = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=gk.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        match.bets.append(bet)
        match.current_turn.bets_placed.append(bet.id)
        
        # Бросаем кубик
        match, dice_value, won_bets = engine.roll_dice(match, manager1_id)
        
        assert dice_value >= 1 and dice_value <= 6
        assert match.current_turn.dice_rolled
        
        # Проверяем, что ставка разрешена
        assert bet.outcome in [BetOutcome.WON, BetOutcome.LOST]


class TestScoreCalculation:
    """Тесты подсчёта счёта"""
    
    def test_goals_scored_without_defense(self):
        """Голы засчитываются без обороны"""
        from src.core.engine.score_calculator import ScoreCalculator
        
        calc = ScoreCalculator()
        
        # Команда 1: 3 передачи, 2 гола vs Команда 2: 0 отбитий
        # Все голы команды 1 засчитываются
        goals = calc._calculate_goals_scored(
            own_passes=3,
            own_goals=2,
            opponent_saves=0
        )
        assert goals == 2
    
    def test_passes_break_through_saves(self):
        """Передачи пробивают отбития"""
        from src.core.engine.score_calculator import ScoreCalculator
        
        calc = ScoreCalculator()
        
        # 5 передач vs 5 отбитий = все голы засчитываются
        goals = calc._calculate_goals_scored(
            own_passes=5,
            own_goals=3,
            opponent_saves=5
        )
        assert goals == 3
    
    def test_goals_destroy_saves(self):
        """Голы уничтожают отбития (1 гол = 2 отбития)"""
        from src.core.engine.score_calculator import ScoreCalculator
        
        calc = ScoreCalculator()
        
        # 0 передач, 4 гола vs 6 отбитий
        # 4 гола нужно потратить на 6 отбитий: 3 гола = 6 отбитий
        # Остаётся 1 гол
        goals = calc._calculate_goals_scored(
            own_passes=0,
            own_goals=4,
            opponent_saves=6
        )
        assert goals == 1
