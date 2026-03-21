# src/platforms/telegram/handlers/match.py
"""Хендлеры создания и управления матчами"""

from uuid import UUID
from typing import List

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from src.core.models.match import MatchType, MatchStatus
from src.core.models.team import Formation, FORMATION_STRUCTURE
from src.core.models.player import Position

from ..keyboards.inline import Keyboards
from ..states.game_states import MatchStates
from ..renderers.match_renderer import MatchRenderer
from ..dependencies import get_user_service, get_match_service

router = Router(name="match")


@router.callback_query(F.data == "play_random")
async def cb_play_random(callback: CallbackQuery, state: FSMContext):
    """Начать поиск случайного соперника"""
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    # Проверяем лимиты
    can_play, reason = await user_service.can_user_play(user.id)
    if not can_play:
        await callback.answer(reason, show_alert=True)
        return
    
    # Проверяем активный матч
    active = await match_service.get_user_active_match(user.id)
    if active:
        await callback.answer("У вас уже есть активный матч!", show_alert=True)
        return
    
    # Ищем или создаём матч
    match, is_new = await match_service.find_or_create_random_match(
        user.id, platform="telegram"
    )
    
    await state.update_data(match_id=str(match.id))
    
    if is_new:
        await state.set_state(MatchStates.waiting_opponent)
        await callback.message.edit_text(
            "⏳ <b>Поиск соперника...</b>\n\n"
            "Ожидаем подключение другого игрока.",
            reply_markup=Keyboards.waiting_for_opponent()
        )
    else:
        # Соперник найден, выбираем состав
        await state.set_state(MatchStates.selecting_formation)
        await callback.message.edit_text(
            "✅ <b>Соперник найден!</b>\n\n"
            "Выберите формацию для вашей команды:",
            reply_markup=Keyboards.formation_select()
        )
    
    await callback.answer()


@router.callback_query(F.data == "play_bot")
async def cb_play_bot(callback: CallbackQuery, state: FSMContext):
    """Начать игру против бота"""
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    # Проверяем лимиты
    can_play, reason = await user_service.can_user_play(user.id)
    if not can_play:
        await callback.answer(reason, show_alert=True)
        return
    
    # Создаём матч против бота
    match = await match_service.create_match(
        user.id, MatchType.VS_BOT, platform="telegram"
    )
    
    await state.update_data(match_id=str(match.id))
    await state.set_state(MatchStates.selecting_formation)
    
    await callback.message.edit_text(
        "🤖 <b>Матч против бота</b>\n\n"
        "Выберите формацию для вашей команды:",
        reply_markup=Keyboards.formation_select()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("formation:"))
async def cb_select_formation(callback: CallbackQuery, state: FSMContext):
    """Выбор формации"""
    formation_value = callback.data.split(":")[1]
    formation = Formation(formation_value)
    
    await state.update_data(
        formation=formation_value,
        selected_players=[]
    )
    await state.set_state(MatchStates.selecting_lineup)
    
    # Получаем команду пользователя
    user_service = await get_user_service()
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    team = await user_service.get_user_team(user.id)
    
    if not team:
        await callback.answer("Команда не найдена!", show_alert=True)
        return
    
    # Формируем требования по позициям
    structure = FORMATION_STRUCTURE[formation]
    requirements = "\n".join([
        f"• Вратарей: {structure['goalkeeper']}",
        f"• Защитников: {structure['defender']}",
        f"• Полузащитников: {structure['midfielder']}",
        f"• Нападающих: {structure['forward']}",
    ])
    
    await callback.message.edit_text(
        f"📋 <b>Формация: {formation_value}</b>\n\n"
        f"Требуется:\n{requirements}\n\n"
        f"Выберите 11 игроков:",
        reply_markup=Keyboards.player_select(team.players, [])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("select_player:"), MatchStates.selecting_lineup)
async def cb_select_player(callback: CallbackQuery, state: FSMContext):
    """Выбор игрока в состав"""
    player_id = callback.data.split(":")[1]
    
    data = await state.get_data()
    selected: List[str] = data.get("selected_players", [])
    
    if player_id in selected:
        selected.remove(player_id)
    else:
        if len(selected) >= 11:
            await callback.answer("Уже выбрано 11 игроков!", show_alert=True)
            return
        selected.append(player_id)
    
    await state.update_data(selected_players=selected)
    
    # Обновляем клавиатуру
    user_service = await get_user_service()
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    team = await user_service.get_user_team(user.id)
    
    selected_uuids = [UUID(s) for s in selected]
    
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.player_select(team.players, selected_uuids)
    )
    await callback.answer(f"Выбрано: {len(selected)}/11")


@router.callback_query(F.data.startswith("filter:"), MatchStates.selecting_lineup)
async def cb_filter_position(callback: CallbackQuery, state: FSMContext):
    """Фильтр игроков по позиции"""
    position_str = callback.data.split(":")[1]
    position = Position(position_str)
    
    data = await state.get_data()
    selected = [UUID(s) for s in data.get("selected_players", [])]
    
    user_service = await get_user_service()
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    team = await user_service.get_user_team(user.id)
    
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.player_select(team.players, selected, position)
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_lineup", MatchStates.selecting_lineup)
async def cb_confirm_lineup(callback: CallbackQuery, state: FSMContext):
    """Подтвердить состав"""
    data = await state.get_data()
    selected = data.get("selected_players", [])
    formation_value = data.get("formation")
    match_id = data.get("match_id")
    
    if len(selected) != 11:
        await callback.answer(f"Выберите 11 игроков (сейчас: {len(selected)})", show_alert=True)
        return
    
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    formation = Formation(formation_value)
    player_ids = [UUID(s) for s in selected]
    
    try:
        match = await match_service.set_lineup(
            UUID(match_id),
            user.id,
            formation,
            player_ids
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    # Проверяем статус матча
    if match.status == MatchStatus.IN_PROGRESS:
        await state.set_state(MatchStates.in_game)
        
        # Рендерим игровой экран
        renderer = MatchRenderer()
        text = renderer.render_match_status(match, user.id)
        text += "\n\n" + renderer.render_turn_info(match, user.id)
        
        # Определяем доступные действия
        is_my_turn = match.current_turn and match.current_turn.current_manager_id == user.id
        
        await callback.message.edit_text(
            text,
            reply_markup=Keyboards.game_actions(
                can_bet=is_my_turn and not (match.current_turn and match.current_turn.dice_rolled),
                can_roll=is_my_turn and bool(match.current_turn and match.current_turn.bets_placed) and not match.current_turn.dice_rolled,
                can_draw_card=is_my_turn and (match.current_turn and match.current_turn.dice_rolled and not match.current_turn.card_drawn),
                can_end_turn=is_my_turn and (match.current_turn and match.current_turn.dice_rolled)
            )
        )
    elif match.status == MatchStatus.SETTING_LINEUP:
        # Ожидаем соперника
        await callback.message.edit_text(
            "✅ <b>Состав выбран!</b>\n\n"
            "⏳ Ожидаем соперника...",
            reply_markup=Keyboards.waiting_for_opponent()
        )
    
    await callback.answer()


@router.callback_query(F.data == "cancel_match")
async def cb_cancel_match(callback: CallbackQuery, state: FSMContext):
    """Отменить матч"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    if match_id:
        user_service = await get_user_service()
        match_service = await get_match_service()
        
        user = await user_service.get_or_create_telegram_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.full_name
        )
        
        try:
            await match_service.cancel_match(UUID(match_id), user.id)
        except ValueError:
            pass
    
    await state.clear()
    await callback.message.edit_text(
        "❌ Матч отменён",
        reply_markup=Keyboards.main_menu()
    )
    await callback.answer()
