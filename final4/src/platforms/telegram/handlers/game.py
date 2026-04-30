# src/platforms/telegram/handlers/game.py
"""Хендлеры игрового процесса (одновременные ставки)"""

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

router = Router(name="game")


async def _render_game_screen(callback: CallbackQuery, state: FSMContext, show_stats: bool = False):
    """Отрендерить игровой экран"""
    from aiogram.exceptions import TelegramBadRequest
    
    data = await state.get_data()
    match_id = data.get("match_id")
    
    if not match_id:
        await callback.message.edit_text(
            "❌ Матч не найден",
            reply_markup=Keyboards.main_menu()
        )
        return
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    match = storage.get_match(UUID(match_id))
    if not match:
        await callback.message.edit_text(
            "❌ Матч не найден",
            reply_markup=Keyboards.main_menu()
        )
        return
    
    renderer = MatchRenderer()
    text = renderer.render_match_status(match, user.id)
    
    # Информация о ходе
    if match.current_turn:
        text += "\n\n" + renderer.render_turn_info_simultaneous(match, user.id)
        
        # Показываем выбранного игрока и сделанные ставки
        is_user_m1 = match.manager1_id == user.id
        player_id = match.current_turn.manager1_player_id if is_user_m1 else match.current_turn.manager2_player_id
        bets_ids = match.current_turn.manager1_bets if is_user_m1 else match.current_turn.manager2_bets
        
        if player_id:
            team = match.team1 if is_user_m1 else match.team2
            player = team.get_player_by_id(player_id) if team else None
            if player:
                text += f"\n\n🎯 <b>Выбран игрок:</b> {player.name} ({player.position.value})"
                
                # Показываем сделанные ставки
                if bets_ids:
                    text += "\n📝 <b>Ваши ставки:</b>"
                    for bet_id in bets_ids:
                        bet = next((b for b in match.bets if b.id == bet_id), None)
                        if bet:
                            text += f"\n   • {bet.bet_type.value}: {bet.get_display_value()}"
    
    # Статистика команд
    if show_stats and match.team1 and match.team2:
        text += "\n\n" + renderer.render_team_stats(
            match.team1, 
            match=match,
            is_opponent=(match.manager1_id != user.id)
        )
        text += "\n\n" + renderer.render_team_stats(
            match.team2,
            match=match,
            is_opponent=(match.manager2_id != user.id)
        )
    
    # Определяем состояние кнопок
    turn = match.current_turn
    is_user_m1 = match.manager1_id == user.id
    
    # Сколько ставок сделано пользователем
    if turn:
        if is_user_m1:
            user_bets = len(turn.manager1_bets)
            is_confirmed = turn.manager1_ready
        else:
            user_bets = len(turn.manager2_bets)
            is_confirmed = turn.manager2_ready
        
        required_bets = turn.get_required_bets_count(match.phase)
        both_ready = turn.both_ready()
    else:
        user_bets = 0
        required_bets = 2
        is_confirmed = False
        both_ready = False
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=Keyboards.game_actions_simultaneous(
                bets_count=user_bets,
                required_bets=required_bets,
                is_confirmed=is_confirmed,
                both_ready=both_ready,
                dice_rolled=turn and turn.dice_rolled if turn else False
            )
        )
    except TelegramBadRequest:
        # Сообщение не изменилось — игнорируем
        pass


@router.callback_query(F.data == "back_to_game")
async def cb_back_to_game(callback: CallbackQuery, state: FSMContext):
    """Вернуться к игровому экрану"""
    await state.set_state(MatchStates.in_game)
    await _render_game_screen(callback, state)
    await callback.answer()


@router.callback_query(F.data == "open_match")
async def cb_open_match(callback: CallbackQuery, state: FSMContext):
    """Открыть текущий/последний матч (используется из уведомлений о таймауте)."""
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок",
    )

    # Сначала ищем активный матч, потом — последний завершённый
    match = storage.get_user_active_match(user.id) or storage.get_user_last_match(user.id)
    if not match:
        await callback.message.edit_text(
            "❌ Матч не найден",
            reply_markup=Keyboards.main_menu(),
        )
        await callback.answer()
        return

    await state.update_data(match_id=str(match.id))

    if match.status == MatchStatus.FINISHED:
        # Завершённый — показываем результат
        renderer = MatchRenderer()
        result_text = renderer.render_match_result(match, user.id)
        await state.set_state(None)
        await callback.message.edit_text(
            result_text,
            reply_markup=Keyboards.match_finished_menu(),
        )
    else:
        # Активный — рендерим игровой экран
        await state.set_state(MatchStates.in_game)
        await _render_game_screen(callback, state)
    await callback.answer()


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
    
    # Рендерим статистику обеих команд
    renderer = MatchRenderer()
    
    text_parts = []
    
    # Счёт матча
    is_user_m1 = match.manager1_id == user.id
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
        is_user_m1 = match.manager1_id == user.id
        
        text_parts.append(renderer.render_team_stats(
            match.team1 if is_user_m1 else match.team2,
            match=match,
            is_opponent=False
        ))
        text_parts.append("")
        text_parts.append(renderer.render_team_stats(
            match.team2 if is_user_m1 else match.team1,
            match=match,
            is_opponent=True
        ))
    
    text = "\n".join(text_parts)
    
    # Выбираем клавиатуру
    if match.status == MatchStatus.FINISHED:
        kb = Keyboards.match_finished_menu()
    else:
        kb = Keyboards.back_to_game()
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


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
    
    # Выбираем клавиатуру в зависимости от статуса матча
    if match.status == MatchStatus.FINISHED:
        kb = Keyboards.match_finished_menu()
    else:
        kb = Keyboards.back_to_game()
    
    await callback.message.edit_text(
        history_text,
        reply_markup=kb
    )
    await callback.answer()


# Обработчик для восстановления состояния (когда игрок получил уведомление через send_message)
@router.callback_query(F.data == "make_bet")
async def cb_make_bet_restore_state(callback: CallbackQuery, state: FSMContext):
    """Восстановить состояние и начать создание ставки (для PvP уведомлений)"""
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    # Ищем активный матч пользователя
    match = storage.get_user_active_match(user.id)
    if not match:
        await callback.answer("У вас нет активного матча", show_alert=True)
        return
    
    # Восстанавливаем состояние FSM
    await state.update_data(match_id=str(match.id))
    await state.set_state(MatchStates.in_game)
    
    # Теперь вызываем основную логику
    await _handle_make_bet(callback, state, match, user)


@router.callback_query(F.data == "make_bet", MatchStates.in_game)
async def cb_make_bet(callback: CallbackQuery, state: FSMContext):
    """Начать создание ставки"""
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
    
    await _handle_make_bet(callback, state, match, user)


async def _handle_make_bet(callback: CallbackQuery, state: FSMContext, match, user):
    """Основная логика создания ставки"""
    data = await state.get_data()
    current_bet_player_id = data.get("current_bet_player_id")  # Уже выбранный игрок
    
    storage = get_storage()
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    # Проверяем, не подтверждены ли уже ставки
    turn = match.current_turn
    is_user_m1 = match.manager1_id == user.id
    
    if turn:
        if is_user_m1 and turn.manager1_ready:
            await callback.answer("Вы уже подтвердили ставки!", show_alert=True)
            return
        if not is_user_m1 and turn.manager2_ready:
            await callback.answer("Вы уже подтвердили ставки!", show_alert=True)
            return
        
        # Проверяем, есть ли уже выбранный игрок в текущем ходе
        if is_user_m1 and turn.manager1_player_id:
            current_bet_player_id = str(turn.manager1_player_id)
        elif not is_user_m1 and turn.manager2_player_id:
            current_bet_player_id = str(turn.manager2_player_id)
    
    # Если игрок уже выбран — сразу к выбору типа ставки
    if current_bet_player_id:
        team = match.get_team(user.id)
        player = team.get_player_by_id(UUID(current_bet_player_id)) if team else None
        
        if player:
            available_types = storage.engine.get_available_bet_types(match, user.id, UUID(current_bet_player_id))
            
            if not available_types:
                # Объясняем причину и возвращаем к выбору игрока
                reason = storage.engine.bet_tracker.explain_unavailable_reason(
                    match, user.id, player
                )
                await callback.answer()
                # Сбрасываем привязку к этому игроку, чтобы можно было выбрать другого
                # ВАЖНО: только если первая ставка ещё не размещена
                turn_obj = match.current_turn
                first_bet_placed = False
                if turn_obj:
                    if is_user_m1 and turn_obj.manager1_bets:
                        first_bet_placed = True
                    elif not is_user_m1 and turn_obj.manager2_bets:
                        first_bet_placed = True

                if first_bet_placed:
                    # Игрок уже залочен первой ставкой — нельзя сменить.
                    # Показываем причину как ошибку (это не должно происходить
                    # с combo-aware фильтрами, но защитимся).
                    await callback.message.edit_text(
                        f"⚠️ <b>Невозможно сделать вторую ставку</b>\n\n{reason}\n\n"
                        f"<i>Это критическая ситуация — пожалуйста, сообщите разработчику.</i>",
                        reply_markup=Keyboards.game_actions_simultaneous(
                            bets_count=len(turn_obj.manager1_bets if is_user_m1 else turn_obj.manager2_bets),
                            required_bets=2,
                            is_confirmed=False,
                            both_ready=False,
                        )
                    )
                    return

                # Перерисовываем экран выбора игрока
                available_players = storage.engine.get_available_players(match, user.id)
                if available_players:
                    await state.set_state(MatchStates.selecting_bet_player)
                    await callback.message.edit_text(
                        f"⚠️ <b>Этот игрок недоступен для ставки</b>\n\n{reason}\n\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🎯 <b>Выберите другого игрока:</b>",
                        reply_markup=Keyboards.bet_player_select(available_players)
                    )
                else:
                    no_players_msg = storage.engine.bet_tracker.explain_no_available_players(
                        match, user.id
                    )
                    await callback.message.edit_text(
                        f"{reason}\n\n{no_players_msg}"
                    )
                return
            
            # Проверяем есть ли уже ставки в этом ходе
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
            await callback.answer()
            return
    
    # Иначе — выбор игрока
    available_players = storage.engine.get_available_players(match, user.id)
    
    # Логирование для отладки PvP
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[DEBUG] User {user.id} (is_m1={is_user_m1}), turn={turn.turn_number if turn else 'N/A'}")
    logger.info(f"[DEBUG] Available players: {len(available_players)}")
    
    if not available_players:
        # Дополнительная отладка
        team = match.get_team(user.id)
        if team:
            used = match.get_used_players(user.id)
            logger.warning(f"[DEBUG] Team has {len(team.players)} players, used: {len(used)}")
            logger.warning(f"[DEBUG] Used player IDs: {used}")
            logger.warning(f"[DEBUG] Phase: {match.phase}")
        else:
            logger.warning(f"[DEBUG] No team for user {user.id}!")
            logger.warning(f"[DEBUG] match.team1 manager: {match.manager1_id}, match.team2 manager: {match.manager2_id}")
        
        # Информативное сообщение пользователю с причиной
        reason_text = storage.engine.bet_tracker.explain_no_available_players(match, user.id)
        await callback.answer()
        try:
            await callback.message.edit_text(reason_text)
        except Exception:
            await callback.message.answer(reason_text)
        return
    
    # Отладка: показать сколько игроков использовано
    team = match.get_team(user.id)
    if team:
        used = match.get_used_players(user.id)
        logger.info(f"[DEBUG] Team {len(team.players)} players, used={len(used)}, available={len(available_players)}")
    
    await state.set_state(MatchStates.selecting_bet_player)
    await callback.message.edit_text(
        "🎯 <b>Выберите игрока для ставки:</b>",
        reply_markup=Keyboards.bet_player_select(available_players)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bet_player:"), MatchStates.selecting_bet_player)
async def cb_bet_player_selected(callback: CallbackQuery, state: FSMContext):
    """Игрок для ставки выбран"""
    player_id = callback.data.split(":")[1]
    
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
    
    # Получаем доступные типы ставок
    available_types = storage.engine.get_available_bet_types(match, user.id, UUID(player_id))
    
    if not available_types:
        # Объясняем причину и возвращаем к выбору игрока
        team = match.get_team(user.id)
        player = team.get_player_by_id(UUID(player_id)) if team else None
        if player:
            reason = storage.engine.bet_tracker.explain_unavailable_reason(
                match, user.id, player
            )
        else:
            reason = "Игрок не найден"

        await callback.answer()  # Сбрасываем "часики"
        # Перерисовываем экран выбора игрока с подсказкой почему текущий не подходит
        available_players = storage.engine.get_available_players(match, user.id)
        if available_players:
            await state.set_state(MatchStates.selecting_bet_player)
            await callback.message.edit_text(
                f"⚠️ <b>Этот игрок недоступен для ставки</b>\n\n{reason}\n\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>Выберите другого игрока:</b>",
                reply_markup=Keyboards.bet_player_select(available_players)
            )
        else:
            no_players_msg = storage.engine.bet_tracker.explain_no_available_players(
                match, user.id
            )
            await callback.message.edit_text(
                f"{reason}\n\n{no_players_msg}"
            )
        return
    
    await state.update_data(bet_player_id=player_id)
    await state.set_state(MatchStates.selecting_bet_type)
    
    # Информация о типах ставок
    phase = match.phase
    turn_num = match.current_turn.turn_number if match.current_turn else 1
    
    if phase == MatchPhase.EXTRA_TIME:
        info = "\n\n⚠️ <b>Дополнительное время:</b>\nОдна ставка ОБЯЗАТЕЛЬНО на гол!"
    elif turn_num == 1:
        info = "\n\n<i>Первый ход: только вратарь, 1 ставка</i>"
    else:
        info = "\n\n<i>Нужно 2 ставки РАЗНЫХ типов</i>"
    
    await callback.message.edit_text(
        "🎯 <b>Выберите тип ставки:</b>\n\n"
        "• <b>Чёт/Нечёт</b> — при выигрыше игрок получает отбития\n"
        "• <b>Больше/Меньше</b> — при выигрыше игрок получает передачи\n"
        "• <b>Точное число</b> — при выигрыше игрок забивает гол"
        + info,
        reply_markup=Keyboards.bet_type_select(available_types, has_existing_bets=False)
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
    
    # Проверяем есть ли ставки
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
    """Значение ставки выбрано — создаём ставку"""
    bet_value = callback.data.split(":")[1]
    
    data = await state.get_data()
    match_id = data.get("match_id")
    player_id = data.get("bet_player_id")
    bet_type_value = data.get("bet_type")
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    match = storage.get_match(UUID(match_id))
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    bet_type = BetType(bet_type_value)
    turn_number = match.current_turn.turn_number if match.current_turn else 1
    
    # Подготавливаем параметры ставки (все сразу!)
    bet_params = {
        "match_id": UUID(match_id),
        "manager_id": user.id,
        "player_id": UUID(player_id),
        "turn_number": turn_number,
        "bet_type": bet_type
    }
    
    # Устанавливаем значение в зависимости от типа
    if bet_type == BetType.EVEN_ODD:
        bet_params["even_odd_choice"] = EvenOddChoice(bet_value)
    elif bet_type == BetType.HIGH_LOW:
        bet_params["high_low_choice"] = HighLowChoice(bet_value)
    elif bet_type == BetType.EXACT_NUMBER:
        bet_params["exact_number"] = int(bet_value)
    
    try:
        bet = Bet(**bet_params)
        match, bet = storage.engine.place_bet(match, user.id, UUID(player_id), bet)
        storage.save_match(match)
        await callback.answer("✅ Ставка сделана!")
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    # Возвращаемся к игровому экрану
    await state.set_state(MatchStates.in_game)
    await _render_game_screen(callback, state)


@router.callback_query(F.data == "cancel_bets")
async def cb_cancel_bets(callback: CallbackQuery, state: FSMContext):
    """Отменить все ставки текущего хода (из любого состояния)"""
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
        match = storage.engine.confirm_bets(match, user.id)
        storage.save_match(match)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    # Для бота — автоматически делаем ставки
    if match.match_type.value == "vs_bot":
        match = _bot_make_bets(storage, match)
        storage.save_match(match)
    
    # Проверяем, можно ли бросить кубик (оба готовы)
    can_roll, reason = storage.engine.can_roll_dice(match)
    
    if can_roll:
        # СНАЧАЛА показываем ставки обоих игроков
        renderer = MatchRenderer()
        bets_text = renderer.render_both_bets_before_roll(match, user.id)
        
        # В PvP — только создатель матча (manager1) бросает кубик
        if match.match_type.value == "random":
            if user.id == match.manager1_id:
                # Manager1 — показываем кнопку броска
                await callback.message.edit_text(
                    bets_text,
                    reply_markup=Keyboards.roll_dice_button()
                )
                await state.set_state(MatchStates.waiting_roll)
                await callback.answer("✅ Ставки подтверждены! Бросайте кубик!")
                
                # Уведомляем manager2 что ждём броска
                await _notify_opponent_waiting_for_roll(callback.bot, match, user.id)
            else:
                # Manager2 — показываем ожидание
                await callback.message.edit_text(
                    bets_text + "\n\n⏳ <i>Ожидаем бросок соперника...</i>",
                    reply_markup=None
                )
                await state.set_state(MatchStates.waiting_roll)
                await callback.answer("✅ Ставки подтверждены! Ожидаем бросок соперника...")
                
                # Уведомляем manager1 что можно бросать
                await _notify_manager1_can_roll(callback.bot, match)
        else:
            # VS_BOT — игрок сам бросает
            await callback.message.edit_text(
                bets_text,
                reply_markup=Keyboards.roll_dice_button()
            )
            await state.set_state(MatchStates.waiting_roll)
            await callback.answer("✅ Ставки подтверждены!")
    else:
        await callback.answer("✅ Ставки подтверждены! Ожидаем соперника...")
        await _render_game_screen(callback, state)


async def _notify_opponent_waiting_for_roll(bot, match, roller_id: UUID):
    """Уведомить manager2 что ждём броска manager1"""
    storage = get_storage()
    
    opponent_id = match.manager2_id if roller_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        return
    
    renderer = MatchRenderer()
    bets_text = renderer.render_both_bets_before_roll(match, opponent_id)
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=bets_text + "\n\n⏳ <i>Ожидаем бросок соперника...</i>",
            reply_markup=None
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to notify opponent: {e}")


async def _notify_manager1_can_roll(bot, match):
    """Уведомить manager1 что можно бросать кубик"""
    storage = get_storage()
    
    manager1 = storage.get_user_by_id(match.manager1_id)
    if not manager1:
        return
    
    renderer = MatchRenderer()
    bets_text = renderer.render_both_bets_before_roll(match, match.manager1_id)
    
    try:
        await bot.send_message(
            chat_id=manager1.telegram_id,
            text="✅ <b>Соперник подтвердил ставки!</b>\n\n" + bets_text,
            reply_markup=Keyboards.roll_dice_button()
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to notify manager1: {e}")


async def _notify_opponent_turn_result(bot, match, roller_user_id: UUID, dice_value: int, won_bets):
    """Уведомить соперника о результатах хода (PvP)"""
    import logging
    logger = logging.getLogger(__name__)
    
    storage = get_storage()
    
    # Определяем соперника
    opponent_id = match.manager2_id if roller_user_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    logger.info(f"[PVP] Notifying opponent: roller={roller_user_id}, opponent_id={opponent_id}, opponent={opponent}")
    
    if not opponent:
        logger.warning(f"[PVP] Opponent not found! opponent_id={opponent_id}")
        return
    
    logger.info(f"[PVP] Opponent telegram_id={opponent.telegram_id}")
    
    renderer = MatchRenderer()
    text = renderer.render_dice_result_simultaneous(dice_value, won_bets, match, opponent_id)
    
    # Карточки
    cards_text = renderer.render_cards_drawn(match, opponent_id)
    if cards_text:
        text += "\n\n" + cards_text
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=text,
            reply_markup=Keyboards.game_actions_after_roll()
        )
        logger.info(f"[PVP] Notification sent successfully to {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent turn result: {e}")


async def _notify_penalty_owner_with_choice(bot, match, penalty_owner_id: UUID):
    """Отправить владельцу пенальти выбор High/Low (PvP)"""
    import logging
    logger = logging.getLogger(__name__)
    
    storage = get_storage()
    owner = storage.get_user_by_id(penalty_owner_id)
    
    if not owner:
        logger.warning(f"[PVP] Penalty owner not found: {penalty_owner_id}")
        return
    
    renderer = MatchRenderer()
    text = renderer.render_match_status(match, penalty_owner_id)
    text += "\n\n⚽ <b>У ВАС ПЕНАЛЬТИ!</b>\nВыберите, куда бьёте:"
    
    try:
        await bot.send_message(
            chat_id=owner.telegram_id,
            text=text,
            reply_markup=Keyboards.penalty_choice()
        )
        logger.info(f"[PVP] Penalty choice sent to {owner.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify penalty owner: {e}")


@router.callback_query(F.data == "roll_dice")
async def cb_roll_dice_restore(callback: CallbackQuery, state: FSMContext):
    """Бросить кубик (с восстановлением состояния)"""
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    # Ищем активный матч
    match = storage.get_user_active_match(user.id)
    if not match:
        await callback.answer("У вас нет активного матча", show_alert=True)
        return
    
    # В PvP только manager1 бросает кубик
    if match.match_type.value == "random" and user.id != match.manager1_id:
        await callback.answer("Только создатель матча бросает кубик!", show_alert=True)
        return
    
    # Проверяем, можно ли бросить (может кубик уже брошен)
    if match.current_turn and match.current_turn.dice_rolled:
        await callback.answer("Кубик уже брошен в этом ходу!", show_alert=True)
        return
    
    # Восстанавливаем состояние
    await state.update_data(match_id=str(match.id))
    await state.set_state(MatchStates.waiting_roll)
    
    # Вызываем основную логику
    await _handle_roll_dice(callback, state, match, user)


@router.callback_query(F.data == "roll_dice", MatchStates.waiting_roll)
async def cb_roll_dice(callback: CallbackQuery, state: FSMContext):
    """Бросить кубик"""
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
    
    # В PvP только manager1 бросает кубик
    if match.match_type.value == "random" and user.id != match.manager1_id:
        await callback.answer("Только создатель матча бросает кубик!", show_alert=True)
        return
    
    await _handle_roll_dice(callback, state, match, user)


async def _handle_roll_dice(callback: CallbackQuery, state: FSMContext, match, user):
    """Основная логика броска кубика"""
    storage = get_storage()

    # Tolerance: кубик уже брошен (соперником или таймером) — обновляем экран
    if match.current_turn and match.current_turn.dice_rolled:
        await state.set_state(MatchStates.in_game)
        await _render_game_screen(callback, state)
        await callback.answer("Кубик уже брошен")
        return

    # Бросаем кубик
    try:
        match, dice_value, won_bets = storage.engine.roll_dice(match)
        storage.save_match(match)
    except ValueError as e:
        # Гонка с таймером — обновляем экран
        logger.warning(f"[BOT] roll_dice failed (likely timer race): {e}")
        await state.set_state(MatchStates.in_game)
        await _render_game_screen(callback, state)
        await callback.answer()
        return
    
    renderer = MatchRenderer()
    
    # Показываем результат
    text = renderer.render_dice_result_simultaneous(dice_value, won_bets, match, user.id)
    
    # Карточки уже вытянуты автоматически
    cards_text = renderer.render_cards_drawn(match, user.id)
    if cards_text:
        text += "\n\n" + cards_text
    
    # Проверяем, нужен ли розыгрыш пенальти
    if match.current_turn and match.current_turn.waiting_for_penalty_roll:
        # Определяем, чей пенальти
        from src.core.models.whistle_card import CardType
        from src.core.engine.game_engine import BOT_USER_ID
        
        penalty_owner = None
        for card in match.whistle_cards_drawn:
            if (card.card_type == CardType.PENALTY and 
                card.turn_applied == match.current_turn.turn_number and
                card.penalty_scored is None):
                penalty_owner = card.applied_by_manager_id
                break
        
        if penalty_owner == BOT_USER_ID:
            # Пенальти бота — автоматический выбор и бросок
            import random
            bot_choice = random.choice(["high", "low"])
            match, success, pen_dice = storage.engine.resolve_penalty(match, BOT_USER_ID, bot_choice)
            storage.save_match(match)
            
            choice_text = "Больше" if bot_choice == "high" else "Меньше"
            if success:
                text += f"\n\n⚽ <b>ПЕНАЛЬТИ БОТА!</b>\nБот выбрал: {choice_text}\n🎲 Выпало: {pen_dice}\n❌ Бот забил гол!"
            else:
                text += f"\n\n⚽ <b>ПЕНАЛЬТИ БОТА!</b>\nБот выбрал: {choice_text}\n🎲 Выпало: {pen_dice}\n✅ Вы отбили!"
        elif penalty_owner == user.id:
            # Пенальти ТЕКУЩЕГО пользователя — показываем выбор High/Low
            text += "\n\n⚽ <b>ПЕНАЛЬТИ!</b>\nВыберите, куда бьёте:"
            
            await state.set_state(MatchStates.penalty_kick)
            await callback.message.edit_text(
                text,
                reply_markup=Keyboards.penalty_choice()
            )
            await callback.answer("⚽ У вас пенальти!")
            return
        else:
            # Пенальти СОПЕРНИКА в PvP — показываем текущему результаты, а сопернику отправляем пенальти
            if match.match_type.value == "random":
                # Отправляем владельцу пенальти его выбор
                await _notify_penalty_owner_with_choice(callback.bot, match, penalty_owner)
                
                # Текущему пользователю показываем ожидание
                text += "\n\n⚽ <b>ПЕНАЛЬТИ СОПЕРНИКА!</b>\n⏳ Ожидаем решение соперника..."
                await callback.message.edit_text(text, reply_markup=None)
                await callback.answer("⚽ Пенальти соперника!")
                return
    
    # Проверяем, нужен ли выбор по жёлтой карточке (предупреждение)
    if match.current_turn and match.current_turn.waiting_for_yellow_card_choice:
        from src.core.engine.game_engine import BOT_USER_ID
        
        target_mgr = match.current_turn.yellow_card_target_manager_id  # КТО ВЫБИРАЕТ (соперник владельца)
        target_pid = match.current_turn.yellow_card_target_player_id  # игрок к которому применяется
        
        if target_mgr and target_pid:
            # Находим целевого игрока в любой из команд (он принадлежит НЕ выбирающему)
            target_player = None
            owner_mgr_id = None
            for t in [match.team1, match.team2]:
                if t:
                    p = t.get_player_by_id(target_pid)
                    if p:
                        target_player = p
                        owner_mgr_id = t.manager_id
                        break
            
            if target_player:
                has_goals = target_player.stats.goals > 0
                has_passes = target_player.stats.passes > 0
                has_saves = target_player.stats.saves > 0
                
                if not has_goals and not has_passes and not has_saves:
                    # Нет действий — карточка ничего не делает
                    match.current_turn.waiting_for_yellow_card_choice = False
                    match.current_turn.yellow_card_target_manager_id = None
                    match.current_turn.yellow_card_target_player_id = None
                    match.current_turn.yellow_card_id = None
                    storage.save_match(match)
                    text += f"\n\n🟡 <b>Предупреждение!</b> У игрока {target_player.name} нет действий — карточка не повлияла."
                elif target_mgr == BOT_USER_ID:
                    # Бот-выбирающий: убирает наименее ценное (отбитие > передача > гол)
                    if has_saves:
                        bot_action = "save"
                    elif has_passes:
                        bot_action = "pass"
                    else:
                        bot_action = "goal"
                    match = storage.engine.resolve_yellow_card(match, BOT_USER_ID, bot_action)
                    storage.save_match(match)
                    action_names = {"save": "отбитие", "pass": "передачу", "goal": "гол"}
                    text += f"\n\n🟡 <b>Предупреждение!</b> Бот убрал у {target_player.name} {action_names[bot_action]}."
                elif target_mgr == user.id:
                    # Я — выбирающий (соперник владельца игрока). Игрок чужой.
                    text += (
                        f"\n\n🟡 <b>ПРЕДУПРЕЖДЕНИЕ!</b>\n"
                        f"Игрок соперника <b>{target_player.name}</b> получил жёлтую карточку.\n"
                        f"Выберите, какое действие убрать:"
                    )
                    
                    await state.set_state(MatchStates.yellow_card_choice)
                    await callback.message.edit_text(
                        text,
                        reply_markup=Keyboards.yellow_card_choice(has_goals, has_passes, has_saves)
                    )
                    await callback.answer("🟡 Предупреждение!")
                    return
                else:
                    # PvP — выбор у соперника, отправим ему уведомление
                    if match.match_type.value == "random":
                        await _notify_yellow_card_owner_with_choice(callback.bot, match, target_mgr)
                        text += (
                            f"\n\n🟡 <b>ПРЕДУПРЕЖДЕНИЕ!</b>\n"
                            f"Ваш игрок <b>{target_player.name}</b> получил жёлтую карточку.\n"
                            f"⏳ Соперник выбирает, какое действие убрать..."
                        )
                        await callback.message.edit_text(text, reply_markup=None)
                        await callback.answer("🟡 Предупреждение!")
                        return
    
    await state.set_state(MatchStates.in_game)
    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.game_actions_after_roll()
    )
    await callback.answer(f"🎲 Выпало: {dice_value}!")
    
    # Для PvP — уведомляем соперника о результатах хода
    if match.match_type.value == "random":
        await _notify_opponent_turn_result(callback.bot, match, user.id, dice_value, won_bets)


@router.callback_query(F.data.startswith("penalty_choice:"))
async def cb_penalty_choice(callback: CallbackQuery, state: FSMContext):
    """Выбор High/Low для пенальти — показываем кнопку броска"""
    choice = callback.data.split(":")[1]  # "high" или "low"
    
    # Восстанавливаем состояние из активного матча
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    match = storage.get_user_active_match(user.id)
    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return
    
    await state.update_data(match_id=str(match.id), penalty_choice=choice)
    await state.set_state(MatchStates.penalty_choice_made)
    
    choice_text = "⬆️ Больше (4-6)" if choice == "high" else "⬇️ Меньше (1-3)"
    
    await callback.message.edit_text(
        f"⚽ <b>ПЕНАЛЬТИ!</b>\n\n"
        f"Ваш выбор: <b>{choice_text}</b>\n\n"
        f"Нажмите кнопку, чтобы бросить кубик!",
        reply_markup=Keyboards.penalty_roll_button()
    )
    await callback.answer()


@router.callback_query(F.data == "penalty_roll")
async def cb_penalty_roll(callback: CallbackQuery, state: FSMContext):
    """Бросок кубика для пенальти"""
    data = await state.get_data()
    match_id = data.get("match_id")
    choice = data.get("penalty_choice")
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    # Восстанавливаем матч если нет в состоянии
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
    
    if not choice:
        await callback.answer("Сначала выберите Больше или Меньше!", show_alert=True)
        return
    
    try:
        match, success, dice_value = storage.engine.resolve_penalty(match, user.id, choice)
        storage.save_match(match)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    # Формируем результат с визуальным броском
    dice_emoji = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    choice_text = "Больше (4-6)" if choice == "high" else "Меньше (1-3)"
    
    result_text = f"⚽ <b>ПЕНАЛЬТИ!</b>\n\n"
    result_text += f"Ваш выбор: <b>{choice_text}</b>\n\n"
    result_text += f"🎲 Бросок: <b>{dice_emoji[dice_value]} {dice_value}</b>\n\n"
    
    if success:
        result_text += "✅ <b>ГОЛ!</b> Вы угадали!"
    else:
        result_text += "❌ <b>Промах!</b> Вратарь отбил!"
    
    renderer = MatchRenderer()
    status_text = renderer.render_match_status(match, user.id)
    
    # Карточки
    cards_text = renderer.render_cards_drawn(match, user.id)
    if cards_text:
        result_text += "\n\n" + cards_text
    
    await state.set_state(MatchStates.in_game)
    await callback.message.edit_text(
        status_text + "\n\n" + result_text,
        reply_markup=Keyboards.game_actions_after_roll()
    )
    await callback.answer("⚽ ГОЛ!" if success else "❌ Промах!")
    
    # В PvP — уведомляем соперника о результате пенальти
    if match.match_type.value == "random":
        await _notify_opponent_penalty_result(callback.bot, match, user.id, success, dice_value, choice)


async def _notify_opponent_penalty_result(bot, match, penalty_user_id: UUID, success: bool, dice_value: int, choice: str):
    """Уведомить соперника о результате пенальти"""
    import logging
    logger = logging.getLogger(__name__)
    
    storage = get_storage()
    
    opponent_id = match.manager2_id if penalty_user_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        return
    
    renderer = MatchRenderer()
    
    dice_emoji = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    choice_text = "Больше (4-6)" if choice == "high" else "Меньше (1-3)"
    
    if success:
        result_text = f"⚽ <b>ПЕНАЛЬТИ СОПЕРНИКА</b>\n\nСоперник выбрал: {choice_text}\n🎲 Выпало: {dice_emoji[dice_value]} {dice_value}\n\n❌ Соперник забил гол!"
    else:
        result_text = f"⚽ <b>ПЕНАЛЬТИ СОПЕРНИКА</b>\n\nСоперник выбрал: {choice_text}\n🎲 Выпало: {dice_emoji[dice_value]} {dice_value}\n\n✅ Вы отбили!"
    
    status_text = renderer.render_match_status(match, opponent_id)
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=status_text + "\n\n" + result_text,
            reply_markup=Keyboards.game_actions_after_roll()
        )
        logger.info(f"[PVP] Penalty result sent to opponent {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent penalty result: {e}")


# ==================== ЖЁЛТАЯ КАРТОЧКА (ПРЕДУПРЕЖДЕНИЕ) ====================


async def _notify_yellow_card_owner_with_choice(bot, match, chooser_manager_id: UUID):
    """Отправить СОПЕРНИКУ владельца игрока выбор, какое действие убрать (PvP).

    chooser_manager_id — менеджер, КОТОРЫЙ ВЫБИРАЕТ (соперник владельца).
    Целевой игрок принадлежит другому менеджеру (владельцу).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    storage = get_storage()
    chooser = storage.get_user_by_id(chooser_manager_id)
    
    if not chooser:
        logger.warning(f"[PVP] Yellow card chooser not found: {chooser_manager_id}")
        return
    
    # Находим целевого игрока в любой команде
    target_pid = match.current_turn.yellow_card_target_player_id
    target_player = None
    for t in [match.team1, match.team2]:
        if t:
            p = t.get_player_by_id(target_pid) if target_pid else None
            if p:
                target_player = p
                break
    
    if not target_player:
        return
    
    has_goals = target_player.stats.goals > 0
    has_passes = target_player.stats.passes > 0
    has_saves = target_player.stats.saves > 0
    
    text = (
        f"🟡 <b>ПРЕДУПРЕЖДЕНИЕ!</b>\n\n"
        f"Игрок соперника <b>{target_player.name}</b> получил жёлтую карточку.\n"
        f"Текущие действия: "
    )
    stats_parts = []
    if target_player.stats.goals > 0:
        stats_parts.append(f"⚽{target_player.stats.goals}")
    if target_player.stats.passes > 0:
        stats_parts.append(f"🎯{target_player.stats.passes}")
    if target_player.stats.saves > 0:
        stats_parts.append(f"🛡{target_player.stats.saves}")
    text += " ".join(stats_parts) if stats_parts else "нет"
    text += "\n\nВыберите, какое действие убрать:"
    
    try:
        await bot.send_message(
            chat_id=chooser.telegram_id,
            text=text,
            reply_markup=Keyboards.yellow_card_choice(has_goals, has_passes, has_saves)
        )
        logger.info(f"[PVP] Yellow card choice sent to chooser {chooser.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify yellow card chooser: {e}")


@router.callback_query(F.data.startswith("yellow_card_action:"))
async def cb_yellow_card_action(callback: CallbackQuery, state: FSMContext):
    """Соперник выбрал, какое действие потерять при предупреждении"""
    action_type = callback.data.split(":")[1]  # "goal", "pass", "save"
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    # Находим матч
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
        await _notify_opponent_yellow_card_result(callback.bot, match, user.id, action_type)


async def _notify_opponent_yellow_card_result(bot, match, affected_manager_id: UUID, action_type: str):
    """Уведомить соперника о результате предупреждения"""
    import logging
    logger = logging.getLogger(__name__)
    
    storage = get_storage()
    
    opponent_id = match.manager2_id if affected_manager_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        return
    
    action_names = {"goal": "гол", "pass": "передачу", "save": "отбитие"}
    text = f"🟡 <b>Предупреждение!</b>\nСоперник потерял {action_names.get(action_type, action_type)}."
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=text,
            reply_markup=Keyboards.game_actions_after_roll()
        )
        logger.info(f"[PVP] Yellow card result sent to opponent {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent yellow card result: {e}")


@router.callback_query(F.data == "end_turn")
async def cb_end_turn_restore(callback: CallbackQuery, state: FSMContext):
    """Завершить ход (с восстановлением состояния)"""
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    # Ищем активный матч
    match = storage.get_user_active_match(user.id)
    if not match:
        await callback.answer("У вас нет активного матча", show_alert=True)
        return
    
    # Восстанавливаем состояние
    await state.update_data(match_id=str(match.id))
    await state.set_state(MatchStates.in_game)
    
    await _handle_end_turn(callback, state, match, user)


@router.callback_query(F.data == "end_turn", MatchStates.in_game)
async def cb_end_turn(callback: CallbackQuery, state: FSMContext):
    """Завершить ход"""
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
    
    await _handle_end_turn(callback, state, match, user)


async def _handle_end_turn(callback: CallbackQuery, state: FSMContext, match, user):
    """Основная логика завершения хода"""
    storage = get_storage()

    # Tolerance: ход уже завершён автоматически (таймер) или соперником —
    # просто рендерим актуальный экран без ошибки
    if not match.current_turn or not match.current_turn.dice_rolled or match.status == MatchStatus.FINISHED:
        # Матч закончен или ход уже завершён до нас
        if match.status == MatchStatus.FINISHED:
            renderer = MatchRenderer()
            result_text = renderer.render_match_result(match, user.id)
            await state.update_data(match_id=str(match.id))
            await state.set_state(None)
            await callback.message.edit_text(
                result_text,
                reply_markup=Keyboards.match_finished_menu()
            )
            await callback.answer()
            return
        else:
            # Активный матч, но текущий ход уже не на той стадии
            await state.set_state(MatchStates.in_game)
            await _render_game_screen(callback, state)
            await callback.answer("Ход уже завершён автоматически")
            return

    # В PvP только manager1 завершает ход
    if match.match_type.value == "random" and user.id != match.manager1_id:
        await callback.answer("Ожидайте, пока соперник завершит ход", show_alert=True)
        return

    try:
        match = storage.engine.end_turn(match)
        storage.save_match(match)
    except ValueError as e:
        # Если ошибка — возможно гонка с таймером, попробуем перерендерить
        logger.warning(f"[BOT] end_turn failed (likely timer race): {e}")
        await state.set_state(MatchStates.in_game)
        await _render_game_screen(callback, state)
        await callback.answer()
        return

    # Управление таймером хода (60 сек)
    from src.platforms.telegram.turn_timer import arm_turn_timer, cancel_match_timers
    if match.status == MatchStatus.FINISHED:
        cancel_match_timers(match.id)
    elif match.status in (MatchStatus.IN_PROGRESS, MatchStatus.EXTRA_TIME) and match.current_turn:
        arm_turn_timer(callback.bot, storage, match)
    
    # Проверяем статус матча
    if match.status == MatchStatus.FINISHED:
        renderer = MatchRenderer()
        result_text = renderer.render_match_result(match, user.id)
        
        # Обновляем рейтинг (ELO) — идемпотентно, для обоих участников
        if match.result:
            from src.platforms.telegram.rating import apply_match_rating
            apply_match_rating(storage, match)
        
        # Сохраняем match_id в состоянии для доступа к истории/статистике
        await state.update_data(match_id=str(match.id))
        await state.set_state(None)
        await callback.message.edit_text(
            result_text,
            reply_markup=Keyboards.match_finished_menu()
        )
        
        # В PvP — уведомляем соперника о результате
        if match.match_type.value == "random":
            await _notify_opponent_match_finished(callback.bot, match, user.id, "finished")
    elif match.status == MatchStatus.EXTRA_TIME:
        await callback.message.edit_text(
            "⏱ <b>ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ!</b>\n\n"
            "Счёт равный, начинаем дополнительные 5 ходов.\n"
            "⚠️ Каждый игрок ОБЯЗАН делать ставку на гол!",
            reply_markup=Keyboards.game_actions_simultaneous(0, 2, False, False)
        )
        await state.set_state(MatchStates.in_game)
        
        # В PvP — уведомляем соперника о переходе в Extra Time
        if match.match_type.value == "random":
            await _notify_opponent_extra_time(callback.bot, match, user.id)
    elif match.status == MatchStatus.PENALTIES:
        # Автоматические пенальти
        match = _auto_penalties(storage, match)
        storage.save_match(match)

        # Обновляем рейтинг
        from src.platforms.telegram.rating import apply_match_rating
        apply_match_rating(storage, match)

        renderer = MatchRenderer()
        result_text = renderer.render_match_result(match, user.id)
        
        await state.update_data(match_id=str(match.id))
        await state.set_state(None)
        await callback.message.edit_text(
            "⚽ <b>СЕРИЯ ПЕНАЛЬТИ!</b>\n\n" + result_text,
            reply_markup=Keyboards.match_finished_menu()
        )
        
        # В PvP — уведомляем соперника о результате
        if match.match_type.value == "random":
            await _notify_opponent_match_finished(callback.bot, match, user.id, "penalties")
    
    elif match.status == MatchStatus.FINISHED:
        # Матч завершён
        # Обновляем рейтинг (на случай если первая ветка FINISHED не сработала)
        from src.platforms.telegram.rating import apply_match_rating
        apply_match_rating(storage, match)

        renderer = MatchRenderer()
        result_text = renderer.render_match_result(match, user.id)
        
        await state.update_data(match_id=str(match.id))
        await state.set_state(None)
        await callback.message.edit_text(
            result_text,
            reply_markup=Keyboards.match_finished_menu()
        )
        
        # В PvP — уведомляем соперника о результате
        if match.match_type.value == "random":
            await _notify_opponent_match_finished(callback.bot, match, user.id, "finished")
    else:
        # Следующий ход
        await _render_game_screen(callback, state)
        
        # В PvP — уведомляем соперника о новом ходе
        if match.match_type.value == "random":
            await _notify_opponent_new_turn(callback.bot, match, user.id)
    
    await callback.answer()


async def _notify_opponent_match_finished(bot, match, user_id: UUID, finish_type: str):
    """Уведомить соперника о завершении матча (PvP)"""
    import logging
    logger = logging.getLogger(__name__)
    
    storage = get_storage()
    
    opponent_id = match.manager2_id if user_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        logger.warning(f"[PVP] Opponent not found for match finished notification")
        return
    
    renderer = MatchRenderer()
    result_text = renderer.render_match_result(match, opponent_id)
    
    if finish_type == "penalties":
        text = "⚽ <b>СЕРИЯ ПЕНАЛЬТИ!</b>\n\n" + result_text
    else:
        text = result_text
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=text,
            reply_markup=Keyboards.match_finished_menu()
        )
        logger.info(f"[PVP] Match finished notification sent to {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent match finished: {e}")


async def _notify_opponent_extra_time(bot, match, user_id: UUID):
    """Уведомить соперника о переходе в Extra Time (PvP)"""
    import logging
    logger = logging.getLogger(__name__)
    
    storage = get_storage()
    
    opponent_id = match.manager2_id if user_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        return
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text="⏱ <b>ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ!</b>\n\n"
                 "Счёт равный, начинаем дополнительные 5 ходов.\n"
                 "⚠️ Каждый игрок ОБЯЗАН делать ставку на гол!",
            reply_markup=Keyboards.game_actions_simultaneous(0, 2, False, False)
        )
        logger.info(f"[PVP] Extra time notification sent to {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent extra time: {e}")


async def _notify_opponent_new_turn(bot, match, user_id: UUID):
    """Уведомить соперника о новом ходе (PvP)"""
    import logging
    logger = logging.getLogger(__name__)
    
    storage = get_storage()
    
    opponent_id = match.manager2_id if user_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        logger.warning(f"[PVP] Opponent not found for new turn notification")
        return
    
    renderer = MatchRenderer()
    text = renderer.render_match_status(match, opponent_id)
    text += "\n\n" + renderer.render_turn_info_simultaneous(match, opponent_id)
    
    # Считаем ставки этого хода
    turn_num = match.current_turn.turn_number if match.current_turn else 1
    bets_count = len([b for b in match.bets 
                      if b.manager_id == opponent_id and b.turn_number == turn_num])
    # В Extra Time всегда 2 ставки
    from src.core.models.match import MatchPhase
    required_bets = 2 if match.phase == MatchPhase.EXTRA_TIME else (1 if turn_num == 1 else 2)
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=f"➡️ <b>Ход {turn_num}</b>\n\n" + text,
            reply_markup=Keyboards.game_actions_simultaneous(
                bets_count=bets_count,
                required_bets=required_bets,
                is_confirmed=False,
                both_ready=False
            )
        )
        logger.info(f"[PVP] New turn notification sent to {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent new turn: {e}")


def _bot_make_bets(storage, match):
    """Бот делает ставки"""
    import logging
    logger = logging.getLogger(__name__)
    
    engine = storage.engine
    
    # Получаем доступных игроков для бота
    available = engine.get_available_players(match, BOT_USER_ID)
    logger.info(f"[BOT] Available players for bot: {len(available) if available else 0}")
    
    if not available:
        logger.warning(f"[BOT] No available players for bot! Match phase: {match.phase}, turn: {match.current_turn}")
        return match
    
    # Выбираем случайного игрока
    player = random.choice(available)
    logger.info(f"[BOT] Selected player: {player.name} ({player.position})")
    
    # Определяем количество ставок
    turn_num = match.current_turn.turn_number if match.current_turn else 1
    # В Extra Time всегда 2 ставки
    from src.core.models.match import MatchPhase
    required_bets = 2 if match.phase == MatchPhase.EXTRA_TIME else (1 if turn_num == 1 else 2)
    logger.info(f"[BOT] Turn {turn_num}, required bets: {required_bets}, phase: {match.phase}")
    
    for i in range(required_bets):
        # Получаем доступные типы КАЖДЫЙ раз (они меняются после первой ставки, особенно в ET)
        available_types = engine.get_available_bet_types(match, BOT_USER_ID, player.id)
        logger.info(f"[BOT] Bet {i+1}: available types = {available_types}")
        
        if not available_types:
            logger.warning(f"[BOT] No available bet types for bet {i+1}")
            break
        
        bet_type = random.choice(available_types)
        
        # Создаём ставку со всеми параметрами СРАЗУ
        bet_params = {
            "match_id": match.id,
            "manager_id": BOT_USER_ID,
            "player_id": player.id,
            "turn_number": turn_num,
            "bet_type": bet_type
        }
        
        if bet_type == BetType.EVEN_ODD:
            bet_params["even_odd_choice"] = random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
        elif bet_type == BetType.HIGH_LOW:
            bet_params["high_low_choice"] = random.choice([HighLowChoice.HIGH, HighLowChoice.LOW])
        elif bet_type == BetType.EXACT_NUMBER:
            bet_params["exact_number"] = random.randint(1, 6)
        
        try:
            bet = Bet(**bet_params)
            match, _ = engine.place_bet(match, BOT_USER_ID, player.id, bet)
            logger.info(f"[BOT] Placed bet: {bet_type}")
        except ValueError as e:
            logger.error(f"[BOT] Failed to place bet: {e}")
    
    # Подтверждаем ставки бота
    try:
        match = engine.confirm_bets(match, BOT_USER_ID)
        logger.info(f"[BOT] Bets confirmed! Manager2 ready: {match.current_turn.manager2_ready if match.current_turn else 'N/A'}")
    except ValueError as e:
        logger.error(f"[BOT] Failed to confirm bets: {e}")
    
    return match


def _auto_penalties(storage, match):
    """Автоматическая серия пенальти с сохранением результатов каждого удара.

    Правила:
    1. Регулярная серия: 5 ударов от каждой команды (всего до 10).
       Игроки берутся в порядке: ET (с последнего хода), затем Main Time
       (с 11-го хода до 1-го).
    2. Если после 5 ударов счёт равный — серия до первого промаха
       ("sudden death"): продолжаем по 1 удару от каждой команды парами.
       После каждой пары проверяем: если счёт стал неравный — победитель
       определён.
    3. Если игроки в команде закончились — финиш по жребию (крайне редко).
    """
    engine = storage.engine
    history = engine.get_match_history(match)

    if not history:
        return engine.finish_by_lottery(match)

    from src.core.models.match import PenaltyKick

    players1 = history.get_all_players_ordered_for_penalties(match.manager1_id, match.manager1_id)
    players2 = history.get_all_players_ordered_for_penalties(match.manager2_id, match.manager1_id)

    goals1, goals2 = 0, 0
    penalty_results: list = []

    def _kick(player_stats, manager_id, sudden_death=False):
        scored = player_stats.passes > 0
        penalty_results.append(PenaltyKick(
            manager_id=manager_id,
            player_name=player_stats.player_name,
            scored=scored,
            sudden_death=sudden_death,
        ))
        return scored

    # 1) Регулярная серия — до 5 ударов от каждой команды
    initial_kicks = min(5, len(players1), len(players2))
    for i in range(initial_kicks):
        if _kick(players1[i], match.manager1_id):
            goals1 += 1
        if _kick(players2[i], match.manager2_id):
            goals2 += 1

    # 2) Серия до промаха (sudden death) — пока счёт равный и есть игроки
    next_idx = initial_kicks
    max_pool = min(len(players1), len(players2))
    while goals1 == goals2 and next_idx < max_pool:
        if _kick(players1[next_idx], match.manager1_id, sudden_death=True):
            goals1 += 1
        if _kick(players2[next_idx], match.manager2_id, sudden_death=True):
            goals2 += 1
        next_idx += 1

    match.penalty_results = penalty_results
    match.penalty_score_m1 = goals1
    match.penalty_score_m2 = goals2
    match.score.manager1_goals += goals1
    match.score.manager2_goals += goals2

    if goals1 > goals2:
        winner_id = match.manager1_id
    elif goals2 > goals1:
        winner_id = match.manager2_id
    else:
        # Игроки закончились, всё ещё ничья — жребий (крайне редкий случай)
        winner_id = random.choice([match.manager1_id, match.manager2_id])

    match = engine.finish_penalty_shootout(match, winner_id)
    return match
