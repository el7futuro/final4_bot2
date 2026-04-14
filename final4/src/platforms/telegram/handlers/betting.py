# src/platforms/telegram/handlers/betting.py
"""Хендлеры ставок: выбор игрока, типа, значения, отмена, подтверждение"""

from uuid import UUID

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from src.core.models.match import MatchStatus, MatchPhase
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice
from src.core.engine.game_engine import BOT_USER_ID

from ..keyboards.inline import Keyboards
from ..states.game_states import MatchStates
from ..renderers.match_renderer import MatchRenderer
from ..storage import get_storage

from .bot_logic import bot_make_bets
from .pvp_notify import notify_opponent_waiting_for_roll, notify_manager1_can_roll

router = Router(name="betting")


@router.callback_query(F.data == "make_bet")
async def cb_make_bet_restore_state(callback: CallbackQuery, state: FSMContext):
    """Восстановить состояние при нажатии make_bet без FSM"""
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
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    data = await state.get_data()
    match_id = data.get("match_id")
    if not match_id:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    match = storage.get_match(UUID(match_id))
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    await _handle_make_bet(callback, state, match, user)
    await callback.answer()


async def _handle_make_bet(callback: CallbackQuery, state: FSMContext, match, user):
    """Общая логика make_bet"""
    storage = get_storage()
    engine = storage.engine
    
    is_user_m1 = match.manager1_id == user.id
    turn = match.current_turn
    
    if not turn:
        await callback.answer("Ход не начат", show_alert=True)
        return
    
    current_bet_player_id = None
    if is_user_m1:
        current_bet_player_id = str(turn.manager1_player_id) if turn.manager1_player_id else None
    else:
        current_bet_player_id = str(turn.manager2_player_id) if turn.manager2_player_id else None
    
    if current_bet_player_id:
        player = None
        team = match.team1 if is_user_m1 else match.team2
        if team:
            player = team.get_player_by_id(UUID(current_bet_player_id))
        
        if player:
            available_types = storage.engine.get_available_bet_types(match, user.id, UUID(current_bet_player_id))
            
            if not available_types:
                await callback.answer("Нет доступных типов ставок", show_alert=True)
                return
            
            if is_user_m1:
                has_bets = len(turn.manager1_bets) > 0 if turn else False
            else:
                has_bets = len(turn.manager2_bets) > 0 if turn else False
            
            await state.update_data(bet_player_id=current_bet_player_id)
            await state.set_state(MatchStates.selecting_bet_type)
            
            await callback.message.edit_text(
                f"🎯 <b>Игрок: {player.name}</b>\n"
                f"<i>({player.position.value})</i>\n\n"
                "Выберите тип ставки:\n\n"
                "• <b>Чёт/Нечёт</b> → Отбития\n"
                "• <b>Больше/Меньше</b> → Передачи\n"
                "• <b>Точное число</b> → Гол",
                reply_markup=Keyboards.bet_type_select(available_types, has_existing_bets=has_bets)
            )
            return
    
    available_players = engine.get_available_players(match, user.id)
    
    if not available_players:
        await callback.answer("Нет доступных игроков!", show_alert=True)
        return
    
    await state.set_state(MatchStates.selecting_bet_player)
    
    renderer = MatchRenderer()
    text = renderer.render_match_status(match, user.id)
    text += "\n\n🎯 <b>Выберите игрока для ставки:</b>"
    
    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.bet_player_select(available_players)
    )


@router.callback_query(F.data.startswith("bet_player:"), MatchStates.selecting_bet_player)
async def cb_bet_player_selected(callback: CallbackQuery, state: FSMContext):
    """Игрок выбран"""
    player_id = callback.data.split(":")[1]
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    data = await state.get_data()
    match = storage.get_match(UUID(data["match_id"]))
    
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    available_types = storage.engine.get_available_bet_types(match, user.id, UUID(player_id))
    
    if not available_types:
        await callback.answer("Нет доступных типов ставок", show_alert=True)
        return
    
    await state.update_data(bet_player_id=player_id)
    await state.set_state(MatchStates.selecting_bet_type)
    
    team = match.team1 if match.manager1_id == user.id else match.team2
    player = team.get_player_by_id(UUID(player_id)) if team else None
    player_name = player.name if player else "Игрок"
    
    info = ""
    if match.phase == MatchPhase.EXTRA_TIME:
        info = "\n\n⏱ <i>Дополнительное время: обязательна ставка на гол!</i>"
    
    await callback.message.edit_text(
        f"🎯 <b>Игрок: {player_name}</b>\n\n"
        "Выберите тип ставки:\n"
        "• <b>Чёт/Нечёт</b> — при выигрыше игрок совершает отбитие\n"
        "• <b>Больше/Меньше</b> — при выигрыше игрок делает передачу\n"
        "• <b>Точное число</b> — при выигрыше игрок забивает гол"
        + info,
        reply_markup=Keyboards.bet_type_select(available_types, has_existing_bets=False)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_type:"), MatchStates.selecting_bet_type)
async def cb_bet_type_selected(callback: CallbackQuery, state: FSMContext):
    """Тип ставки выбран"""
    bet_type_str = callback.data.split(":")[1]
    bet_type = BetType(bet_type_str)
    
    await state.update_data(bet_type=bet_type_str)
    await state.set_state(MatchStates.selecting_bet_value)
    
    if bet_type == BetType.EVEN_ODD:
        await callback.message.edit_text(
            "🔢 <b>Чёт или Нечёт?</b>",
            reply_markup=Keyboards.even_odd_select()
        )
    elif bet_type == BetType.HIGH_LOW:
        await callback.message.edit_text(
            "📊 <b>Больше (4-6) или Меньше (1-3)?</b>",
            reply_markup=Keyboards.high_low_select()
        )
    elif bet_type == BetType.EXACT_NUMBER:
        await callback.message.edit_text(
            "🎯 <b>Выберите точное число (1-6):</b>",
            reply_markup=Keyboards.exact_number_select()
        )
    
    await callback.answer()


@router.callback_query(F.data == "back_bet_type", MatchStates.selecting_bet_value)
async def cb_back_bet_type(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору типа ставки"""
    data = await state.get_data()
    match_id = data.get("match_id")
    player_id = data.get("bet_player_id")
    
    if not match_id or not player_id:
        await callback.answer("Ошибка состояния", show_alert=True)
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
    
    available_types = storage.engine.get_available_bet_types(match, user.id, UUID(player_id))
    
    is_m1 = match.manager1_id == user.id
    has_bets = False
    if match.current_turn:
        has_bets = len(match.current_turn.manager1_bets if is_m1 else match.current_turn.manager2_bets) > 0
    
    await state.set_state(MatchStates.selecting_bet_type)
    await callback.message.edit_text(
        "🎯 <b>Выберите тип ставки:</b>",
        reply_markup=Keyboards.bet_type_select(available_types, has_existing_bets=has_bets)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_value:"), MatchStates.selecting_bet_value)
async def cb_bet_value_selected(callback: CallbackQuery, state: FSMContext):
    """Значение ставки выбрано"""
    value = callback.data.split(":")[1]
    
    data = await state.get_data()
    match_id = data.get("match_id")
    player_id = data.get("bet_player_id")
    bet_type_str = data.get("bet_type")
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    match = storage.get_match(UUID(match_id))
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    bet_type = BetType(bet_type_str)
    turn_number = match.current_turn.turn_number if match.current_turn else 1
    
    bet_params = {
        "match_id": match.id,
        "manager_id": user.id,
        "player_id": UUID(player_id),
        "turn_number": turn_number,
        "bet_type": bet_type,
    }
    
    if bet_type == BetType.EVEN_ODD:
        bet_params["even_odd_choice"] = EvenOddChoice(value)
    elif bet_type == BetType.HIGH_LOW:
        bet_params["high_low_choice"] = HighLowChoice(value)
    elif bet_type == BetType.EXACT_NUMBER:
        bet_params["exact_number"] = int(value)
    
    try:
        bet = Bet(**bet_params)
        match, _ = storage.engine.place_bet(match, user.id, UUID(player_id), bet)
        storage.save_match(match)
    except ValueError as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)
        return
    
    await state.set_state(MatchStates.in_game)
    
    # Проверяем, нужна ли ещё ставка
    available_types = storage.engine.get_available_bet_types(match, user.id, UUID(player_id))
    
    if available_types:
        await state.set_state(MatchStates.selecting_bet_type)
        await callback.message.edit_text(
            "✅ Первая ставка принята!\n\n"
            "🎯 <b>Выберите тип ВТОРОЙ ставки:</b>",
            reply_markup=Keyboards.bet_type_select(available_types, has_existing_bets=True)
        )
    else:
        # Возвращаемся к игровому экрану
        from .game import _render_game_screen
        await _render_game_screen(callback, state)
    
    await callback.answer("✅ Ставка принята!")


@router.callback_query(F.data == "cancel_bets")
async def cb_cancel_bets(callback: CallbackQuery, state: FSMContext):
    """Отменить все ставки текущего хода"""
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
            match_id = str(match.id)
            await state.update_data(match_id=match_id)
    else:
        match = storage.get_match(UUID(match_id))
    
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    try:
        match = storage.engine.cancel_turn_bets(match, user.id)
        storage.save_match(match)
        await callback.answer("🔄 Ставки отменены!")
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    await state.set_state(MatchStates.in_game)
    from .game import _render_game_screen
    await _render_game_screen(callback, state)


@router.callback_query(F.data == "confirm_bets", MatchStates.in_game)
async def cb_confirm_bets(callback: CallbackQuery, state: FSMContext):
    """Подтвердить ставки"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    match = storage.get_match(UUID(match_id))
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    try:
        storage.engine.confirm_bets(match, user.id)
        storage.save_match(match)
    except ValueError as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)
        return
    
    # Проверяем, нужно ли ботом сделать ставки (vs_bot)
    if match.match_type.value == "vs_bot":
        if not match.current_turn.manager2_ready:
            match = bot_make_bets(storage, match)
            storage.save_match(match)
        
        # Автоматически бросаем кубик
        from .game import _handle_roll_dice
        await _handle_roll_dice(callback, state, match, user)
        return
    
    # PvP
    is_m1 = match.manager1_id == user.id
    
    if match.current_turn.manager1_ready and match.current_turn.manager2_ready:
        # Оба подтвердили — manager1 бросает кубик
        if is_m1:
            await state.set_state(MatchStates.waiting_roll)
            renderer = MatchRenderer()
            bets_text = renderer.render_both_bets_before_roll(match, user.id)
            await callback.message.edit_text(
                "✅ <b>Оба подтвердили!</b>\n\n" + bets_text,
                reply_markup=Keyboards.roll_dice_button()
            )
        else:
            await notify_manager1_can_roll(callback.bot, match)
            await callback.message.edit_text(
                "✅ <b>Ставки подтверждены!</b>\n\n⏳ Ожидаем бросок соперника...",
                reply_markup=None
            )
    else:
        # Ждём соперника
        await callback.message.edit_text(
            "✅ <b>Ставки подтверждены!</b>\n\n⏳ Ожидаем подтверждения соперника...",
            reply_markup=None
        )
        if is_m1:
            await notify_opponent_waiting_for_roll(callback.bot, match, user.id)
    
    await callback.answer("✅ Ставки подтверждены!")
