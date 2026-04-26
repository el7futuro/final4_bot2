# src/platforms/telegram/turn_timer.py
"""Таймер хода: автоматические случайные ставки при таймауте.

Лимит 60 секунд на ход. Если игрок не успел сделать и подтвердить ставки —
за него ставки делает рандомизатор (та же логика, что у бота),
после чего ход продолжается автоматически.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from uuid import UUID

from src.core.engine.game_engine import BOT_USER_ID
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice
from src.core.models.match import MatchPhase, MatchStatus

logger = logging.getLogger(__name__)

TURN_TIMEOUT_SECONDS = 60


class TurnTimerManager:
    """Управляет фоновыми задачами-таймерами по матчам."""

    def __init__(self):
        self._tasks: Dict[Tuple[UUID, int], asyncio.Task] = {}

    def cancel(self, match_id: UUID, turn_number: Optional[int] = None) -> None:
        """Отменить таймер. Если turn_number=None — отменить все таймеры этого матча."""
        keys_to_remove = []
        for key in list(self._tasks.keys()):
            mid, tn = key
            if mid == match_id and (turn_number is None or tn == turn_number):
                task = self._tasks[key]
                if not task.done():
                    task.cancel()
                keys_to_remove.append(key)
        for k in keys_to_remove:
            self._tasks.pop(k, None)

    def schedule(self, bot, storage, match_id: UUID, turn_number: int) -> None:
        """Запланировать таймер на текущий ход. Перезапишет существующий для этой пары."""
        # Отменяем старый, если был
        self.cancel(match_id, turn_number)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # Не в async контексте — не создаём
        task = loop.create_task(
            _turn_timeout_task(bot, storage, match_id, turn_number)
        )
        self._tasks[(match_id, turn_number)] = task


_manager: Optional[TurnTimerManager] = None


def get_timer_manager() -> TurnTimerManager:
    global _manager
    if _manager is None:
        _manager = TurnTimerManager()
    return _manager


def arm_turn_timer(bot, storage, match) -> None:
    """Установить дедлайн на текущем ходу матча и запустить таймер.

    Безопасно вызывать после каждого перехода на новый ход (start_match,
    end_turn → следующий ход, переход в Extra Time).
    """
    if not match.current_turn:
        return
    if match.status not in (MatchStatus.IN_PROGRESS, MatchStatus.EXTRA_TIME):
        return
    deadline = datetime.now(timezone.utc) + timedelta(seconds=TURN_TIMEOUT_SECONDS)
    match.current_turn.turn_deadline_at = deadline
    storage.save_match(match)
    get_timer_manager().schedule(bot, storage, match.id, match.current_turn.turn_number)
    logger.info(f"[TIMER] Armed turn {match.current_turn.turn_number} for match {match.id}, deadline {deadline.isoformat()}")


def cancel_match_timers(match_id: UUID) -> None:
    """Отменить все таймеры матча (при завершении или отмене)."""
    get_timer_manager().cancel(match_id)


async def _turn_timeout_task(bot, storage, match_id: UUID, turn_number: int):
    """Фоновая задача: ждёт TURN_TIMEOUT_SECONDS, затем автоставит за неготовых."""
    try:
        await asyncio.sleep(TURN_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        return

    try:
        await _execute_timeout(bot, storage, match_id, turn_number)
    except Exception as e:
        logger.exception(f"[TIMER] Timeout handler failed for match {match_id} turn {turn_number}: {e}")


async def _execute_timeout(bot, storage, match_id: UUID, turn_number: int):
    """Выполнить автоставки и продолжить ход."""
    match = storage.get_match(match_id)
    if not match:
        return
    if match.status not in (MatchStatus.IN_PROGRESS, MatchStatus.EXTRA_TIME):
        return
    if not match.current_turn or match.current_turn.turn_number != turn_number:
        return  # Уже сменился ход

    engine = storage.engine

    # Определяем, кто ещё не подтвердил ставки
    timed_out_managers: list = []
    if not match.current_turn.manager1_ready:
        timed_out_managers.append(match.manager1_id)
    if (
        not match.current_turn.manager2_ready
        and match.manager2_id is not None
        and match.manager2_id != BOT_USER_ID  # бот сам себе автоставит
    ):
        timed_out_managers.append(match.manager2_id)

    if not timed_out_managers:
        return  # Уже всё готово

    logger.info(f"[TIMER] Turn {turn_number} timeout — auto-betting for {len(timed_out_managers)} manager(s)")

    # Автоставки за просрочивших (та же логика, что у бота)
    for mgr_id in timed_out_managers:
        try:
            _auto_random_bets_for_manager(engine, match, mgr_id)
        except Exception as e:
            logger.exception(f"[TIMER] Auto-bets failed for {mgr_id}: {e}")

    # Если соперник — vs_bot и бот ещё не сделал ставки, его автоставит штатная логика
    # после нашего confirm_bets (там есть проверка `match_type == vs_bot` в cb_confirm_bets,
    # но мы не в callback'е, поэтому продублируем здесь).
    from src.platforms.telegram.handlers.game import _bot_make_bets
    if (
        match.match_type.value == "vs_bot"
        and match.current_turn
        and not match.current_turn.manager2_ready
    ):
        try:
            match = _bot_make_bets(storage, match)
        except Exception as e:
            logger.exception(f"[TIMER] Bot make_bets failed: {e}")

    storage.save_match(match)

    # Бросаем кубик автоматически (только если оба готовы)
    can_roll, _ = engine.can_roll_dice(match)
    if can_roll:
        try:
            match, dice, _won = engine.roll_dice(match)
        except Exception as e:
            logger.exception(f"[TIMER] roll_dice failed: {e}")
            dice = None
        else:
            storage.save_match(match)
            # Резолвим жёлтую карточку (выбор атакуемой статы) и пенальти автоматически
            await _auto_resolve_post_dice(engine, storage, match)
    else:
        dice = None

    # Уведомляем участников
    await _notify_timeout(bot, storage, match, turn_number, timed_out_managers, dice)


def _auto_random_bets_for_manager(engine, match, manager_id: UUID) -> None:
    """Случайные ставки за конкретного менеджера (используется при таймауте)."""
    available = engine.get_available_players(match, manager_id)
    if not available:
        # Подтвердить ставки нельзя без игроков — пропускаем; ход останется висеть,
        # но это аномальная ситуация (combo-валидатор не должен её допускать).
        return
    player = random.choice(available)
    turn_num = match.current_turn.turn_number if match.current_turn else 1
    required_bets = (
        2 if match.phase == MatchPhase.EXTRA_TIME else (1 if turn_num == 1 else 2)
    )

    for _ in range(required_bets):
        types = engine.get_available_bet_types(match, manager_id, player.id)
        if not types:
            break
        bt = random.choice(types)
        kwargs = {
            "match_id": match.id,
            "manager_id": manager_id,
            "player_id": player.id,
            "turn_number": turn_num,
            "bet_type": bt,
        }
        if bt == BetType.EVEN_ODD:
            kwargs["even_odd_choice"] = random.choice(
                [EvenOddChoice.EVEN, EvenOddChoice.ODD]
            )
        elif bt == BetType.HIGH_LOW:
            kwargs["high_low_choice"] = random.choice(
                [HighLowChoice.HIGH, HighLowChoice.LOW]
            )
        elif bt == BetType.EXACT_NUMBER:
            kwargs["exact_number"] = random.randint(1, 6)
        try:
            engine.place_bet(match, manager_id, player.id, Bet(**kwargs))
        except ValueError as e:
            logger.warning(f"[TIMER] place_bet failed for {manager_id}: {e}")
            break

    try:
        engine.confirm_bets(match, manager_id)
    except ValueError as e:
        logger.warning(f"[TIMER] confirm_bets failed for {manager_id}: {e}")


async def _auto_resolve_post_dice(engine, storage, match) -> None:
    """Авто-разрешение жёлтой карточки и пенальти после броска кубика при таймауте."""
    if not match.current_turn:
        return

    # Жёлтая карточка — берём первое доступное действие
    if match.current_turn.waiting_for_yellow_card_choice:
        target_mgr = match.current_turn.yellow_card_target_manager_id
        target_pid = match.current_turn.yellow_card_target_player_id
        target_team = match.get_team(target_mgr) if target_mgr else None
        if target_team and target_pid:
            tp = target_team.get_player_by_id(target_pid)
            if tp:
                if tp.stats.saves > 0:
                    match = engine.resolve_yellow_card(match, target_mgr, "save")
                elif tp.stats.passes > 0:
                    match = engine.resolve_yellow_card(match, target_mgr, "pass")
                elif tp.stats.goals > 0:
                    match = engine.resolve_yellow_card(match, target_mgr, "goal")
                else:
                    match.current_turn.waiting_for_yellow_card_choice = False

    # Пенальти-карточка — авто-выбор "high"
    if match.current_turn.waiting_for_penalty_roll:
        from src.core.models.whistle_card import CardType
        for card in match.whistle_cards_drawn:
            if (
                card.card_type == CardType.PENALTY
                and card.penalty_scored is None
                and card.turn_applied == match.current_turn.turn_number
            ):
                try:
                    match, _scored, _dice = engine.resolve_penalty(
                        match, card.applied_by_manager_id, "high"
                    )
                except ValueError as e:
                    logger.warning(f"[TIMER] resolve_penalty failed: {e}")
                break

    storage.save_match(match)


async def _notify_timeout(bot, storage, match, turn_number, timed_out_managers, dice):
    """Уведомить участников о таймауте и текущем состоянии."""
    text_base = (
        f"⏱ <b>Время вышло (60 сек)!</b>\n\n"
        f"Ставки сделаны автоматически за тех, кто не успел.\n"
    )
    if dice is not None:
        text_base += f"🎲 Кубик брошен: <b>{dice}</b>\n"

    # Получаем telegram_id участников
    for mgr_id in [match.manager1_id, match.manager2_id]:
        if mgr_id is None or mgr_id == BOT_USER_ID:
            continue
        user = storage.get_user_by_id(mgr_id)
        if not user or not user.telegram_id:
            continue
        try:
            you_timed_out = mgr_id in timed_out_managers
            text = text_base + (
                "⚠️ Вы не успели подтвердить ставки.\n"
                if you_timed_out
                else "ℹ️ Соперник не успел подтвердить ставки.\n"
            )
            text += f"\nХод #{turn_number}. Откройте матч, чтобы продолжить."
            await bot.send_message(chat_id=user.telegram_id, text=text)
        except Exception as e:
            logger.warning(f"[TIMER] Failed to notify {mgr_id}: {e}")
