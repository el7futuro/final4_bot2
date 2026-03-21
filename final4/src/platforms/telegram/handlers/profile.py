# src/platforms/telegram/handlers/profile.py
"""Хендлеры профиля пользователя"""

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from ..keyboards.inline import Keyboards
from ..dependencies import get_user_service

router = Router(name="profile")


@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery, state: FSMContext):
    """Показать профиль"""
    user_service = await get_user_service()
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    win_rate = user.get_win_rate()
    
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"<b>{user.username}</b>\n"
        f"📊 Рейтинг: <b>{user.rating}</b>\n\n"
        
        f"<b>📈 Статистика:</b>\n"
        f"• Матчей: {user.stats.matches_played}\n"
        f"• Побед: {user.stats.matches_won}\n"
        f"• Поражений: {user.stats.matches_lost}\n"
        f"• Винрейт: {win_rate:.1f}%\n\n"
        
        f"⚽ Голов забито: {user.stats.goals_scored}\n"
        f"🥅 Голов пропущено: {user.stats.goals_conceded}\n"
        f"🔥 Серия побед: {user.stats.win_streak}\n"
        f"🏆 Лучшая серия: {user.stats.best_win_streak}\n\n"
        
        f"💎 План: {user.plan.value.upper()}\n"
        f"🎮 Матчей сегодня: {user.daily_limits.matches_today}"
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: CallbackQuery):
    """Показать таблицу лидеров"""
    user_service = await get_user_service()
    leaders = await user_service.get_leaderboard(limit=10)
    
    lines = ["🏆 <b>Таблица лидеров</b>\n"]
    
    medals = ["🥇", "🥈", "🥉"]
    
    for i, user in enumerate(leaders, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        win_rate = user.get_win_rate()
        lines.append(
            f"{medal} <b>{user.username}</b> — {user.rating} "
            f"({user.stats.matches_won}W/{user.stats.matches_lost}L, {win_rate:.0f}%)"
        )
    
    if not leaders:
        lines.append("Пока нет игроков")
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text("\n".join(lines), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "team_menu")
async def cb_team_menu(callback: CallbackQuery):
    """Меню команды"""
    user_service = await get_user_service()
    user = await user_service.get_or_create_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.full_name
    )
    
    team = await user_service.get_user_team(user.id)
    
    if not team:
        await callback.message.edit_text(
            "❌ Команда не найдена. Используйте /start для создания.",
            reply_markup=Keyboards.main_menu()
        )
        await callback.answer()
        return
    
    # Группируем игроков по позициям
    from src.core.models.player import Position
    
    lines = [f"⚽ <b>Команда: {team.name}</b>\n"]
    
    positions = [
        (Position.GOALKEEPER, "🧤 Вратари"),
        (Position.DEFENDER, "🛡 Защитники"),
        (Position.MIDFIELDER, "🎯 Полузащитники"),
        (Position.FORWARD, "⚡ Нападающие"),
    ]
    
    for pos, title in positions:
        players = team.get_players_by_position(pos)
        if players:
            lines.append(f"\n<b>{title}:</b>")
            for p in players:
                status = "✅" if p.is_available else "❌"
                lines.append(f"  {status} #{p.number} {p.name}")
    
    lines.append(f"\n📊 Всего игроков: {len(team.players)}/16")
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text("\n".join(lines), reply_markup=kb)
    await callback.answer()
