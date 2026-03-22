# src/platforms/telegram/handlers/match.py
"""Хендлеры создания и управления матчами"""

from uuid import UUID
import copy

from aiogram import Router, F
from aiogram.types import CallbackQuery
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
    """Поиск случайного соперника (пока недоступно)"""
    await callback.answer("🔜 Режим случайного соперника в разработке!", show_alert=True)


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
    
    # Команда пользователя
    user_team = storage.get_user_team(user.id)
    if not user_team:
        user_team = storage._create_default_team(user.id, user.username)
    
    # Команда бота
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
