# src/platforms/telegram/rating.py
"""ELO-рейтинг и обновление статистики пользователей по итогам матча.

Формула ELO:
    expected = 1 / (1 + 10^((opp_rating - my_rating) / 400))
    delta = K * (actual - expected)
    new_rating = old_rating + delta

K-factor:
    32 — новички (matches_played < 30)
    24 — опытные (>= 30)

Идемпотентность: на матче ставится флаг rating_applied=True, повторное
применение игнорируется (защита от race condition timer + manual end_turn).

Бот (BOT_USER_ID) исключён из подсчёта.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.core.engine.game_engine import BOT_USER_ID
from src.core.models.match import Match

logger = logging.getLogger(__name__)

DEFAULT_RATING = 1000


def _k_factor(matches_played: int) -> int:
    return 32 if matches_played < 30 else 24


def _expected_score(my_rating: int, opp_rating: int) -> float:
    return 1.0 / (1.0 + 10 ** ((opp_rating - my_rating) / 400.0))


def apply_match_rating(storage, match: Match) -> Optional[dict]:
    """Применить рейтинговые изменения по итогам завершённого матча.

    Returns:
        dict с deltas {manager_id: {old, new, delta}} либо None если матч 
        ещё не финиширован / уже обработан / нет результата.
    """
    if match.status.value != "finished" or not match.result:
        return None
    if match.rating_applied:
        return None

    winner_id = match.result.winner_id
    loser_id = match.result.loser_id
    if not winner_id or not loser_id:
        match.rating_applied = True  # Метим, чтобы не пытаться снова
        return None

    winner_user = storage.get_user_by_id(winner_id) if winner_id != BOT_USER_ID else None
    loser_user = storage.get_user_by_id(loser_id) if loser_id != BOT_USER_ID else None

    deltas = {}

    # Рейтинг для расчёта (если соперник — бот, считаем его рейтинг = DEFAULT_RATING)
    winner_rating = winner_user.rating if winner_user else DEFAULT_RATING
    loser_rating = loser_user.rating if loser_user else DEFAULT_RATING

    # Победитель
    if winner_user:
        k = _k_factor(winner_user.matches_played)
        expected = _expected_score(winner_user.rating, loser_rating)
        delta = round(k * (1.0 - expected))
        delta = max(1, delta)  # минимум +1 за победу
        old = winner_user.rating
        winner_user.rating = max(0, old + delta)
        winner_user.matches_played += 1
        winner_user.matches_won += 1
        deltas[winner_id] = {"old": old, "new": winner_user.rating, "delta": delta}
        try:
            storage.update_user_stats(winner_user)
        except Exception as e:
            logger.warning(f"[RATING] update_user_stats(winner) failed: {e}")

    # Проигравший
    if loser_user:
        k = _k_factor(loser_user.matches_played)
        expected = _expected_score(loser_user.rating, winner_rating)
        delta = round(k * (0.0 - expected))  # отрицательное
        delta = min(-1, delta)  # минимум -1 за поражение
        old = loser_user.rating
        loser_user.rating = max(0, old + delta)
        loser_user.matches_played += 1
        deltas[loser_id] = {"old": old, "new": loser_user.rating, "delta": delta}
        try:
            storage.update_user_stats(loser_user)
        except Exception as e:
            logger.warning(f"[RATING] update_user_stats(loser) failed: {e}")

    # Помечаем матч как обработанный
    match.rating_applied = True
    try:
        storage.save_match(match)
    except Exception as e:
        logger.warning(f"[RATING] save_match (rating_applied) failed: {e}")

    logger.info(
        f"[RATING] Match {match.id} applied: "
        + ", ".join(
            f"{uid}: {d['old']}→{d['new']} ({d['delta']:+d})" for uid, d in deltas.items()
        )
    )
    return deltas
