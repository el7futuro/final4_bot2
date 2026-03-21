# src/platforms/telegram/handlers/game.py
"""Хендлеры игрового процесса"""

from uuid import UUID
from typing import Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice, BetOutcome

from ..keyboards.inline import Keyboards
from ..states.game_states import MatchStates
from ..renderers.match_renderer import MatchRenderer
from ..dependencies import get_user_service, get_match_service

router = Router(name="game")


async def _render_game_screen(callback: CallbackQuery, state: FSMContext):
    """Отрендерить игровой экран"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    if not match_id:
        await callback.message.edit_text(
            "❌ Матч не найден",
            reply_markup=Keyboards.main_menu()
        )
        return
    
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    match = await match_service.get_match(UUID(match_id))
    if not match:
        await callback.message.edit_text(
            "❌ Матч не найден",
            reply_markup=Keyboards.main_menu()
        )
        return
    
    renderer = MatchRenderer()
    text = renderer.render_match_status(match, user.id)
    text += "\n\n" + renderer.render_turn_info(match, user.id)
    
    # Статистика команд
    if match.team1:
        text += "\n\n" + renderer.render_team_stats(
            match.team1, 
            is_opponent=(match.manager1_id != user.id)
        )
    if match.team2:
        text += "\n\n" + renderer.render_team_stats(
            match.team2,
            is_opponent=(match.manager2_id != user.id)
        )
    
    is_my_turn = match.current_turn and match.current_turn.current_manager_id == user.id
    turn = match.current_turn
    
    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.game_actions(
            can_bet=is_my_turn and turn and not turn.dice_rolled,
            can_roll=is_my_turn and turn and bool(turn.bets_placed) and not turn.dice_rolled,
            can_draw_card=is_my_turn and turn and turn.dice_rolled and not turn.card_drawn,
            can_end_turn=is_my_turn and turn and turn.dice_rolled
        )
    )


@router.callback_query(F.data == "back_to_game")
async def cb_back_to_game(callback: CallbackQuery, state: FSMContext):
    """Вернуться к игровому экрану"""
    await state.set_state(MatchStates.in_game)
    await _render_game_screen(callback, state)
    await callback.answer()


@router.callback_query(F.data == "match_stats")
async def cb_match_stats(callback: CallbackQuery, state: FSMContext):
    """Показать статистику матча"""
    await _render_game_screen(callback, state)
    await callback.answer()


@router.callback_query(F.data == "make_bet", MatchStates.in_game)
async def cb_make_bet(callback: CallbackQuery, state: FSMContext):
    """Начать создание ставки"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    match = await match_service.get_match(UUID(match_id))
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    team = match.get_team(user.id)
    if not team:
        await callback.answer("Команда не найдена", show_alert=True)
        return
    
    field_players = team.get_field_players()
    
    await state.set_state(MatchStates.selecting_bet_player)
    await callback.message.edit_text(
        "🎯 <b>Выберите игрока для ставки:</b>",
        reply_markup=Keyboards.bet_player_select(field_players)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_player:"), MatchStates.selecting_bet_player)
async def cb_bet_player_selected(callback: CallbackQuery, state: FSMContext):
    """Игрок для ставки выбран"""
    player_id = callback.data.split(":")[1]
    
    data = await state.get_data()
    match_id = data.get("match_id")
    
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    # Получаем доступные типы ставок
    available_types = await match_service.get_available_bet_types(
        UUID(match_id), user.id, UUID(player_id)
    )
    
    if not available_types:
        await callback.answer("Нет доступных типов ставок", show_alert=True)
        return
    
    await state.update_data(bet_player_id=player_id)
    await state.set_state(MatchStates.selecting_bet_type)
    
    await callback.message.edit_text(
        "🎯 <b>Выберите тип ставки:</b>\n\n"
        "• <b>Чёт/Нечёт</b> — при выигрыше игрок получает отбития\n"
        "• <b>Больше/Меньше</b> — при выигрыше игрок получает передачи\n"
        "• <b>Точное число</b> — при выигрыше игрок забивает гол",
        reply_markup=Keyboards.bet_type_select(available_types)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_type:"), MatchStates.selecting_bet_type)
async def cb_bet_type_selected(callback: CallbackQuery, state: FSMContext):
    """Тип ставки выбран"""
    bet_type_value = callback.data.split(":")[1]
    bet_type = BetType(bet_type_value)
    
    await state.update_data(bet_type=bet_type_value)
    await state.set_state(MatchStates.selecting_bet_value)
    
    if bet_type == BetType.EVEN_ODD:
        await callback.message.edit_text(
            "🔢 <b>Чёт или Нечёт?</b>\n\n"
            "Чётные: 2, 4, 6\n"
            "Нечётные: 1, 3, 5",
            reply_markup=Keyboards.even_odd_select()
        )
    elif bet_type == BetType.HIGH_LOW:
        await callback.message.edit_text(
            "📊 <b>Больше или Меньше?</b>\n\n"
            "Меньше: 1, 2, 3\n"
            "Больше: 4, 5, 6",
            reply_markup=Keyboards.high_low_select()
        )
    elif bet_type == BetType.EXACT_NUMBER:
        await callback.message.edit_text(
            "🎯 <b>Выберите точное число:</b>",
            reply_markup=Keyboards.exact_number_select()
        )
    
    await callback.answer()


@router.callback_query(F.data == "back_bet_type", MatchStates.selecting_bet_value)
async def cb_back_bet_type(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору типа ставки"""
    data = await state.get_data()
    match_id = data.get("match_id")
    player_id = data.get("bet_player_id")
    
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    available_types = await match_service.get_available_bet_types(
        UUID(match_id), user.id, UUID(player_id)
    )
    
    await state.set_state(MatchStates.selecting_bet_type)
    await callback.message.edit_text(
        "🎯 <b>Выберите тип ставки:</b>",
        reply_markup=Keyboards.bet_type_select(available_types)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_value:"), MatchStates.selecting_bet_value)
async def cb_bet_value_selected(callback: CallbackQuery, state: FSMContext):
    """Значение ставки выбрано — создаём ставку"""
    bet_value = callback.data.split(":")[1]
    
    data = await state.get_data()
    match_id = data.get("match_id")
    player_id = data.get("bet_player_id")
    bet_type_value = data.get("bet_type")
    
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    bet_type = BetType(bet_type_value)
    
    # Создаём объект ставки
    bet = Bet(
        match_id=UUID(match_id),
        manager_id=user.id,
        player_id=UUID(player_id),
        turn_number=1,  # Будет установлено в сервисе
        bet_type=bet_type
    )
    
    # Устанавливаем значение в зависимости от типа
    if bet_type == BetType.EVEN_ODD:
        bet.even_odd_choice = EvenOddChoice(bet_value)
    elif bet_type == BetType.HIGH_LOW:
        bet.high_low_choice = HighLowChoice(bet_value)
    elif bet_type == BetType.EXACT_NUMBER:
        bet.exact_number = int(bet_value)
    
    try:
        match, bet = await match_service.place_bet(
            UUID(match_id), user.id, UUID(player_id), bet
        )
        await callback.answer("✅ Ставка сделана!")
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    # Возвращаемся к игровому экрану
    await state.set_state(MatchStates.in_game)
    await _render_game_screen(callback, state)


@router.callback_query(F.data == "roll_dice", MatchStates.in_game)
async def cb_roll_dice(callback: CallbackQuery, state: FSMContext):
    """Бросить кубик"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    try:
        match, dice_value, won_bets = await match_service.roll_dice(
            UUID(match_id), user.id
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    # Отображаем результат
    renderer = MatchRenderer()
    
    # Получаем проигравшие ставки
    turn_bets = match.get_turn_bets()
    lost_bets = [b for b in turn_bets if b.outcome == BetOutcome.LOST]
    
    result_text = renderer.render_dice_result(dice_value, won_bets, lost_bets)
    
    await callback.message.edit_text(
        result_text + "\n\n" + renderer.render_turn_info(match, user.id),
        reply_markup=Keyboards.game_actions(
            can_bet=False,
            can_roll=False,
            can_draw_card=bool(won_bets) and not match.current_turn.card_drawn,
            can_end_turn=True
        )
    )
    await callback.answer()


@router.callback_query(F.data == "draw_card", MatchStates.in_game)
async def cb_draw_card(callback: CallbackQuery, state: FSMContext):
    """Взять карточку Свисток"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    try:
        match, card = await match_service.draw_card(UUID(match_id), user.id)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    if card:
        renderer = MatchRenderer()
        card_text = renderer.render_card_drawn(card)
        
        # Проверяем, нужна ли цель
        if card.requires_target():
            from src.core.engine.whistle_deck import WhistleDeck
            valid_targets = WhistleDeck.get_valid_targets(card, match, user.id)
            
            if valid_targets:
                await state.update_data(card_id=str(card.id))
                await state.set_state(MatchStates.selecting_card_target)
                
                await callback.message.edit_text(
                    f"{card_text}\n\nВыберите цель:",
                    reply_markup=Keyboards.card_target_select(valid_targets)
                )
                await callback.answer()
                return
        
        # Карточка без цели — автоприменение
        await match_service.apply_card(UUID(match_id), user.id, card.id)
        await callback.message.edit_text(
            f"{card_text}\n\n✅ Карточка применена!",
            reply_markup=Keyboards.game_actions(can_end_turn=True)
        )
    else:
        await callback.message.edit_text(
            "🃏 Карточка не выпала",
            reply_markup=Keyboards.game_actions(can_end_turn=True)
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("card_target:"), MatchStates.selecting_card_target)
async def cb_card_target_selected(callback: CallbackQuery, state: FSMContext):
    """Цель для карточки выбрана"""
    target_id = callback.data.split(":")[1]
    
    data = await state.get_data()
    match_id = data.get("match_id")
    card_id = data.get("card_id")
    
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    try:
        await match_service.apply_card(
            UUID(match_id), user.id, UUID(card_id), UUID(target_id)
        )
        await callback.answer("✅ Карточка применена!")
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    await state.set_state(MatchStates.in_game)
    await _render_game_screen(callback, state)


@router.callback_query(F.data == "skip_card", MatchStates.selecting_card_target)
async def cb_skip_card(callback: CallbackQuery, state: FSMContext):
    """Пропустить применение карточки"""
    await state.set_state(MatchStates.in_game)
    await _render_game_screen(callback, state)
    await callback.answer()


@router.callback_query(F.data == "end_turn", MatchStates.in_game)
async def cb_end_turn(callback: CallbackQuery, state: FSMContext):
    """Завершить ход"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    user_service = await get_user_service()
    match_service = await get_match_service()
    
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    try:
        match = await match_service.end_turn(UUID(match_id), user.id)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    # Проверяем, завершился ли матч
    from src.core.models.match import MatchStatus
    
    if match.status == MatchStatus.FINISHED:
        renderer = MatchRenderer()
        result_text = renderer.render_match_result(match, user.id)
        
        await state.clear()
        await callback.message.edit_text(
            result_text,
            reply_markup=Keyboards.main_menu()
        )
    else:
        await _render_game_screen(callback, state)
    
    await callback.answer()
