# src/platforms/telegram/handlers/match.py
"""Хендлеры создания и управления матчами"""

from uuid import UUID
from typing import List
import copy

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from src.core.models.match import MatchType, MatchStatus
from src.core.models.team import Team, Formation, FORMATION_STRUCTURE
from src.core.models.player import Position

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
    storage.save_match(match)
    
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
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    team = storage.get_user_team(user.id)
    if not team:
        await callback.answer("Команда не найдена!", show_alert=True)
        return
    
    await state.update_data(
        formation=formation_value,
        selected_players=[]
    )
    await state.set_state(MatchStates.selecting_lineup)
    
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
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    team = storage.get_user_team(user.id)
    
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
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    team = storage.get_user_team(user.id)
    
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
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    
    match = storage.get_match(UUID(match_id))
    if not match:
        await callback.answer("Матч не найден!", show_alert=True)
        return
    
    formation = Formation(formation_value)
    player_ids = [UUID(s) for s in selected]
    
    # Копируем команду пользователя для матча
    user_team = storage.get_user_team(user.id)
    match_team = Team(
        manager_id=user.id,
        name=user_team.name,
        players=copy.deepcopy(user_team.players)
    )
    
    try:
        match = storage.engine.set_team_lineup(
            match, user.id, match_team, formation, player_ids
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    
    # Для бота — автоматически создаём команду и состав
    if match.match_type == MatchType.VS_BOT and match.team2 is None:
        from src.core.engine.game_engine import BOT_USER_ID
        
        # Создаём команду бота
        bot_team = _create_bot_team()
        bot_lineup = _select_bot_lineup(bot_team, formation)
        
        match = storage.engine.set_team_lineup(
            match, BOT_USER_ID, bot_team, formation, bot_lineup
        )
    
    storage.save_match(match)
    
    # Проверяем статус матча
    if match.status == MatchStatus.IN_PROGRESS:
        await state.set_state(MatchStates.in_game)
        
        renderer = MatchRenderer()
        text = renderer.render_match_status(match, user.id)
        text += "\n\n" + renderer.render_turn_info_simultaneous(match, user.id)
        
        await callback.message.edit_text(
            text,
            reply_markup=Keyboards.game_actions_simultaneous(
                bets_count=0,
                required_bets=1 if match.current_turn.turn_number == 1 else 2,
                is_confirmed=False,
                both_ready=False
            )
        )
    
    await callback.answer()


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
    from src.core.models.player import Player, Position
    
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


def _select_bot_lineup(team: Team, formation: Formation) -> List[UUID]:
    """Автоматически выбрать состав для бота"""
    structure = FORMATION_STRUCTURE[formation]
    selected = []
    
    for pos_str, count in structure.items():
        pos = Position(pos_str)
        pos_players = team.get_players_by_position(pos)
        selected.extend([p.id for p in pos_players[:count]])
    
    return selected
