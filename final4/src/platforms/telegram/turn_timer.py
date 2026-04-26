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
        self._tickers: Dict[Tuple[UUID, int], asyncio.Task] = {}
        # (match_id, telegram_id) -> message_id таймер-сообщения
        self._timer_messages: Dict[Tuple[UUID, int], int] = {}
        self._bot = None

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

        # Также отменяем тикеры
        ticker_keys = []
        for key in list(self._tickers.keys()):
            mid, tn = key
            if mid == match_id and (turn_number is None or tn == turn_number):
                t = self._tickers[key]
                if not t.done():
                    t.cancel()
                ticker_keys.append(key)
        for k in ticker_keys:
            self._tickers.pop(k, None)

        # И запускаем удаление таймер-сообщений из чатов
        if self._bot is not None:
            asyncio.create_task(self._delete_timer_messages(match_id))

    async def _delete_timer_messages(self, match_id: UUID) -> None:
        """Удалить таймер-сообщения у участников этого матча."""
        keys = [k for k in self._timer_messages.keys() if k[0] == match_id]
        for key in keys:
            _, telegram_id = key
            msg_id = self._timer_messages.pop(key, None)
            if not msg_id or self._bot is None:
                continue
            try:
                await self._bot.delete_message(chat_id=telegram_id, message_id=msg_id)
            except Exception:
                pass

    def schedule(self, bot, storage, match_id: UUID, turn_number: int) -> None:
        """Запланировать таймер на текущий ход. Перезапишет существующий."""
        self._bot = bot
        # Отменяем старые таймеры/тикеры этого матча (новый ход → всё сбрасывается)
        self.cancel(match_id)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(
            _turn_timeout_task(bot, storage, match_id, turn_number)
        )
        self._tasks[(match_id, turn_number)] = task
        # Запускаем тикер
        ticker = loop.create_task(
            _ticker_task(bot, storage, match_id, turn_number)
        )
        self._tickers[(match_id, turn_number)] = ticker

    def get_timer_message_id(self, match_id: UUID, telegram_id: int) -> Optional[int]:
        return self._timer_messages.get((match_id, telegram_id))

    def set_timer_message_id(self, match_id: UUID, telegram_id: int, msg_id: int) -> None:
        self._timer_messages[(match_id, telegram_id)] = msg_id


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


async def _ticker_task(bot, storage, match_id: UUID, turn_number: int):
    """Живой обратный отсчёт: отдельное сообщение, тикающее каждые 15 сек."""
    mgr = get_timer_manager()
    # Получаем актуальный матч и список участников-людей
    match = storage.get_match(match_id)
    if not match:
        return
    participants = []
    for uid in [match.manager1_id, match.manager2_id]:
        if uid is None or uid == BOT_USER_ID:
            continue
        u = storage.get_user_by_id(uid)
        if u and u.telegram_id:
            participants.append((uid, u.telegram_id))

    # Шаг 1: отправляем стартовое сообщение
    initial_text = _format_timer_text(turn_number, TURN_TIMEOUT_SECONDS)
    for _uid, tg_id in participants:
        try:
            msg = await bot.send_message(chat_id=tg_id, text=initial_text)
            mgr.set_timer_message_id(match_id, tg_id, msg.message_id)
        except Exception as e:
            logger.warning(f"[TIMER] Failed to send timer message to {tg_id}: {e}")

    # Шаг 2: тикаем каждые 15 сек
    for remaining in (45, 30, 15):
        try:
            await asyncio.sleep(15)
        except asyncio.CancelledError:
            return
        text = _format_timer_text(turn_number, remaining)
        for _uid, tg_id in participants:
            msg_id = mgr.get_timer_message_id(match_id, tg_id)
            if not msg_id:
                continue
            try:
                await bot.edit_message_text(
                    chat_id=tg_id, message_id=msg_id, text=text
                )
            except Exception:
                # Сообщение могли удалить, или текст тот же — игнорируем
                pass


def _format_timer_text(turn_number: int, remaining_seconds: int) -> str:
    """Текст таймер-сообщения."""
    if remaining_seconds <= 5:
        emoji = "🚨"
    elif remaining_seconds <= 15:
        emoji = "⚠️"
    else:
        emoji = "⏱"
    return f"{emoji} <b>Ход #{turn_number} — осталось {remaining_seconds} сек</b>"


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
        and match.manager2_id != BOT_USER_ID
    ):
        timed_out_managers.append(match.manager2_id)

    logger.info(
        f"[TIMER] Turn {turn_number} timeout — auto-betting for "
        f"{len(timed_out_managers)} manager(s); dice_rolled={match.current_turn.dice_rolled}"
    )

    # Автоставки за просрочивших
    for mgr_id in timed_out_managers:
        try:
            _auto_random_bets_for_manager(engine, match, mgr_id)
        except Exception as e:
            logger.exception(f"[TIMER] Auto-bets failed for {mgr_id}: {e}")

    # Если оппонент-бот ещё не сделал ставки — делаем за него
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

    # Бросаем кубик автоматически (если оба готовы и кубик ещё не брошен)
    dice = None
    if match.current_turn and not match.current_turn.dice_rolled:
        can_roll, _ = engine.can_roll_dice(match)
        if can_roll:
            try:
                match, dice, _won = engine.roll_dice(match)
            except Exception as e:
                logger.exception(f"[TIMER] roll_dice failed: {e}")
            else:
                storage.save_match(match)
                # Резолвим жёлтую карточку и пенальти автоматически
                await _auto_resolve_post_dice(engine, storage, match)
    elif match.current_turn:
        dice = match.current_turn.dice_value

    # Уведомляем участников
    await _notify_timeout(bot, storage, match, turn_number, timed_out_managers, dice)


def _auto_random_bets_for_manager(engine, match, manager_id: UUID) -> None:
    """Случайные ставки за конкретного менеджера (используется при таймауте).

    Учитывает уже сделанный пользователем выбор:
    - Если пользователь уже залочил игрока в этом ходу — используем ЭТОГО игрока
      и доставляем недостающие ставки на него же (его частичный прогресс
      сохраняется).
    - Если игрок ещё не выбран — выбираем случайного из доступных.
    """
    turn = match.current_turn
    if not turn:
        return

    is_m1 = manager_id == match.manager1_id
    locked_player_id = turn.manager1_player_id if is_m1 else turn.manager2_player_id
    existing_bets = list(turn.manager1_bets if is_m1 else turn.manager2_bets)

    turn_num = turn.turn_number
    required_bets = (
        2 if match.phase == MatchPhase.EXTRA_TIME else (1 if turn_num == 1 else 2)
    )

    # Выбираем игрока (или используем уже залоченного)
    if locked_player_id:
        team = match.get_team(manager_id)
        player = team.get_player_by_id(locked_player_id) if team else None
        if not player:
            logger.warning(
                f"[TIMER] Locked player {locked_player_id} not found for {manager_id}"
            )
            return
    else:
        available = engine.get_available_players(match, manager_id)
        if not available:
            logger.warning(f"[TIMER] No available players for {manager_id}")
            return
        player = random.choice(available)

    # Доставляем недостающие ставки на этого игрока
    bets_to_place = max(0, required_bets - len(existing_bets))
    for _ in range(bets_to_place):
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
    from src.platforms.telegram.keyboards.inline import Keyboards

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
            text += f"\nХод #{turn_number}."
            await bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                reply_markup=Keyboards.timeout_notice(),
            )
        except Exception as e:
            logger.warning(f"[TIMER] Failed to notify {mgr_id}: {e}")
