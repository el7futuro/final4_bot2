# src/platforms/telegram/handlers/game.py
"""Хендлеры игрового процесса: экран, кубик, конец хода, история, статистика"""

from uuid import UUID
from typing import Optional
import random

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from src.core.models.match import MatchStatus, MatchPhase
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice, BetOutcome
from src.core.engine.game_engine import BOT_USER_ID

from ..keyboards.inline import Keyboards
from ..states.game_states import MatchStates
from ..renderers.match_renderer import MatchRenderer
from ..storage import get_storage

from .pvp_notify import (
    notify_opponent_waiting_for_roll,
    notify_manager1_can_roll,
    notify_opponent_turn_result,
    notify_penalty_owner_with_choice,
    notify_opponent_penalty_result,
    notify_yellow_card_owner_with_choice,
    notify_opponent_match_finished,
    notify_opponent_extra_time,
    notify_opponent_new_turn,
)
from .bot_logic import bot_make_bets, auto_penalties

router = Router(name="game")


# ==================== РЕНДЕР ИГРОВОГО ЭКРАНА ====================


async def _render_game_screen(callback: CallbackQuery, state: FSMContext, show_stats: bool = False):
    """Отрендерить текущее состояние игры"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    if not match_id:
        match = storage.get_user_active_match(user.id)
        if match:
            await state.update_data(match_id=str(match.id))
            await state.set_state(MatchStates.in_game)
    else:
        match = storage.get_match(UUID(match_id))
    
    if not match:
        await callback.message.edit_text(
            "❌ Матч не найден!",
            reply_markup=Keyboards.main_menu()
        )
        return
    
    renderer = MatchRenderer()
    
    text = renderer.render_match_status(match, user.id)
    text += "\n\n" + renderer.render_turn_info_simultaneous(match, user.id)
    
    is_user_m1 = match.manager1_id == user.id
    turn = match.current_turn
    
    if turn:
        bets_count = len(turn.manager1_bets if is_user_m1 else turn.manager2_bets)
        is_confirmed = turn.manager1_confirmed if is_user_m1 else turn.manager2_confirmed
        both_ready = turn.manager1_confirmed and turn.manager2_confirmed
        
        turn_number = turn.turn_number
        required_bets = 2 if match.phase == MatchPhase.EXTRA_TIME else (1 if turn_number == 1 else 2)
        
        is_roller = is_user_m1
        
        if both_ready and is_roller:
            await state.set_state(MatchStates.waiting_roll)
        else:
            await state.set_state(MatchStates.in_game)
        
        await callback.message.edit_text(
            text,
            reply_markup=Keyboards.game_actions_simultaneous(
                bets_count=bets_count,
                required_bets=required_bets,
                is_confirmed=is_confirmed,
                both_ready=both_ready and is_roller
            )
        )
    else:
        await callback.message.edit_text(
            text,
            reply_markup=Keyboards.main_menu()
        )


# ==================== НАВИГАЦИЯ ====================


@router.callback_query(F.data == "back_to_game")
async def cb_back_to_game(callback: CallbackQuery, state: FSMContext):
    """Вернуться к игре"""
    await _render_game_screen(callback, state)
    await callback.answer()


# ==================== СТАТИСТИКА ====================


@router.callback_query(F.data == "match_stats")
async def cb_match_stats(callback: CallbackQuery, state: FSMContext):
    """Показать статистику матча"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    match = None
    if match_id:
        match = storage.get_match(UUID(match_id))
    
    if not match:
        match = storage.get_user_active_match(user.id)
        if not match:
            match = storage.get_user_last_match(user.id)
        if match:
            await state.update_data(match_id=str(match.id))
            await state.set_state(MatchStates.in_game)
    
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    renderer = MatchRenderer()
    is_user_m1 = match.manager1_id == user.id
    
    text_parts = []
    
    if match.status == MatchStatus.FINISHED and match.score:
        vg = match.score.manager1_goals if is_user_m1 else match.score.manager2_goals
        og = match.score.manager2_goals if is_user_m1 else match.score.manager1_goals
        text_parts.append(f"🏁 <b>Итоговый счёт: {vg}:{og}</b>")
        if match.result and match.result.decided_by == MatchPhase.PENALTIES and match.penalty_results:
            vp = match.penalty_score_m1 if is_user_m1 else match.penalty_score_m2
            op = match.penalty_score_m2 if is_user_m1 else match.penalty_score_m1
            text_parts.append(f"🎯 Серия пенальти: <b>{vp}:{op}</b>")
        text_parts.append("")
    elif match.phase == MatchPhase.EXTRA_TIME:
        s1, s2, details = MatchRenderer.calculate_extra_time_score(match)
        vs = s1 if is_user_m1 else s2
        os_ = s2 if is_user_m1 else s1
        text_parts.append(f"⏱ <b>Счёт ET: {vs}:{os_}</b>\n")
    else:
        s1, s2, details = MatchRenderer.calculate_current_score(match)
        vs = s1 if is_user_m1 else s2
        os_ = s2 if is_user_m1 else s1
        text_parts.append(f"📊 <b>Счёт: {vs}:{os_}</b>\n")
    
    if match.team1 and match.team2:
        text_parts.append(renderer.render_team_stats(
            match.team1 if is_user_m1 else match.team2,
            match=match, is_opponent=False
        ))
        text_parts.append("")
        text_parts.append(renderer.render_team_stats(
            match.team2 if is_user_m1 else match.team1,
            match=match, is_opponent=True
        ))
    
    text = "\n".join(text_parts)
    
    if match.status == MatchStatus.FINISHED:
        kb = Keyboards.match_finished_menu()
    else:
        kb = Keyboards.back_to_game()
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ==================== ИСТОРИЯ ====================


@router.callback_query(F.data == "match_history")
async def cb_match_history(callback: CallbackQuery, state: FSMContext):
    """Показать историю ходов матча"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    match = None
    if match_id:
        match = storage.get_match(UUID(match_id))
    
    if not match:
        match = storage.get_user_active_match(user.id)
        if not match:
            match = storage.get_user_last_match(user.id)
        if match:
            await state.update_data(match_id=str(match.id))
    
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    renderer = MatchRenderer()
    history_text = renderer.render_match_history(match, user.id)
    
    if match.status == MatchStatus.FINISHED:
        kb = Keyboards.match_finished_menu()
    else:
        kb = Keyboards.back_to_game()
    
    await callback.message.edit_text(
        history_text,
        reply_markup=kb
    )
    await callback.answer()


# ==================== КУБИК ====================


@router.callback_query(F.data == "roll_dice")
async def cb_roll_dice_restore(callback: CallbackQuery, state: FSMContext):
    """Восстановить состояние и бросить кубик"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    if not match_id:
        storage = get_storage()
        user = storage.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.full_name or "Игрок"
        )
        match = storage.get_user_active_match(user.id)
        if match:
            await state.update_data(match_id=str(match.id))
            await state.set_state(MatchStates.waiting_roll)
            match_id = str(match.id)
    
    if not match_id:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    match = storage.get_match(UUID(match_id))
    
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    await _handle_roll_dice(callback, state, match, user)


async def _handle_roll_dice(callback: CallbackQuery, state: FSMContext, match, user):
    """Логика броска кубика"""
    storage = get_storage()
    engine = storage.engine
    
    can_roll, reason = engine.can_roll_dice(match)
    if not can_roll:
        await callback.answer(f"Нельзя бросить: {reason}", show_alert=True)
        return
    
    match, dice_value, won_bets = engine.roll_dice(match)
    storage.save_match(match)
    
    renderer = MatchRenderer()
    text = renderer.render_dice_result_simultaneous(dice_value, won_bets, match, user.id)
    
    cards_text = renderer.render_cards_drawn(match, user.id)
    if cards_text:
        text += "\n\n" + cards_text
    
    # PvP — уведомляем соперника
    if match.match_type.value == "random":
        await notify_opponent_turn_result(callback.bot, match, user.id, dice_value, won_bets)
    
    # Проверяем пенальти (карточка)
    if match.current_turn and match.current_turn.waiting_for_penalty_roll:
        for card in match.whistle_cards_drawn:
            if (card.card_type.value == "penalty" and
                card.penalty_scored is None and
                card.turn_applied == match.current_turn.turn_number):
                
                penalty_owner_id = card.applied_by_manager_id
                
                if penalty_owner_id == BOT_USER_ID:
                    choice = random.choice(["high", "low"])
                    match, success, pen_dice = engine.resolve_penalty(match, BOT_USER_ID, choice)
                    storage.save_match(match)
                    pen_result = "⚽ ГОЛ" if success else "❌ МИМО"
                    text += f"\n\n⚽ <b>ПЕНАЛЬТИ БОТА:</b> {pen_result}"
                elif penalty_owner_id == user.id:
                    text += "\n\n⚽ <b>ПЕНАЛЬТИ!</b>\nВыберите направление удара:"
                    await state.set_state(MatchStates.penalty_kick)
                    await callback.message.edit_text(
                        text,
                        reply_markup=Keyboards.penalty_choice()
                    )
                    await callback.answer("⚽ Пенальти!")
                    return
                else:
                    if match.match_type.value == "random":
                        await notify_penalty_owner_with_choice(callback.bot, match, penalty_owner_id)
                        text += "\n\n⚽ <b>ПЕНАЛЬТИ СОПЕРНИКА!</b>\n⏳ Ожидаем выбор соперника..."
                        await callback.message.edit_text(text, reply_markup=None)
                        await callback.answer("⚽ Пенальти соперника!")
                        return
                break
    
    # Проверяем жёлтую карточку
    if match.current_turn and match.current_turn.waiting_for_yellow_card_choice:
        target_mgr = match.current_turn.yellow_card_target_manager_id
        target_pid = match.current_turn.yellow_card_target_player_id
        
        if target_mgr and target_pid:
            target_team = match.get_team(target_mgr)
            target_player = target_team.get_player_by_id(target_pid) if target_team else None
            
            if target_player:
                has_goals = target_player.stats.goals > 0
                has_passes = target_player.stats.passes > 0
                has_saves = target_player.stats.saves > 0
                
                if not has_goals and not has_passes and not has_saves:
                    match.current_turn.waiting_for_yellow_card_choice = False
                    match.current_turn.yellow_card_target_manager_id = None
                    match.current_turn.yellow_card_target_player_id = None
                    match.current_turn.yellow_card_id = None
                    storage.save_match(match)
                    text += "\n\n🟡 <b>Предупреждение!</b> У игрока нет действий — карточка не повлияла."
                elif target_mgr == BOT_USER_ID:
                    if has_saves:
                        bot_action = "save"
                    elif has_passes:
                        bot_action = "pass"
                    else:
                        bot_action = "goal"
                    match = storage.engine.resolve_yellow_card(match, BOT_USER_ID, bot_action)
                    storage.save_match(match)
                    action_names = {"save": "отбитие", "pass": "передачу", "goal": "гол"}
                    text += f"\n\n🟡 <b>Предупреждение!</b> Бот потерял {action_names[bot_action]}."
                elif target_mgr == user.id:
                    text += f"\n\n🟡 <b>ПРЕДУПРЕЖДЕНИЕ!</b>\nВаш игрок <b>{target_player.name}</b> получил жёлтую карточку.\nВыберите, какое действие потерять:"
                    await state.set_state(MatchStates.yellow_card_choice)
                    await callback.message.edit_text(
                        text,
                        reply_markup=Keyboards.yellow_card_choice(has_goals, has_passes, has_saves)
                    )
                    await callback.answer("🟡 Предупреждение!")
                    return
                else:
                    if match.match_type.value == "random":
                        await notify_yellow_card_owner_with_choice(callback.bot, match, target_mgr)
                        text += f"\n\n🟡 <b>ПРЕДУПРЕЖДЕНИЕ СОПЕРНИКА!</b>\n⏳ Ожидаем выбор соперника..."
                        await callback.message.edit_text(text, reply_markup=None)
                        await callback.answer("🟡 Предупреждение соперника!")
                        return
    
    await state.set_state(MatchStates.in_game)
    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.game_actions_after_roll()
    )
    await callback.answer(f"🎲 Выпало: {dice_value}")


# ==================== КОНЕЦ ХОДА ====================


@router.callback_query(F.data == "end_turn")
async def cb_end_turn_restore(callback: CallbackQuery, state: FSMContext):
    """Восстановить состояние и завершить ход"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    if not match_id:
        storage = get_storage()
        user = storage.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.full_name or "Игрок"
        )
        match = storage.get_user_active_match(user.id)
        if match:
            await state.update_data(match_id=str(match.id))
            await state.set_state(MatchStates.in_game)
            match_id = str(match.id)
    
    if not match_id:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    match = storage.get_match(UUID(match_id))
    
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    await _handle_end_turn(callback, state, match, user)


async def _handle_end_turn(callback: CallbackQuery, state: FSMContext, match, user):
    """Логика завершения хода"""
    storage = get_storage()
    engine = storage.engine
    
    try:
        match = engine.end_turn(match)
        storage.save_match(match)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    if match.status == MatchStatus.FINISHED:
        renderer = MatchRenderer()
        result_text = renderer.render_match_result(match, user.id)
        
        if match.result:
            user_obj = storage.get_user_by_id(user.id)
            if user_obj:
                user_obj.matches_played += 1
                if match.result.winner_id == user.id:
                    user_obj.matches_won += 1
                    user_obj.rating += 25
                else:
                    user_obj.rating = max(0, user_obj.rating - 15)
                storage.update_user_stats(user_obj)
        
        await state.update_data(match_id=str(match.id))
        await state.set_state(None)
        await callback.message.edit_text(
            result_text,
            reply_markup=Keyboards.match_finished_menu()
        )
        
        if match.match_type.value == "random":
            await notify_opponent_match_finished(callback.bot, match, user.id, "finished")
    
    elif match.status == MatchStatus.EXTRA_TIME:
        renderer = MatchRenderer()
        text = renderer.render_match_status(match, user.id)
        text += "\n\n" + renderer.render_turn_info_simultaneous(match, user.id)
        
        await state.set_state(MatchStates.in_game)
        await callback.message.edit_text(
            "⏱ <b>ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ!</b>\n\n"
            "Счёт равный, начинаем дополнительные 5 ходов.\n"
            "⚠️ Каждый игрок ОБЯЗАН делать ставку на гол!\n\n" + text,
            reply_markup=Keyboards.game_actions_simultaneous(0, 2, False, False)
        )
        
        if match.match_type.value == "random":
            await notify_opponent_extra_time(callback.bot, match, user.id)
    
    elif match.status == MatchStatus.PENALTIES:
        match = auto_penalties(storage, match)
        storage.save_match(match)
        
        renderer = MatchRenderer()
        result_text = renderer.render_match_result(match, user.id)
        
        await state.update_data(match_id=str(match.id))
        await state.set_state(None)
        await callback.message.edit_text(
            "⚽ <b>СЕРИЯ ПЕНАЛЬТИ!</b>\n\n" + result_text,
            reply_markup=Keyboards.match_finished_menu()
        )
        
        if match.match_type.value == "random":
            await notify_opponent_match_finished(callback.bot, match, user.id, "penalties")
    
    elif match.status == MatchStatus.IN_PROGRESS:
        if match.match_type.value == "random":
            await notify_opponent_new_turn(callback.bot, match, user.id)
        
        await _render_game_screen(callback, state)
    
    else:
        await _render_game_screen(callback, state)
    
    await callback.answer()
