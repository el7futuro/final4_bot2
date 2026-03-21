# src/platforms/telegram/handlers/start.py
"""Хендлеры команды /start и главного меню"""

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from ..keyboards.inline import Keyboards
from ..dependencies import get_user_service

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start"""
    # Очищаем состояние
    await state.clear()
    
    # Получаем или создаём пользователя
    user_service = await get_user_service()
    user = await user_service.get_or_create_telegram_user(
        telegram_id=message.from_user.id,
        username=message.from_user.full_name or message.from_user.username or "Игрок"
    )
    
    text = (
        f"⚽ <b>Final 4</b>\n\n"
        f"Привет, <b>{user.username}</b>!\n\n"
        f"Добро пожаловать в пошаговую футбольную стратегию. "
        f"Управляй командой, делай ставки на игроков и побеждай!\n\n"
        f"📊 Твой рейтинг: <b>{user.rating}</b>\n"
        f"🏆 Побед: {user.stats.matches_won} из {user.stats.matches_played}"
    )
    
    await message.answer(text, reply_markup=Keyboards.main_menu())


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    """Команда /menu"""
    await state.clear()
    await message.answer(
        "⚽ <b>Главное меню</b>",
        reply_markup=Keyboards.main_menu()
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await callback.message.edit_text(
        "⚽ <b>Главное меню</b>",
        reply_markup=Keyboards.main_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "play_menu")
async def cb_play_menu(callback: CallbackQuery):
    """Меню игры"""
    await callback.message.edit_text(
        "⚽ <b>Выберите режим игры:</b>\n\n"
        "🎲 <b>Случайный соперник</b> — матч с реальным игроком\n"
        "🤖 <b>Против бота</b> — тренировочный матч",
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
        
        "<b>🎲 Ход игры:</b>\n"
        "1. Выбери игрока и сделай на него ставку\n"
        "2. Брось кубик\n"
        "3. Если ставка выиграла — игрок получает действие\n"
        "4. Возьми карточку Свисток (если выиграл)\n\n"
        
        "<b>📊 Типы ставок:</b>\n"
        "• <b>Чёт/Нечёт</b> → Отбития\n"
        "• <b>Больше/Меньше</b> → Передачи\n"
        "• <b>Точное число</b> → Гол\n\n"
        
        "<b>⚽ Подсчёт голов:</b>\n"
        "• Передачи пробивают отбития соперника\n"
        "• 1 гол = 2 отбития\n"
        "• Оставшиеся голы засчитываются"
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()
