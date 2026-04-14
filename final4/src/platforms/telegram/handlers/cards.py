# src/platforms/telegram/handlers/cards.py
"""Хендлеры карточек: пенальти (карточка Свисток) и предупреждение"""

from uuid import UUID

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from src.core.models.whistle_card import CardType

from ..keyboards.inline import Keyboards
from ..states.game_states import MatchStates
from ..renderers.match_renderer import MatchRenderer
from ..storage import get_storage

from .pvp_notify import notify_opponent_penalty_result, notify_opponent_yellow_card_result

router = Router(name="cards")


@router.callback_query(F.data.startswith("penalty_choice:"))
async def cb_penalty_choice(callback: CallbackQuery, state: FSMContext):
    """Выбор направления пенальти (high/low)"""
    choice = callback.data.split(":")[1]
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    data = await state.get_data()
    match_id = data.get("match_id")
    match = storage.get_match(UUID(match_id)) if match_id else None
    
    if not match:
        match = storage.get_user_active_match(user.id)
        if match:
            await state.update_data(match_id=str(match.id))
    
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    choice_text = "Больше (4-6)" if choice == "high" else "Меньше (1-3)"
    
    await state.update_data(penalty_choice=choice)
    await state.set_state(MatchStates.penalty_choice_made)
    
    await callback.message.edit_text(
        f"⚽ <b>ПЕНАЛЬТИ!</b>\n\n"
        f"Ваш выбор: <b>{choice_text}</b>\n\n"
        f"Нажмите, чтобы бросить кубик!",
        reply_markup=Keyboards.penalty_roll_button()
    )
    await callback.answer()


@router.callback_query(F.data == "penalty_roll")
async def cb_penalty_roll(callback: CallbackQuery, state: FSMContext):
    """Бросок кубика для пенальти"""
    data = await state.get_data()
    choice = data.get("penalty_choice")
    match_id = data.get("match_id")
    
    if not choice:
        await callback.answer("Сначала выберите направление!", show_alert=True)
        return
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    match = storage.get_match(UUID(match_id)) if match_id else None
    if not match:
        match = storage.get_user_active_match(user.id)
    
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    try:
        match, success, dice_value = storage.engine.resolve_penalty(match, user.id, choice)
        storage.save_match(match)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    dice_emoji = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    choice_text = "Больше (4-6)" if choice == "high" else "Меньше (1-3)"
    
    if success:
        result_text = f"⚽ <b>ПЕНАЛЬТИ</b>\n\nВаш выбор: {choice_text}\n🎲 Выпало: {dice_emoji[dice_value]} <b>{dice_value}</b>\n\n🎉 <b>ГОЛ!</b>"
    else:
        result_text = f"⚽ <b>ПЕНАЛЬТИ</b>\n\nВаш выбор: {choice_text}\n🎲 Выпало: {dice_emoji[dice_value]} <b>{dice_value}</b>\n\n😞 <b>Мимо!</b>"
    
    await state.set_state(MatchStates.in_game)
    await callback.message.edit_text(
        result_text,
        reply_markup=Keyboards.game_actions_after_roll()
    )
    await callback.answer("⚽ Пенальти!" if success else "😞 Мимо!")
    
    # PvP — уведомляем соперника
    if match.match_type.value == "random":
        await notify_opponent_penalty_result(callback.bot, match, user.id, success, dice_value, choice)


@router.callback_query(F.data.startswith("yellow_card_action:"))
async def cb_yellow_card_action(callback: CallbackQuery, state: FSMContext):
    """Соперник выбрал, какое действие потерять при предупреждении"""
    action_type = callback.data.split(":")[1]  # "goal", "pass", "save"
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    data = await state.get_data()
    match_id = data.get("match_id")
    
    if match_id:
        match = storage.get_match(UUID(match_id))
    else:
        match = storage.get_user_active_match(user.id)
        if match:
            await state.update_data(match_id=str(match.id))
    
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    if not match.current_turn or not match.current_turn.waiting_for_yellow_card_choice:
        await callback.answer("Нет ожидающего предупреждения", show_alert=True)
        return
    
    if match.current_turn.yellow_card_target_manager_id != user.id:
        await callback.answer("Не ваш выбор", show_alert=True)
        return
    
    try:
        match = storage.engine.resolve_yellow_card(match, user.id, action_type)
        storage.save_match(match)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    action_names = {"goal": "гол", "pass": "передачу", "save": "отбитие"}
    result_text = f"🟡 Вы потеряли {action_names.get(action_type, action_type)}."
    
    await state.set_state(MatchStates.in_game)
    await callback.message.edit_text(
        result_text,
        reply_markup=Keyboards.game_actions_after_roll()
    )
    await callback.answer(f"🟡 Потеряно: {action_names.get(action_type, action_type)}")
    
    # В PvP — уведомляем соперника о результате
    if match.match_type.value == "random":
        await notify_opponent_yellow_card_result(callback.bot, match, user.id, action_type)
