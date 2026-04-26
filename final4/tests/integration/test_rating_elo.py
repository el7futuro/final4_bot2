"""Тесты ELO-рейтинга и идемпотентности обновления."""

from uuid import uuid4

import pytest

from src.core.models.match import (
    Match, MatchType, MatchStatus, MatchPhase, MatchScore, MatchResult,
)
from src.platforms.telegram.rating import (
    apply_match_rating, _expected_score, _k_factor, DEFAULT_RATING,
)


class _FakeUser:
    def __init__(self, uid, rating=DEFAULT_RATING, matches_played=0, matches_won=0):
        self.id = uid
        self.rating = rating
        self.matches_played = matches_played
        self.matches_won = matches_won


class _FakeStorage:
    def __init__(self, users):
        self._users = {u.id: u for u in users}
        self.saved_users = []
        self.saved_matches = []

    def get_user_by_id(self, uid):
        return self._users.get(uid)

    def update_user_stats(self, user):
        self.saved_users.append(user)

    def save_match(self, match):
        self.saved_matches.append(match)


def _make_finished_match(m1_id, m2_id, winner_id, *, decided_by=MatchPhase.MAIN_TIME):
    """Минимальный завершённый матч с результатом."""
    match = Match(
        match_type=MatchType.RANDOM,
        status=MatchStatus.FINISHED,
        manager1_id=m1_id,
        manager2_id=m2_id,
    )
    loser_id = m2_id if winner_id == m1_id else m1_id
    match.score = MatchScore(manager1_goals=2 if winner_id == m1_id else 1,
                              manager2_goals=2 if winner_id == m2_id else 1)
    match.result = MatchResult(
        winner_id=winner_id,
        loser_id=loser_id,
        final_score=match.score,
        decided_by=decided_by,
    )
    return match


class TestEloFormula:
    def test_k_factor_for_new_player(self):
        assert _k_factor(0) == 32
        assert _k_factor(29) == 32
        assert _k_factor(30) == 24

    def test_expected_score_equal_ratings(self):
        assert abs(_expected_score(1000, 1000) - 0.5) < 1e-9

    def test_expected_score_higher_wins_more_likely(self):
        # 1200 vs 1000 → ожидание у 1200 ~0.76
        e = _expected_score(1200, 1000)
        assert 0.7 < e < 0.8


class TestApplyMatchRating:
    def test_winner_gains_loser_loses(self):
        m1, m2 = uuid4(), uuid4()
        u1 = _FakeUser(m1, rating=1000)
        u2 = _FakeUser(m2, rating=1000)
        storage = _FakeStorage([u1, u2])
        match = _make_finished_match(m1, m2, winner_id=m1)

        deltas = apply_match_rating(storage, match)

        assert deltas is not None
        assert m1 in deltas and m2 in deltas
        assert deltas[m1]["delta"] > 0
        assert deltas[m2]["delta"] < 0
        # Симметрия для равных рейтингов: |delta| одинаковая
        assert abs(deltas[m1]["delta"]) == abs(deltas[m2]["delta"])
        assert u1.matches_played == 1
        assert u1.matches_won == 1
        assert u2.matches_played == 1
        assert u2.matches_won == 0

    def test_idempotent_on_second_call(self):
        m1, m2 = uuid4(), uuid4()
        u1 = _FakeUser(m1, rating=1000)
        u2 = _FakeUser(m2, rating=1000)
        storage = _FakeStorage([u1, u2])
        match = _make_finished_match(m1, m2, winner_id=m1)

        d1 = apply_match_rating(storage, match)
        d2 = apply_match_rating(storage, match)

        assert d1 is not None
        assert d2 is None  # повтор проигнорирован
        assert u1.matches_played == 1  # не удвоилось
        assert match.rating_applied is True

    def test_underdog_win_gives_more_points(self):
        m1, m2 = uuid4(), uuid4()
        # Слабый (800) обыгрывает сильного (1200) — должен получить больше очков
        u1 = _FakeUser(m1, rating=800)
        u2 = _FakeUser(m2, rating=1200)
        storage = _FakeStorage([u1, u2])
        match = _make_finished_match(m1, m2, winner_id=m1)

        deltas = apply_match_rating(storage, match)
        # Победа аутсайдера → большой плюс
        assert deltas[m1]["delta"] >= 24

    def test_skips_bot_user(self):
        from src.core.engine.game_engine import BOT_USER_ID
        m1 = uuid4()
        u1 = _FakeUser(m1, rating=1000)
        storage = _FakeStorage([u1])
        # Матч против бота, человек выиграл
        match = _make_finished_match(m1, BOT_USER_ID, winner_id=m1)

        deltas = apply_match_rating(storage, match)

        # Только человек получает дельту
        assert m1 in deltas
        assert BOT_USER_ID not in deltas
        assert u1.rating > 1000  # Получил +
        assert u1.matches_played == 1
        assert u1.matches_won == 1

    def test_no_op_for_unfinished_match(self):
        m1, m2 = uuid4(), uuid4()
        u1 = _FakeUser(m1, rating=1000)
        u2 = _FakeUser(m2, rating=1000)
        storage = _FakeStorage([u1, u2])
        match = Match(
            match_type=MatchType.RANDOM,
            status=MatchStatus.IN_PROGRESS,  # ещё не закончен
            manager1_id=m1,
            manager2_id=m2,
        )

        result = apply_match_rating(storage, match)
        assert result is None
        assert u1.rating == 1000
        assert u2.rating == 1000

    def test_rating_never_below_zero(self):
        m1, m2 = uuid4(), uuid4()
        u1 = _FakeUser(m1, rating=10)  # очень низкий рейтинг
        u2 = _FakeUser(m2, rating=2000)
        storage = _FakeStorage([u1, u2])
        match = _make_finished_match(m1, m2, winner_id=m2)

        apply_match_rating(storage, match)
        assert u1.rating >= 0
