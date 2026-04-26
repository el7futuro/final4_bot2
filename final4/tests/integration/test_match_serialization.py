"""Регрессионный тест: round-trip сериализации Match → JSONB → Match.

Цель: убедиться что после сохранения матча в БД и загрузки обратно
через `MatchRepository._to_domain` все поля, нужные для рендера истории
(bets, used_players_*, whistle_cards_drawn, penalty_results, score,
team1/team2 snapshots, current_turn) восстанавливаются корректно.

Это предотвращает регрессию бага "История не работает после миграции на БД",
не требуя живой PostgreSQL — мы воспроизводим сериализацию через
model_dump(mode='json') (то же самое что хранится в JSONB) и десериализацию
через `_to_domain` в обход БД.
"""
import json
from uuid import uuid4
from datetime import datetime, timezone

import pytest

from src.core.engine.game_engine import GameEngine
from src.core.models.match import (
    Match, MatchType, MatchStatus, MatchPhase, MatchScore, MatchResult,
    PenaltyKick, TurnState,
)
from src.core.models.player import Player, Position
from src.core.models.team import Team
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice
from src.core.models.whistle_card import WhistleCard


def _make_team(mgr_id, prefix):
    players = [Player(name=f'{prefix}-GK', position=Position.GOALKEEPER, number=1)]
    n = 2
    for i in range(5):
        players.append(Player(name=f'{prefix}-DF{i+1}', position=Position.DEFENDER, number=n)); n += 1
    for i in range(6):
        players.append(Player(name=f'{prefix}-MF{i+1}', position=Position.MIDFIELDER, number=n)); n += 1
    for i in range(4):
        players.append(Player(name=f'{prefix}-FW{i+1}', position=Position.FORWARD, number=n)); n += 1
    return Team(manager_id=mgr_id, name=f'{prefix} Team', players=players)


def _build_match_with_history():
    """Создать матч с заполненной историей (ставки, использованные игроки, пенальти)."""
    engine = GameEngine()
    m1 = uuid4(); m2 = uuid4()
    match = engine.create_match(m1, MatchType.RANDOM)
    match.manager2_id = m2
    match.status = MatchStatus.IN_PROGRESS
    match.team1 = _make_team(m1, 'T1')
    match.team2 = _make_team(m2, 'T2')

    # Несколько ставок
    p1 = match.team1.players[0]  # GK
    bet1 = Bet(
        id=uuid4(), match_id=match.id, manager_id=m1, player_id=p1.id,
        turn_number=1, bet_type=BetType.EVEN_ODD,
        even_odd_choice=EvenOddChoice.EVEN, dice_roll=4,
    )
    match.bets.append(bet1)
    match.used_players_main_m1.append(str(p1.id))

    p2 = match.team1.players[6]  # MF1
    bet2 = Bet(
        id=uuid4(), match_id=match.id, manager_id=m1, player_id=p2.id,
        turn_number=2, bet_type=BetType.HIGH_LOW,
        high_low_choice=HighLowChoice.HIGH, dice_roll=5,
    )
    match.bets.append(bet2)
    match.used_players_main_m1.append(str(p2.id))

    # Пенальти
    match.penalty_results = [
        PenaltyKick(manager_id=m1, player_name='T1-FW1', scored=True),
        PenaltyKick(manager_id=m2, player_name='T2-FW1', scored=False),
        PenaltyKick(manager_id=m1, player_name='T1-FW2', scored=True, sudden_death=True),
        PenaltyKick(manager_id=m2, player_name='T2-FW2', scored=False, sudden_death=True),
    ]
    match.penalty_score_m1 = 2
    match.penalty_score_m2 = 0

    # Завершён с результатом
    match.status = MatchStatus.FINISHED
    match.score = MatchScore(manager1_goals=2, manager2_goals=2)
    match.result = MatchResult(
        winner_id=m1,
        loser_id=m2,
        final_score=match.score,
        decided_by=MatchPhase.PENALTIES,
        decided_by_lottery=False,
    )
    match.finished_at = datetime.now(timezone.utc)
    match.current_turn = TurnState(turn_number=11)
    return match


def _serialize_to_jsonb_dict(match: Match) -> dict:
    """Сериализовать матч так же, как делает _db_save_match для записи в JSONB."""
    return {
        "id": match.id,
        "match_type": match.match_type.value,
        "status": match.status.value,
        "phase": match.phase.value,
        "manager1_id": match.manager1_id,
        "manager2_id": match.manager2_id,
        "team1_snapshot": match.team1.model_dump(mode='json') if match.team1 else None,
        "team2_snapshot": match.team2.model_dump(mode='json') if match.team2 else None,
        "current_turn": match.current_turn.model_dump(mode='json') if match.current_turn else None,
        "total_turns_main": match.total_turns_main,
        "total_turns_extra": match.total_turns_extra,
        "used_players_main_m1": list(match.used_players_main_m1),
        "used_players_main_m2": list(match.used_players_main_m2),
        "used_players_extra_m1": list(match.used_players_extra_m1),
        "used_players_extra_m2": list(match.used_players_extra_m2),
        "whistle_deck": [c.model_dump(mode='json') for c in match.whistle_deck],
        "whistle_cards_drawn": [c.model_dump(mode='json') for c in match.whistle_cards_drawn],
        "bets": [b.model_dump(mode='json') for b in match.bets],
        "score_manager1": match.score.manager1_goals,
        "score_manager2": match.score.manager2_goals,
        "winner_id": match.result.winner_id if match.result else None,
        "loser_id": match.result.loser_id if match.result else None,
        "decided_by": match.result.decided_by.value if match.result else None,
        "decided_by_lottery": match.result.decided_by_lottery if match.result else False,
        "penalty_results": [p.model_dump(mode='json') for p in match.penalty_results],
        "penalty_score_m1": match.penalty_score_m1,
        "penalty_score_m2": match.penalty_score_m2,
        "platform": match.platform,
        "created_at": match.created_at,
        "started_at": match.started_at,
        "finished_at": match.finished_at,
    }


class _FakeModel:
    """Имитация SQLAlchemy MatchModel со всеми полями из словаря."""
    def __init__(self, data: dict):
        for key, value in data.items():
            # Имитируем JSONB round-trip через json.dumps/loads только для dict/list
            if isinstance(value, (dict, list)):
                value = json.loads(json.dumps(value, default=str))
            setattr(self, key, value)


class TestMatchSerializationRoundTrip:
    """Round-trip Match -> dict (JSONB) -> Match через _to_domain."""

    def test_finished_match_roundtrip_preserves_history_fields(self):
        from src.infrastructure.repositories.match_repository import MatchRepository

        original = _build_match_with_history()
        data = _serialize_to_jsonb_dict(original)
        # Имитируем JSONB → dict (UUID → str)
        model = _FakeModel(data)

        # _to_domain не использует session-методы, поэтому передаём None
        repo = MatchRepository(session=None)  # session нужен только для CRUD
        restored = repo._to_domain(model)

        # Базовые поля
        assert restored.id == original.id
        assert restored.status == original.status
        assert restored.manager1_id == original.manager1_id
        assert restored.manager2_id == original.manager2_id

        # Команды
        assert restored.team1 is not None
        assert restored.team2 is not None
        assert len(restored.team1.players) == len(original.team1.players)
        assert restored.team1.players[0].name == original.team1.players[0].name
        assert restored.team1.players[0].position == original.team1.players[0].position

        # Ставки
        assert len(restored.bets) == len(original.bets)
        assert restored.bets[0].bet_type == original.bets[0].bet_type
        assert restored.bets[0].player_id == original.bets[0].player_id
        assert restored.bets[0].turn_number == 1
        assert restored.bets[0].dice_roll == 4

        # Использованные игроки
        assert restored.used_players_main_m1 == list(original.used_players_main_m1)

        # Счёт
        assert restored.score.manager1_goals == 2
        assert restored.score.manager2_goals == 2

        # Результат
        assert restored.result is not None
        assert restored.result.winner_id == original.result.winner_id
        assert restored.result.decided_by == MatchPhase.PENALTIES

        # Серия пенальти (включая sudden_death)
        assert len(restored.penalty_results) == 4
        assert restored.penalty_results[0].player_name == 'T1-FW1'
        assert restored.penalty_results[0].scored is True
        assert restored.penalty_results[0].sudden_death is False
        assert restored.penalty_results[2].sudden_death is True
        assert restored.penalty_score_m1 == 2

    def test_render_match_history_works_after_roundtrip(self):
        """Главное: после round-trip render_match_history не падает и возвращает текст."""
        from src.infrastructure.repositories.match_repository import MatchRepository
        from src.platforms.telegram.renderers.match_renderer import MatchRenderer

        original = _build_match_with_history()
        data = _serialize_to_jsonb_dict(original)
        model = _FakeModel(data)
        repo = MatchRepository(session=None)
        restored = repo._to_domain(model)

        # Рендер истории — это и есть то, что показывает кнопка "История"
        text = MatchRenderer.render_match_history(restored, viewer_id=original.manager1_id)
        assert text  # не пустая
        assert "ИСТОРИЯ МАТЧА" in text
        # Пенальти секция должна быть
        assert "СЕРИЯ ПЕНАЛЬТИ" in text
        assert "T1-FW1" in text
        # Sudden death секция должна быть (т.к. в данных есть sudden_death=True)
        assert "Серия до промаха" in text
