# tests/unit/core/test_whistle_cards.py
"""Тесты карточек Свисток — правильность целеполагания"""

import pytest
from uuid import uuid4

from src.core.engine.game_engine import GameEngine
from src.core.engine.whistle_deck import WhistleDeck
from src.core.models.match import Match, MatchType, MatchStatus, TurnState, MatchPhase
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, BetOutcome, EvenOddChoice, HighLowChoice
from src.core.models.whistle_card import WhistleCard, CardType, CardTarget, CardEffect


@pytest.fixture
def manager1_id():
    return uuid4()

@pytest.fixture
def manager2_id():
    return uuid4()

@pytest.fixture
def setup_match(manager1_id, manager2_id):
    """Создать матч с двумя командами на ходе 2 (полевые игроки)"""
    engine = GameEngine()
    
    # Создаём команды
    team1_players = [
        Player(name="Вратарь 1", position=Position.GOALKEEPER, number=1),
    ]
    for i in range(5):
        team1_players.append(Player(name=f"Защитник 1-{i+1}", position=Position.DEFENDER, number=2+i))
    for i in range(6):
        team1_players.append(Player(name=f"Полузащитник 1-{i+1}", position=Position.MIDFIELDER, number=7+i))
    for i in range(4):
        team1_players.append(Player(name=f"Нападающий 1-{i+1}", position=Position.FORWARD, number=13+i))
    
    team2_players = [
        Player(name="Вратарь 2", position=Position.GOALKEEPER, number=1),
    ]
    for i in range(5):
        team2_players.append(Player(name=f"Защитник 2-{i+1}", position=Position.DEFENDER, number=2+i))
    for i in range(6):
        team2_players.append(Player(name=f"Полузащитник 2-{i+1}", position=Position.MIDFIELDER, number=7+i))
    for i in range(4):
        team2_players.append(Player(name=f"Нападающий 2-{i+1}", position=Position.FORWARD, number=13+i))
    
    team1 = Team(manager_id=manager1_id, name="Команда 1", players=team1_players)
    team2 = Team(manager_id=manager2_id, name="Команда 2", players=team2_players)
    
    match = Match(
        match_type=MatchType.VS_BOT,
        manager1_id=manager1_id,
        manager2_id=manager2_id,
        team1=team1,
        team2=team2,
        status=MatchStatus.IN_PROGRESS,
    )
    
    # Ход 2 — полевые игроки
    defender1 = team1.players[1]  # Защитник команды 1
    defender2 = team2.players[1]  # Защитник команды 2
    
    match.current_turn = TurnState(
        turn_number=2,
        manager1_player_id=defender1.id,
        manager2_player_id=defender2.id,
    )
    
    # Даём защитнику 2 действия чтобы YELLOW_CARD мог снять
    defender2.add_saves(2)
    defender2.add_goals(1)
    
    # Даём защитнику 1 тоже действия
    defender1.add_passes(1)
    defender1.add_goals(1)
    
    engine._init_match_history(match)
    
    return match, engine, defender1, defender2


class TestRedCardTargeting:
    """Тесты: Удаление (RED_CARD) применяется к СОПЕРНИКУ"""
    
    def test_red_card_clears_opponent_stats(self, setup_match, manager1_id, manager2_id):
        """RED_CARD от менеджера 1 обнуляет действия игрока менеджера 2"""
        match, engine, defender1, defender2 = setup_match
        
        # Проверяем начальное состояние
        assert defender2.stats.saves == 2
        assert defender2.stats.goals == 1
        assert defender1.stats.passes == 1
        assert defender1.stats.goals == 1
        
        # Создаём карточку удаление
        card = WhistleCard(card_type=CardType.RED_CARD)
        card.applied_by_manager_id = manager1_id
        card.turn_applied = 2
        
        # target = игрок СОПЕРНИКА (defender2)
        target_player_id = match.current_turn.manager2_player_id
        assert target_player_id == defender2.id
        
        # Получаем эффект
        effect = WhistleDeck.get_card_effect(card, match, manager1_id, target_player_id)
        
        assert effect.player_removed is True
        assert effect.target_player_id == defender2.id
        
        # Применяем
        history = engine.get_match_history(match)
        WhistleDeck.apply_effect(match, effect, history)
        
        # defender2 должен быть обнулён
        assert defender2.stats.saves == 0
        assert defender2.stats.goals == 0
        assert defender2.stats.passes == 0
        assert defender2.is_available is False
        
        # defender1 (свой) НЕ должен быть затронут!
        assert defender1.stats.passes == 1
        assert defender1.stats.goals == 1
        assert defender1.is_available is True
    
    def test_red_card_from_m2_clears_m1_player(self, setup_match, manager1_id, manager2_id):
        """RED_CARD от менеджера 2 обнуляет действия игрока менеджера 1"""
        match, engine, defender1, defender2 = setup_match
        
        card = WhistleCard(card_type=CardType.RED_CARD)
        card.applied_by_manager_id = manager2_id
        card.turn_applied = 2
        
        # target = игрок менеджера 1
        target_player_id = match.current_turn.manager1_player_id
        assert target_player_id == defender1.id
        
        effect = WhistleDeck.get_card_effect(card, match, manager2_id, target_player_id)
        
        assert effect.player_removed is True
        assert effect.target_player_id == defender1.id
        
        history = engine.get_match_history(match)
        WhistleDeck.apply_effect(match, effect, history)
        
        # defender1 обнулён
        assert defender1.stats.passes == 0
        assert defender1.stats.goals == 0
        assert defender1.is_available is False
        
        # defender2 НЕ затронут
        assert defender2.stats.saves == 2
        assert defender2.stats.goals == 1
        assert defender2.is_available is True


class TestYellowCardTargeting:
    """Тесты: Предупреждение (YELLOW_CARD) снимает 1 действие у СОПЕРНИКА"""
    
    def test_yellow_card_removes_action_from_opponent(self, setup_match, manager1_id, manager2_id):
        """YELLOW_CARD от менеджера 1 снимает 1 действие у игрока менеджера 2"""
        match, engine, defender1, defender2 = setup_match
        
        # defender2 имеет: saves=2, goals=1
        # Приоритет снятия: гол > передача > отбитие
        
        card = WhistleCard(card_type=CardType.YELLOW_CARD)
        card.applied_by_manager_id = manager1_id
        card.turn_applied = 2
        
        target_player_id = match.current_turn.manager2_player_id
        assert target_player_id == defender2.id
        
        effect = WhistleDeck.get_card_effect(card, match, manager1_id, target_player_id)
        
        # Должен снять 1 гол (приоритет: гол > передача > отбитие)
        assert effect.goals_removed == 1
        assert effect.target_player_id == defender2.id
        
        history = engine.get_match_history(match)
        WhistleDeck.apply_effect(match, effect, history)
        
        # defender2: goals 1→0, saves остаётся 2
        assert defender2.stats.goals == 0
        assert defender2.stats.saves == 2
        
        # defender1 НЕ затронут
        assert defender1.stats.passes == 1
        assert defender1.stats.goals == 1
    
    def test_yellow_card_removes_pass_when_no_goals(self, setup_match, manager1_id, manager2_id):
        """YELLOW_CARD снимает передачу если голов нет"""
        match, engine, defender1, defender2 = setup_match
        
        # Убираем голы у defender2, добавляем передачу
        defender2.stats.goals = 0
        defender2.add_passes(1)
        # defender2: saves=2, passes=1, goals=0
        
        card = WhistleCard(card_type=CardType.YELLOW_CARD)
        card.applied_by_manager_id = manager1_id
        card.turn_applied = 2
        
        target_player_id = match.current_turn.manager2_player_id
        
        effect = WhistleDeck.get_card_effect(card, match, manager1_id, target_player_id)
        
        assert effect.passes_removed == 1
        assert effect.goals_removed == 0
    
    def test_yellow_card_removes_save_when_no_goals_passes(self, setup_match, manager1_id, manager2_id):
        """YELLOW_CARD снимает отбитие если нет голов и передач"""
        match, engine, defender1, defender2 = setup_match
        
        # defender2: saves=2, goals=0, passes=0
        defender2.stats.goals = 0
        defender2.stats.passes = 0
        
        card = WhistleCard(card_type=CardType.YELLOW_CARD)
        card.applied_by_manager_id = manager1_id
        card.turn_applied = 2
        
        target_player_id = match.current_turn.manager2_player_id
        
        effect = WhistleDeck.get_card_effect(card, match, manager1_id, target_player_id)
        
        assert effect.saves_removed == 1
        assert effect.goals_removed == 0
        assert effect.passes_removed == 0


class TestAutoDrawTargeting:
    """Тесты: автоматическое вытягивание карточки с правильной целью"""
    
    def test_opponent_player_card_targets_opponent(self, setup_match, manager1_id, manager2_id):
        """OPPONENT_PLAYER карточки нацеливаются на игрока соперника"""
        match, engine, defender1, defender2 = setup_match
        
        # Проверяем что get_valid_targets возвращает соперника
        card = WhistleCard(card_type=CardType.RED_CARD)
        
        targets = WhistleDeck.get_valid_targets(card, match, manager1_id)
        
        # Должен вернуть defender2 (игрок соперника)
        assert len(targets) == 1
        assert targets[0].id == defender2.id
    
    def test_self_player_card_targets_own(self, setup_match, manager1_id, manager2_id):
        """SELF_PLAYER карточки нацеливаются на своего игрока"""
        match, engine, defender1, defender2 = setup_match
        
        card = WhistleCard(card_type=CardType.GOAL)
        
        targets = WhistleDeck.get_valid_targets(card, match, manager1_id)
        
        # Должен вернуть defender1 (свой игрок)
        assert len(targets) == 1
        assert targets[0].id == defender1.id


class TestDeckDistribution:
    """Тест: колода содержит 50 карточек"""
    
    def test_deck_has_50_cards(self):
        deck = WhistleDeck.create_deck()
        assert len(deck) == 50
    
    def test_deck_distribution(self):
        deck = WhistleDeck.create_deck()
        counts = {}
        for card in deck:
            counts[card.card_type] = counts.get(card.card_type, 0) + 1
        
        assert counts[CardType.HAT_TRICK] == 1
        assert counts[CardType.DOUBLE] == 1
        assert counts[CardType.GOAL] == 2
        assert counts[CardType.OWN_GOAL] == 2
        assert counts[CardType.VAR] == 2
        assert counts[CardType.OFFSIDE] == 2
        assert counts[CardType.PENALTY] == 3
        assert counts[CardType.RED_CARD] == 2
        assert counts[CardType.YELLOW_CARD] == 3
        assert counts[CardType.FOUL] == 8
        assert counts[CardType.LOSS] == 8
        assert counts[CardType.INTERCEPTION] == 8
        assert counts[CardType.TACKLE] == 8
