# src/platforms/telegram/handlers/start.py
"""Хендлеры команды /start и главного меню"""

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from ..keyboards.inline import Keyboards
from ..storage import get_storage

router = Router(name="start")


def _has_active_match(storage, user_id) -> bool:
    """Есть ли у пользователя активный матч (для кнопки 'Продолжить матч')."""
    try:
        return storage.get_user_active_match(user_id) is not None
    except Exception:
        return False


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start"""
    await state.clear()
    
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.full_name or message.from_user.username or "Игрок"
    )
    
    text = (
        f"⚽ <b>Final 4</b>\n\n"
        f"Привет, <b>{user.username}</b>!\n\n"
        f"Добро пожаловать в пошаговую футбольную стратегию. "
        f"Управляй командой, делай ставки на игроков и побеждай!\n\n"
        f"📊 Твой рейтинг: <b>{user.rating}</b>\n"
        f"🏆 Побед: {user.matches_won} из {user.matches_played}"
    )
    
    await message.answer(text, reply_markup=Keyboards.main_menu(
        has_active_match=_has_active_match(storage, user.id)
    ))


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    """Команда /menu"""
    await state.clear()
    storage = get_storage()
    user = storage.get_user_by_telegram_id(message.from_user.id)
    has_active = _has_active_match(storage, user.id) if user else False
    await message.answer(
        "⚽ <b>Главное меню</b>",
        reply_markup=Keyboards.main_menu(has_active_match=has_active)
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    storage = get_storage()
    user = storage.get_user_by_telegram_id(callback.from_user.id)
    has_active = _has_active_match(storage, user.id) if user else False
    await callback.message.edit_text(
        "⚽ <b>Главное меню</b>",
        reply_markup=Keyboards.main_menu(has_active_match=has_active)
    )
    await callback.answer()


@router.callback_query(F.data == "play_menu")
async def cb_play_menu(callback: CallbackQuery):
    """Меню игры"""
    await callback.message.edit_text(
        "⚽ <b>Выберите режим игры:</b>\n\n"
        "🤖 <b>Против бота</b> — тренировочный матч\n\n"
        "<i>🎲 Случайный соперник — скоро!</i>",
        reply_markup=Keyboards.play_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "rules")
async def cb_rules(callback: CallbackQuery):
    """Правила игры"""
    text = (
        "📖 <b>Правила Final 4</b>\n\n"
        
        "<b>🎯 Цель игры:</b>\n"
        "Забить больше голов, чем соперник.\n\n"
        
        "<b>👥 Состав:</b>\n"
        "16 игроков: 1 ВР + 5 ЗЩ + 6 ПЗ + 4 НП\n\n"
        
        "<b>⏱ Матч:</b>\n"
        "• Основное время: 11 ходов\n"
        "• Дополнительное: 5 ходов (при ничьей)\n"
        "• Пенальти (если всё ещё ничья)\n\n"
        
        "<b>🎲 Ход игры:</b>\n"
        "1. Выбери игрока\n"
        "2. Сделай 2 ставки разных типов\n"
        "3. Бросок кубика для обоих\n"
        "4. Победившие ставки = действия игроку\n"
        "5. Карточка Свисток (при выигрыше)\n\n"
        
        "<b>📊 Типы ставок:</b>\n"
        "• <b>Чёт/Нечёт</b> → Отбития\n"
        "• <b>Больше/Меньше</b> → Передачи\n"
        "• <b>Точное число</b> → Гол\n\n"
        
        "<b>⚽ Подсчёт голов:</b>\n"
        "• Передачи пробивают отбития (1:1)\n"
        "• Отбития гасят голы (2:1)\n"
        "• Лишние передачи НЕ = голы!"
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    """Профиль пользователя"""
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    team = storage.get_user_team(user.id)

    win_pct = (
        round(user.matches_won * 100 / user.matches_played)
        if user.matches_played > 0 else 0
    )

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"<b>{user.username}</b>\n\n"
        f"📊 Рейтинг: <b>{user.rating}</b> (ELO)\n"
        f"⚽ Матчей: {user.matches_played}\n"
        f"🏆 Побед: {user.matches_won} ({win_pct}%)\n"
    )

    if team:
        text += f"\n⚽ Команда: {team.name}\n"

    # Последние 5 завершённых матчей
    last_matches = storage.get_user_finished_matches(user.id, limit=5)
    if last_matches:
        text += "\n📜 <b>Последние 5 матчей:</b>\n"
        for m in last_matches:
            text += _format_match_summary_line(storage, m, user.id) + "\n"
    else:
        text += "\n<i>Завершённых матчей пока нет</i>\n"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="main_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


def _format_match_summary_line(storage, match, viewer_id) -> str:
    """Одна строка сводки матча для профиля.

    Формат: «✅ 25.04 vs Алексей — 3:1 (по пенальти)»
    """
    from src.core.engine.game_engine import BOT_USER_ID
    from src.core.models.match import MatchPhase

    is_m1 = match.manager1_id == viewer_id
    opp_id = match.manager2_id if is_m1 else match.manager1_id

    # Имя соперника
    if opp_id == BOT_USER_ID:
        opp_name = "Бот"
    else:
        opp_user = storage.get_user_by_id(opp_id) if opp_id else None
        opp_name = opp_user.username if opp_user else "?"

    # Результат
    if not match.result or not match.result.winner_id:
        emoji = "⚪"
    elif match.result.winner_id == viewer_id:
        emoji = "✅"
    else:
        emoji = "❌"

    # Счёт «свой:соперника»
    s1 = match.score.manager1_goals
    s2 = match.score.manager2_goals
    you = s1 if is_m1 else s2
    them = s2 if is_m1 else s1

    # Дата
    date_src = match.finished_at or match.created_at
    date_str = date_src.strftime("%d.%m") if date_src else "—"

    # Признак завершения через ET / пенальти
    suffix = ""
    if match.result and match.result.decided_by == MatchPhase.PENALTIES:
        vp = match.penalty_score_m1 if is_m1 else match.penalty_score_m2
        op = match.penalty_score_m2 if is_m1 else match.penalty_score_m1
        suffix = f" (пен. {vp}:{op})"
    elif match.result and match.result.decided_by == MatchPhase.EXTRA_TIME:
        suffix = " (ОТ)"

    return f"{emoji} {date_str} vs {opp_name} — {you}:{them}{suffix}"


@router.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: CallbackQuery):
    """Рейтинг игроков"""
    storage = get_storage()
    
    # Сортируем по рейтингу
    users_list = sorted(storage.users.values(), key=lambda u: u.rating, reverse=True)[:10]
    
    lines = ["🏆 <b>Рейтинг игроков</b>\n"]
    
    for i, user in enumerate(users_list, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        lines.append(f"{medal} {user.username} — {user.rating}")
    
    if not users_list:
        lines.append("\n<i>Пока нет игроков</i>")
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text("\n".join(lines), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "team_menu")
async def cb_team_menu(callback: CallbackQuery):
    """Меню команды"""
    storage = get_storage()
    user = storage.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name or "Игрок"
    )
    team = storage.get_user_team(user.id)
    
    if not team:
        await callback.answer("Команда не найдена!", show_alert=True)
        return
    
    lines = [f"⚽ <b>Команда: {team.name}</b>\n"]
    
    # Группируем по позициям
    positions = {
        "🧤 Вратари": [p for p in team.players if p.position.value == "goalkeeper"],
        "🛡 Защитники": [p for p in team.players if p.position.value == "defender"],
        "🎯 Полузащитники": [p for p in team.players if p.position.value == "midfielder"],
        "⚡ Нападающие": [p for p in team.players if p.position.value == "forward"],
    }
    
    for pos_name, players in positions.items():
        lines.append(f"\n{pos_name}:")
        for p in players:
            lines.append(f"  {p.number}. {p.name}")
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text("\n".join(lines), reply_markup=kb)
    await callback.answer()
