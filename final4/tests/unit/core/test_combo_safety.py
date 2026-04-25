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
        После фикса combo-aware валидатор должен предотвращать такой сценарий
        ещё на ходах 7-8, не давая поставить пары, которые исчерпают и квоту голов,
        и бюджет ч/н одновременно.

        Симулируем 11-ходовой матч полным автоплеем, выбирая первый доступный
        игрок и первый доступный тип ставки. Если фикс работает — все 11 ходов
        пройдут, на каждом ходу len(available_players) >= 1.
        """
        import random
        random.seed(123)
        engine, match, m1, m2 = _setup()

        for turn in range(1, 12):
            assert match.current_turn is not None
            assert match.current_turn.turn_number == turn

            for mgr in (m1, m2):
                avail = engine.get_available_players(match, mgr)
                assert len(avail) >= 1, (
                    f"Тупик: ход {turn}, менеджер {mgr}, доступных 0. "
                    f"Это означает что combo-валидатор пропустил ставку, "
                    f"которая создала dead-end."
                )
                player = avail[0]
                required = 1 if turn == 1 else 2
                for _ in range(required):
                    types = engine.get_available_bet_types(match, mgr, player.id)
                    assert types, f"Нет валидных типов для игрока {player.name}"
                    bet = _bet(match.id, mgr, player.id,
                               match.current_turn.turn_number, types[0])
                    match, _ = engine.place_bet(match, mgr, player.id, bet)
                engine.confirm_bets(match, mgr)

            # Кубик
            match, dice, _ = engine.roll_dice(match)
            # Игнорируем yellow card / penalty для упрощения регрессии
            if match.current_turn and match.current_turn.waiting_for_yellow_card_choice:
                match.current_turn.waiting_for_yellow_card_choice = False
                match.current_turn.yellow_card_target_manager_id = None
                match.current_turn.yellow_card_target_player_id = None
                match.current_turn.yellow_card_id = None
            if match.current_turn and match.current_turn.waiting_for_penalty_roll:
                # Отмечаем все нерешённые пенальти как промах
                for card in match.whistle_cards_drawn:
                    if (card.card_type.value == "penalty"
                            and card.penalty_scored is None
                            and card.turn_applied == match.current_turn.turn_number):
                        match, _, _ = engine.resolve_penalty(
                            match, card.applied_by_manager_id, "high"
                        )
                        break
            match = engine.end_turn(match)
            if match.status != MatchStatus.IN_PROGRESS and match.phase == MatchPhase.MAIN_TIME:
                # Матч завершён до 11 ходов — это нормально (досрочная победа)
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
