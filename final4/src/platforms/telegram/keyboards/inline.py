# src/platforms/telegram/keyboards/inline.py
"""Inline клавиатуры"""

from uuid import UUID
from typing import List, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.core.models.match import Match, MatchStatus
from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.models.bet import BetType


class Keyboards:
    """Генератор клавиатур"""
    
    # ====== ГЛАВНОЕ МЕНЮ ======
    
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Главное меню"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⚽ Играть", callback_data="play_menu")
        )
        builder.row(
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="🏆 Рейтинг", callback_data="leaderboard")
        )
        builder.row(
            InlineKeyboardButton(text="❓ Правила", callback_data="rules")
        )
        return builder.as_markup()
    
    @staticmethod
    def play_menu() -> InlineKeyboardMarkup:
        """Меню выбора типа игры"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🎲 Случайный соперник", callback_data="play_random")
        )
        builder.row(
            InlineKeyboardButton(text="🤖 Против бота", callback_data="play_bot")
        )
        builder.row(
            InlineKeyboardButton(text="« Назад", callback_data="main_menu")
        )
        return builder.as_markup()
    
    @staticmethod
    def cancel_search() -> InlineKeyboardMarkup:
        """Клавиатура отмены поиска соперника"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="❌ Отменить поиск", callback_data="cancel_search")
        )
        return builder.as_markup()
    
    # ====== ФОРМАЦИИ ======
    
    @staticmethod
    def formation_select() -> InlineKeyboardMarkup:
        """Выбор формации"""
        builder = InlineKeyboardBuilder()
        formations = [
            (Formation.F_4_4_2, "4-4-2"),
            (Formation.F_4_3_3, "4-3-3"),
            (Formation.F_3_5_2, "3-5-2"),
            (Formation.F_3_4_3, "3-4-3"),
            (Formation.F_5_3_2, "5-3-2"),
            (Formation.F_5_2_3, "5-2-3"),
            (Formation.F_3_3_4, "3-3-4"),
        ]
        
        for i in range(0, len(formations), 2):
            row = []
            for f, name in formations[i:i+2]:
                row.append(InlineKeyboardButton(
                    text=name,
                    callback_data=f"formation:{f.value}"
                ))
            builder.row(*row)
        
        builder.row(
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_match")
        )
        return builder.as_markup()
    
    # ====== ИГРОКИ ======
    
    @staticmethod
    def player_select(
        players: List[Player],
        selected_ids: List[UUID],
        position_filter: Optional[Position] = None
    ) -> InlineKeyboardMarkup:
        """Выбор игроков для состава"""
        builder = InlineKeyboardBuilder()
        
        filtered = players
        if position_filter:
            filtered = [p for p in players if p.position == position_filter]
        
        for player in filtered:
            is_selected = player.id in selected_ids
            emoji = "✅" if is_selected else "⬜"
            text = f"{emoji} {player.number}. {player.name}"
            builder.row(InlineKeyboardButton(
                text=text,
                callback_data=f"select_player:{player.id}"
            ))
        
        # Фильтры по позициям
        builder.row(
            InlineKeyboardButton(text="🧤 Вр", callback_data="filter:goalkeeper"),
            InlineKeyboardButton(text="🛡 Защ", callback_data="filter:defender"),
            InlineKeyboardButton(text="🎯 Пз", callback_data="filter:midfielder"),
            InlineKeyboardButton(text="⚡ Нап", callback_data="filter:forward"),
        )
        
        builder.row(
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_lineup"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_match")
        )
        
        return builder.as_markup()
    
    # ====== ИГРОВОЙ ПРОЦЕСС ======
    
    @staticmethod
    def game_actions(
        can_bet: bool = True,
        can_roll: bool = False,
        can_draw_card: bool = False,
        can_end_turn: bool = False
    ) -> InlineKeyboardMarkup:
        """Действия в игре (legacy)"""
        builder = InlineKeyboardBuilder()
        
        if can_bet:
            builder.row(InlineKeyboardButton(
                text="🎯 Сделать ставку",
                callback_data="make_bet"
            ))
        
        if can_roll:
            builder.row(InlineKeyboardButton(
                text="🎲 Бросить кубик",
                callback_data="roll_dice"
            ))
        
        if can_draw_card:
            builder.row(InlineKeyboardButton(
                text="🃏 Взять карточку",
                callback_data="draw_card"
            ))
        
        if can_end_turn:
            builder.row(InlineKeyboardButton(
                text="➡️ Завершить ход",
                callback_data="end_turn"
            ))
        
        builder.row(InlineKeyboardButton(
            text="📊 Статистика",
            callback_data="match_stats"
        ))
        
        return builder.as_markup()
    
    @staticmethod
    def game_actions_simultaneous(
        bets_count: int = 0,
        required_bets: int = 2,
        is_confirmed: bool = False,
        both_ready: bool = False,
        dice_rolled: bool = False
    ) -> InlineKeyboardMarkup:
        """Действия в игре (одновременные ставки)"""
        builder = InlineKeyboardBuilder()
        
        if not dice_rolled:
            if not is_confirmed:
                # Ещё не подтвердил ставки
                if bets_count < required_bets:
                    builder.row(InlineKeyboardButton(
                        text=f"🎯 Сделать ставку ({bets_count}/{required_bets})",
                        callback_data="make_bet"
                    ))
                
                if bets_count > 0:
                    # Есть ставки — можно отменить
                    builder.row(InlineKeyboardButton(
                        text="🔄 Отменить ставки",
                        callback_data="cancel_bets"
                    ))
                
                if bets_count >= required_bets:
                    builder.row(InlineKeyboardButton(
                        text="✅ Подтвердить ставки",
                        callback_data="confirm_bets"
                    ))
            else:
                # Ставки подтверждены, ждём соперника
                builder.row(InlineKeyboardButton(
                    text="⏳ Ожидание соперника...",
                    callback_data="waiting"
                ))
        else:
            # После броска кубика
            builder.row(InlineKeyboardButton(
                text="➡️ Завершить ход",
                callback_data="end_turn"
            ))
        
        builder.row(InlineKeyboardButton(
            text="📊 Статистика",
            callback_data="match_stats"
        ))
        
        return builder.as_markup()
    
    @staticmethod
    def game_actions_after_roll() -> InlineKeyboardMarkup:
        """Действия после броска кубика"""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="➡️ Следующий ход",
            callback_data="end_turn"
        ))
        builder.row(InlineKeyboardButton(
            text="📊 Статистика",
            callback_data="match_stats"
        ))
        return builder.as_markup()
    
    @staticmethod
    def roll_dice_button() -> InlineKeyboardMarkup:
        """Кнопка броска кубика (после показа ставок)"""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="🎲 Бросить кубик!",
            callback_data="roll_dice"
        ))
        return builder.as_markup()
    
    @staticmethod
    def penalty_choice() -> InlineKeyboardMarkup:
        """Выбор для пенальти: Больше или Меньше"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⬇️ Меньше (1-3)", callback_data="penalty_choice:low"),
            InlineKeyboardButton(text="⬆️ Больше (4-6)", callback_data="penalty_choice:high")
        )
        return builder.as_markup()
    
    @staticmethod
    def penalty_roll_button() -> InlineKeyboardMarkup:
        """Кнопка броска кубика для пенальти"""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="🎲 Бросить кубик!",
            callback_data="penalty_roll"
        ))
        return builder.as_markup()
    
    @staticmethod
    def bet_player_select(players: List[Player]) -> InlineKeyboardMarkup:
        """Выбор игрока для ставки"""
        builder = InlineKeyboardBuilder()
        
        for player in players:
            pos_emoji = {
                Position.GOALKEEPER: "🧤",
                Position.DEFENDER: "🛡",
                Position.MIDFIELDER: "🎯",
                Position.FORWARD: "⚡"
            }.get(player.position, "")
            
            text = f"{pos_emoji} {player.number}. {player.name}"
            builder.row(InlineKeyboardButton(
                text=text,
                callback_data=f"bet_player:{player.id}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="« Назад",
            callback_data="back_to_game"
        ))
        
        return builder.as_markup()
    
    @staticmethod
    def bet_type_select(available_types: List[BetType]) -> InlineKeyboardMarkup:
        """Выбор типа ставки"""
        builder = InlineKeyboardBuilder()
        
        type_labels = {
            BetType.EVEN_ODD: "🔢 Чёт/Нечёт (отбития)",
            BetType.HIGH_LOW: "📊 Больше/Меньше (передачи)",
            BetType.EXACT_NUMBER: "🎯 Точное число (гол)",
        }
        
        for bt in available_types:
            builder.row(InlineKeyboardButton(
                text=type_labels.get(bt, bt.value),
                callback_data=f"bet_type:{bt.value}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="« Назад",
            callback_data="make_bet"
        ))
        
        return builder.as_markup()
    
    @staticmethod
    def even_odd_select() -> InlineKeyboardMarkup:
        """Выбор чёт/нечёт"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="Чётное (2,4,6)", callback_data="bet_value:even"),
            InlineKeyboardButton(text="Нечётное (1,3,5)", callback_data="bet_value:odd")
        )
        builder.row(InlineKeyboardButton(text="« Назад", callback_data="back_bet_type"))
        return builder.as_markup()
    
    @staticmethod
    def high_low_select() -> InlineKeyboardMarkup:
        """Выбор больше/меньше"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="Меньше (1-3)", callback_data="bet_value:low"),
            InlineKeyboardButton(text="Больше (4-6)", callback_data="bet_value:high")
        )
        builder.row(InlineKeyboardButton(text="« Назад", callback_data="back_bet_type"))
        return builder.as_markup()
    
    @staticmethod
    def exact_number_select() -> InlineKeyboardMarkup:
        """Выбор точного числа"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="1", callback_data="bet_value:1"),
            InlineKeyboardButton(text="2", callback_data="bet_value:2"),
            InlineKeyboardButton(text="3", callback_data="bet_value:3"),
        )
        builder.row(
            InlineKeyboardButton(text="4", callback_data="bet_value:4"),
            InlineKeyboardButton(text="5", callback_data="bet_value:5"),
            InlineKeyboardButton(text="6", callback_data="bet_value:6"),
        )
        builder.row(InlineKeyboardButton(text="« Назад", callback_data="back_bet_type"))
        return builder.as_markup()
    
    @staticmethod
    def card_target_select(players: List[Player]) -> InlineKeyboardMarkup:
        """Выбор цели для карточки"""
        builder = InlineKeyboardBuilder()
        
        for player in players:
            text = f"{player.number}. {player.name}"
            # Показываем текущие действия
            actions = []
            if player.stats.saves > 0:
                actions.append(f"🛡{player.stats.saves}")
            if player.stats.passes > 0:
                actions.append(f"🎯{player.stats.passes}")
            if player.stats.goals > 0:
                actions.append(f"⚽{player.stats.goals}")
            if actions:
                text += f" ({' '.join(actions)})"
            
            builder.row(InlineKeyboardButton(
                text=text,
                callback_data=f"card_target:{player.id}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="❌ Не применять",
            callback_data="skip_card"
        ))
        
        return builder.as_markup()
    
    # ====== ПОДТВЕРЖДЕНИЯ ======
    
    @staticmethod
    def confirm_cancel() -> InlineKeyboardMarkup:
        """Подтверждение отмены"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Да, отменить", callback_data="confirm_cancel"),
            InlineKeyboardButton(text="❌ Нет", callback_data="back_to_game")
        )
        return builder.as_markup()
    
    @staticmethod
    def waiting_for_opponent() -> InlineKeyboardMarkup:
        """Ожидание соперника"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="❌ Отменить поиск", callback_data="cancel_match")
        )
        return builder.as_markup()
