"""Регрессия логики жёлтой карточки.

Правило: жёлтая карточка применяется к игроку ТОГО, кто её вытянул (СВОЕМУ).
Соперник владельца игрока выбирает, какое действие убрать.
"""

from uuid import uuid4

from src.core.engine.game_engine import GameEngine
from src.core.engine.whistle_deck import WhistleDeck
from src.core.models.match import (
    Match, MatchType, MatchStatus, MatchPhase, TurnState,
)
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.whistle_card import WhistleCard, CardType, CardEffect, CardTarget


def _make_team(mgr_id, prefix):
    players = [Player(name=f"{prefix}-GK", position=Position.GOALKEEPER, number=1)]
    n = 2
    for i in range(5):
        players.append(Player(name=f"{prefix}-DF{i+1}", position=Position.DEFENDER, number=n)); n += 1
    for i in range(6):
        players.append(Player(name=f"{prefix}-MF{i+1}", position=Position.MIDFIELDER, number=n)); n += 1
    for i in range(4):
        players.append(Player(name=f"{prefix}-FW{i+1}", position=Position.FORWARD, number=n)); n += 1
    return Team(manager_id=mgr_id, name=f"{prefix} Team", players=players)


def _setup():
    engine = GameEngine()
    m1, m2 = uuid4(), uuid4()
    match = engine.create_match(m1, MatchType.RANDOM)
    match.manager2_id = m2
    match.status = MatchStatus.IN_PROGRESS
    match.team1 = _make_team(m1, "T1")
    match.team2 = _make_team(m2, "T2")
    match.current_turn = TurnState(turn_number=2)
    return engine, match, m1, m2


class TestYellowCardOwnership:
    def test_target_type_is_self_player(self):
        """CardTarget для YELLOW_CARD должен быть SELF_PLAYER."""
        from src.core.models.whistle_card import CARD_TARGETS
        assert CARD_TARGETS[CardType.YELLOW_CARD] == CardTarget.SELF_PLAYER

    def test_yellow_card_targets_own_player_chooser_is_opponent(self):
        """
        M1 вытягивает жёлтую карточку → target_player_id = игрок M1,
        chooser (yellow_card_target_manager_id) = M2.
        """
        engine, match, m1, m2 = _setup()
        # M1 ставит на своего DF
        df_m1 = match.team1.players[1]
        match.current_turn.manager1_player_id = df_m1.id
        # У игрока есть действия (имитация)
        df_m1.stats.passes = 2
        df_m1.stats.saves = 1

        # Эффект жёлтой карточки на M1
        card = WhistleCard(card_type=CardType.YELLOW_CARD)
        effect = CardEffect(
            card_id=card.id,
            card_type=CardType.YELLOW_CARD,
            target_player_id=df_m1.id,
            requires_yellow_card_choice=True,
        )
        WhistleDeck.apply_effect(match, effect, history=None)

        # Целевой игрок остался M1's
        assert match.current_turn.yellow_card_target_player_id == df_m1.id
        # Выбирает СОПЕРНИК (M2)
        assert match.current_turn.yellow_card_target_manager_id == m2
        assert match.current_turn.waiting_for_yellow_card_choice is True

    def test_resolve_yellow_card_finds_player_in_owner_team(self):
        """resolve_yellow_card должен искать игрока в обеих командах."""
        engine, match, m1, m2 = _setup()
        df_m1 = match.team1.players[1]
        df_m1.stats.passes = 2
        df_m1.stats.saves = 1

        card = WhistleCard(card_type=CardType.YELLOW_CARD)
        effect = CardEffect(
            card_id=card.id,
            card_type=CardType.YELLOW_CARD,
            target_player_id=df_m1.id,
            requires_yellow_card_choice=True,
        )
        WhistleDeck.apply_effect(match, effect, history=None)

        # M2 (выбирающий) убирает 'pass' у M1's игрока
        match = engine.resolve_yellow_card(match, m2, "pass")

        assert df_m1.stats.passes == 1  # было 2, стало 1
        assert df_m1.stats.saves == 1  # не тронут
        assert match.current_turn.waiting_for_yellow_card_choice is False

    def test_resolve_yellow_card_only_chooser_can_resolve(self):
        """Владелец игрока (M1) не может разрешить — может только M2."""
        import pytest
        engine, match, m1, m2 = _setup()
        df_m1 = match.team1.players[1]
        df_m1.stats.passes = 1

        card = WhistleCard(card_type=CardType.YELLOW_CARD)
        effect = CardEffect(
            card_id=card.id,
            card_type=CardType.YELLOW_CARD,
            target_player_id=df_m1.id,
            requires_yellow_card_choice=True,
        )
        WhistleDeck.apply_effect(match, effect, history=None)

        # M1 пытается → ошибка "Не ваш выбор"
        with pytest.raises(ValueError, match="Не ваш выбор"):
            engine.resolve_yellow_card(match, m1, "pass")

    def test_yellow_card_no_effect_if_no_actions(self):
        """Если у целевого игрока 0 действий — resolve упадёт. UI handler в game.py
        обнуляет флаги ожидания и сообщает «нет действий — карточка не повлияла»."""
        import pytest
        engine, match, m1, m2 = _setup()
        df_m1 = match.team1.players[1]
        # Все статы = 0
        assert df_m1.stats.goals == 0
        assert df_m1.stats.passes == 0
        assert df_m1.stats.saves == 0

        card = WhistleCard(card_type=CardType.YELLOW_CARD)
        effect = CardEffect(
            card_id=card.id,
            card_type=CardType.YELLOW_CARD,
            target_player_id=df_m1.id,
            requires_yellow_card_choice=True,
        )
        WhistleDeck.apply_effect(match, effect, history=None)

        # Любой action_type должен упасть на проверке наличия
        with pytest.raises(ValueError):
            engine.resolve_yellow_card(match, m2, "save")
