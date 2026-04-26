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
    
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"<b>{user.username}</b>\n\n"
        f"📊 Рейтинг: {user.rating}\n"
        f"⚽ Матчей: {user.matches_played}\n"
        f"🏆 Побед: {user.matches_won}\n"
    )
    
    if team:
        text += f"\n⚽ Команда: {team.name}"
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


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
