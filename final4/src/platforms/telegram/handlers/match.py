# src/platforms/telegram/handlers/match.py
"""Хендлеры создания и управления матчами"""

from uuid import UUID
import copy

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from src.core.models.match import MatchType, MatchStatus
from src.core.models.team import Team
from src.core.models.player import Player, Position

from ..keyboards.inline import Keyboards
from ..states.game_states import MatchStates
from ..renderers.match_renderer import MatchRenderer
from ..storage import get_storage

router = Router(name="match")


@router.callback_query(F.data == "play_random")
async def cb_play_random(callback: CallbackQuery, state: FSMContext):
    """Поиск случайного соперника"""
    storage = get_storage()
    
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    # Проверяем активный матч
    active = storage.get_user_active_match(user.id)
    if active:
        await callback.answer("У вас уже есть активный матч!", show_alert=True)
        return
    
    # Ищем ожидающий матч
    waiting_match = storage.find_waiting_match(exclude_user_id=user.id)
    
    if waiting_match:
        # Нашли соперника — присоединяемся!
        await _join_existing_match(callback, state, user, waiting_match)
    else:
        # Создаём новый матч и ждём соперника
        await _create_waiting_match(callback, state, user)


async def _create_waiting_match(callback: CallbackQuery, state: FSMContext, user):
    """Создать матч и ждать соперника"""
    storage = get_storage()
    
    # Создаём матч PvP
    match = storage.engine.create_match(user.id, MatchType.RANDOM, platform="telegram")
    match.status = MatchStatus.WAITING_FOR_OPPONENT
    
    # Команда пользователя
    user_team_template = storage.get_user_team(user.id)
    if not user_team_template:
        user_team_template = storage._create_default_team(user.id, user.username)
    
    user_team = copy.deepcopy(user_team_template)
    for player in user_team.players:
        player.stats.saves = 0
        player.stats.passes = 0
        player.stats.goals = 0
        player.is_available = True
    
    match = storage.engine.set_team_without_formation(match, user.id, user_team)
    
    storage.save_match(match)
    storage.add_waiting_match(match.id)
    
    # Сохраняем telegram_id создателя матча для уведомления
    storage.match_creators = getattr(storage, 'match_creators', {})
    storage.match_creators[match.id] = callback.from_user.id
    
    await state.update_data(match_id=str(match.id), waiting_for_opponent=True)
    await state.set_state(MatchStates.waiting_opponent)
    
    await callback.message.edit_text(
        "🔍 <b>Поиск соперника...</b>\n\n"
        "Ожидаем, пока кто-то присоединится к игре.\n"
        "Это может занять некоторое время.",
        reply_markup=Keyboards.cancel_search()
    )
    await callback.answer("🔍 Ищем соперника...")


async def _join_existing_match(callback: CallbackQuery, state: FSMContext, user, match):
    """Присоединиться к существующему матчу"""
    storage = get_storage()
    
    # Убираем из очереди
    storage.remove_waiting_match(match.id)
    
    # Присоединяем второго игрока
    match.manager2_id = user.id
    
    # Команда второго игрока
    user_team_template = storage.get_user_team(user.id)
    if not user_team_template:
        user_team_template = storage._create_default_team(user.id, user.username)
    
    user_team = copy.deepcopy(user_team_template)
    for player in user_team.players:
        player.stats.saves = 0
        player.stats.passes = 0
        player.stats.goals = 0
        player.is_available = True
    
    match = storage.engine.set_team_without_formation(match, user.id, user_team)
    
    # start_match уже вызывается внутри set_team_without_formation когда обе команды готовы
    storage.save_match(match)
    
    # Сохраняем состояние для второго игрока
    await state.update_data(match_id=str(match.id))
    await state.set_state(MatchStates.in_game)
    
    renderer = MatchRenderer()
    
    # Уведомляем второго игрока (текущего)
    opponent = storage.get_user_by_id(match.manager1_id)
    opponent_name = opponent.username if opponent else "Соперник"
    
    text = f"✅ <b>Соперник найден!</b>\n"
    text += f"Вы играете против: <b>{opponent_name}</b>\n\n"
    text += renderer.render_match_status(match, user.id)
    text += "\n\n" + renderer.render_turn_info_simultaneous(match, user.id)
    
    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.game_actions_simultaneous(
            bets_count=0,
            required_bets=1,
            is_confirmed=False,
            both_ready=False
        )
    )
    await callback.answer("🎮 Соперник найден! Матч начинается!")
    
    # Уведомляем первого игрока (создателя)
    await _notify_opponent_found(callback.bot, match, user)


async def _notify_opponent_found(bot: Bot, match, joining_user):
    """Уведомить создателя матча, что соперник найден"""
    storage = get_storage()
    
    # Получаем telegram_id создателя
    match_creators = getattr(storage, 'match_creators', {})
    creator_telegram_id = match_creators.get(match.id)
    
    if not creator_telegram_id:
        return
    
    creator = storage.get_user_by_id(match.manager1_id)
    
    renderer = MatchRenderer()
    
    text = f"✅ <b>Соперник найден!</b>\n"
    text += f"Вы играете против: <b>{joining_user.username}</b>\n\n"
    text += renderer.render_match_status(match, match.manager1_id)
    text += "\n\n" + renderer.render_turn_info_simultaneous(match, match.manager1_id)
    
    try:
        await bot.send_message(
            chat_id=creator_telegram_id,
            text=text,
            reply_markup=Keyboards.game_actions_simultaneous(
                bets_count=0,
                required_bets=1,
                is_confirmed=False,
                both_ready=False
            )
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to notify creator: {e}")


@router.callback_query(F.data == "cancel_search", MatchStates.waiting_opponent)
async def cb_cancel_search(callback: CallbackQuery, state: FSMContext):
    """Отменить поиск соперника"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    if match_id:
        storage = get_storage()
        storage.remove_waiting_match(UUID(match_id))
        
        match = storage.get_match(UUID(match_id))
        if match:
            match.status = MatchStatus.CANCELLED
            storage.save_match(match)
    
    await state.clear()
    await callback.message.edit_text(
        "❌ Поиск отменён",
        reply_markup=Keyboards.main_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "play_bot")
async def cb_play_bot(callback: CallbackQuery, state: FSMContext):
    """Начать игру против бота"""
    storage = get_storage()
    
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    # Проверяем активный матч
    active = storage.get_user_active_match(user.id)
    if active:
        await callback.answer("У вас уже есть активный матч!", show_alert=True)
        return
    
    # Создаём матч против бота
    match = storage.engine.create_match(user.id, MatchType.VS_BOT, platform="telegram")
    
    # Создаём команды (16 игроков каждая) и сразу присоединяем
    from src.core.engine.game_engine import BOT_USER_ID
    import copy
    
    # Команда пользователя — КОПИРУЕМ и сбрасываем статистику
    user_team_template = storage.get_user_team(user.id)
    if not user_team_template:
        user_team_template = storage._create_default_team(user.id, user.username)
    
    user_team = copy.deepcopy(user_team_template)
    # Сбрасываем статистику всех игроков
    for player in user_team.players:
        player.stats.saves = 0
        player.stats.passes = 0
        player.stats.goals = 0
        player.is_available = True
    
    # Команда бота (всегда новая)
    bot_team = _create_bot_team()
    
    # Устанавливаем команды БЕЗ формации (None = динамическая)
    match = storage.engine.set_team_without_formation(match, user.id, user_team)
    match = storage.engine.set_team_without_formation(match, BOT_USER_ID, bot_team)
    
    storage.save_match(match)
    
    await state.update_data(match_id=str(match.id))
    await state.set_state(MatchStates.in_game)
    
    renderer = MatchRenderer()
    text = renderer.render_match_status(match, user.id)
    text += "\n\n" + renderer.render_turn_info_simultaneous(match, user.id)
    
    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.game_actions_simultaneous(
            bets_count=0,
            required_bets=1,  # Первый ход — вратарь, 1 ставка
            is_confirmed=False,
            both_ready=False
        )
    )
    await callback.answer("🎮 Матч начался!")


@router.callback_query(F.data == "cancel_match")
async def cb_cancel_match(callback: CallbackQuery, state: FSMContext):
    """Отменить матч"""
    data = await state.get_data()
    match_id = data.get("match_id")
    
    if match_id:
        storage = get_storage()
        user = storage.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.full_name or "Игрок"
        )
        
        match = storage.get_match(UUID(match_id))
        if match:
            try:
                match = storage.engine.cancel_match(match, user.id)
                storage.save_match(match)
            except ValueError:
                pass
    
    await state.clear()
    await callback.message.edit_text(
        "❌ Матч отменён",
        reply_markup=Keyboards.main_menu()
    )
    await callback.answer()


def _create_bot_team() -> Team:
    """Создать команду бота"""
    from src.core.engine.game_engine import BOT_USER_ID
    
    players = []
    number = 1
    
    # 1 вратарь
    players.append(Player(name="Бот-Вратарь", position=Position.GOALKEEPER, number=number))
    number += 1
    
    # 5 защитников
    for i in range(5):
        players.append(Player(name=f"Бот-Защитник {i+1}", position=Position.DEFENDER, number=number))
        number += 1
    
    # 6 полузащитников
    for i in range(6):
        players.append(Player(name=f"Бот-Полузащитник {i+1}", position=Position.MIDFIELDER, number=number))
        number += 1
    
    # 4 нападающих
    for i in range(4):
        players.append(Player(name=f"Бот-Нападающий {i+1}", position=Position.FORWARD, number=number))
        number += 1
    
    return Team(manager_id=BOT_USER_ID, name="Команда Бота", players=players)
