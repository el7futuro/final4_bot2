# tests/unit/core/test_combo_safety.py
"""Регрессионные тесты для combo-aware валидации ставок.

Проблема: раньше валидатор проверял каждый тип ставки по отдельности 
(_even_odd_safe_for_future, _goal_safe_for_future), но не симулировал 
ОБЕ ставки одновременно. Это приводило к тупикам, когда обе ставки 
по отдельности безопасны, но вместе создают тупик к концу основного времени.
"""

from uuid import uuid4

from src.core.engine.game_engine import GameEngine
from src.core.models.match import (
    Match, MatchType, MatchStatus, MatchPhase, TurnState
)
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice


def _bet(match_id, manager_id, player_id, turn_number, bet_type, **extra):
    kwargs = dict(
        id=uuid4(), match_id=match_id, manager_id=manager_id,
        player_id=player_id, turn_number=turn_number, bet_type=bet_type,
    )
    if bet_type == BetType.EVEN_ODD:
        kwargs["even_odd_choice"] = extra.get("even_odd_choice", EvenOddChoice.EVEN)
    elif bet_type == BetType.HIGH_LOW:
        kwargs["high_low_choice"] = extra.get("high_low_choice", HighLowChoice.HIGH)
    elif bet_type == BetType.EXACT_NUMBER:
        kwargs["exact_number"] = extra.get("exact_number", 1)
    return Bet(**kwargs)


def _make_team(mgr_id, prefix):
    players = [Player(name=f"{prefix}-GK", position=Position.GOALKEEPER, number=1)]
    for i in range(5):
        players.append(Player(name=f"{prefix}-DF{i+1}", position=Position.DEFENDER, number=2 + i))
    for i in range(6):
        players.append(Player(name=f"{prefix}-MF{i+1}", position=Position.MIDFIELDER, number=7 + i))
    for i in range(4):
        players.append(Player(name=f"{prefix}-FW{i+1}", position=Position.FORWARD, number=13 + i))
    return Team(manager_id=mgr_id, name=f"{prefix} Team", players=players)


def _setup():
    engine = GameEngine()
    m1 = uuid4(); m2 = uuid4()
    match = engine.create_match(m1, MatchType.RANDOM)
    match.manager2_id = m2
    match.status = MatchStatus.SETTING_LINEUP
    match = engine.set_team_without_formation(match, m1, _make_team(m1, "T1"))
    match = engine.set_team_without_formation(match, m2, _make_team(m2, "T2"))
    return engine, match, m1, m2


class TestComboFutureSafety:
    def test_no_deadlock_at_turn_9(self):
        """
        Регрессия из логов: к ходу 9 m1 имел 0 доступных игроков из 8 оставшихся.
        После фикса combo-aware валидатор должен предотвращать такой сценарий.

        Прогоняем 50 случайных автоплеев — ни на одном ходу не должно возникнуть
        "Available players: 0" в основном времени.
        """
        import random
        for seed in range(50):
            random.seed(seed)
            engine, match, m1, m2 = _setup()

            for turn in range(1, 12):
                if match.phase != MatchPhase.MAIN_TIME:
                    break
                assert match.current_turn is not None
                assert match.current_turn.turn_number == turn

                for mgr in (m1, m2):
                    avail = engine.get_available_players(match, mgr)
                    assert len(avail) >= 1, (
                        f"[seed={seed}] Тупик: ход {turn}, mgr {mgr}, доступных 0"
                    )
                    player = random.choice(avail)
                    required = 1 if turn == 1 else 2
                    for _ in range(required):
                        types = engine.get_available_bet_types(match, mgr, player.id)
                        assert types, (
                            f"[seed={seed}] Нет валидных типов для {player.name}"
                        )
                        bt = random.choice(types)
                        bet = _bet(match.id, mgr, player.id,
                                   match.current_turn.turn_number, bt)
                        match, _ = engine.place_bet(match, mgr, player.id, bet)
                    engine.confirm_bets(match, mgr)

                match, _, _ = engine.roll_dice(match)
                if match.current_turn and match.current_turn.waiting_for_yellow_card_choice:
                    match.current_turn.waiting_for_yellow_card_choice = False
                    match.current_turn.yellow_card_target_manager_id = None
                    match.current_turn.yellow_card_target_player_id = None
                    match.current_turn.yellow_card_id = None
                if match.current_turn and match.current_turn.waiting_for_penalty_roll:
                    for card in match.whistle_cards_drawn:
                        if (card.card_type.value == "penalty"
                                and card.penalty_scored is None
                                and card.turn_applied == match.current_turn.turn_number):
                            match, _, _ = engine.resolve_penalty(
                                match, card.applied_by_manager_id, "high"
                            )
                            break
                match = engine.end_turn(match)
                if match.status != MatchStatus.IN_PROGRESS:
                    break

    def test_simulate_bets_safe_for_future_returns_bool(self):
        engine, match, m1, _ = _setup()
        match.current_turn = TurnState(turn_number=2)
        df = next(p for p in match.team1.players if p.position == Position.DEFENDER)
        result = engine.bet_tracker._simulate_bets_safe_for_future(
            match, m1, df, [BetType.EVEN_ODD, BetType.HIGH_LOW]
        )
        assert isinstance(result, bool)

    def test_pair_rules_validity_basic(self):
        engine, match, m1, _ = _setup()
        match.current_turn = TurnState(turn_number=2)
        df = next(p for p in match.team1.players if p.position == Position.DEFENDER)
        fw = next(p for p in match.team1.players if p.position == Position.FORWARD)

        # FW не может ставить EVEN_ODD
        assert not engine.bet_tracker._is_pair_rules_valid(
            match, m1, fw, BetType.EVEN_ODD, BetType.HIGH_LOW
        )
        # DF может EO+HL
        assert engine.bet_tracker._is_pair_rules_valid(
            match, m1, df, BetType.EVEN_ODD, BetType.HIGH_LOW
        )
        # Две одинаковые (не EXACT) запрещены
        assert not engine.bet_tracker._is_pair_rules_valid(
            match, m1, df, BetType.HIGH_LOW, BetType.HIGH_LOW
        )
        # Две EXACT для DF — нельзя (квота 1)
        assert not engine.bet_tracker._is_pair_rules_valid(
            match, m1, df, BetType.EXACT_NUMBER, BetType.EXACT_NUMBER
        )
