# Модуль: Telegram Adapter

## Обзор

Адаптер для платформы Telegram. Использует aiogram 3.x для асинхронной обработки.

---

## 1. Структура модуля

```
src/platforms/telegram/
├── __init__.py
├── bot.py                  # Инициализация бота
├── handlers/
│   ├── __init__.py
│   ├── start.py            # /start, /help
│   ├── match.py            # Создание/поиск матча
│   ├── bet.py              # Размещение ставок
│   ├── game.py             # Игровой процесс
│   └── profile.py          # Профиль, статистика
├── keyboards/
│   ├── __init__.py
│   └── inline.py           # Inline клавиатуры
├── callbacks/
│   ├── __init__.py
│   └── callback_data.py    # Callback data factories
├── renderers/
│   ├── __init__.py
│   └── match_renderer.py   # Рендеринг сообщений
├── middlewares/
│   ├── __init__.py
│   ├── auth.py             # Авторизация
│   └── rate_limit.py       # Rate limiting
└── states/
    ├── __init__.py
    └── match_states.py     # FSM states
```

---

## 2. Bot Initialization

```python
# src/platforms/telegram/bot.py

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from src.infrastructure.db.database import Database
from src.infrastructure.cache.redis_client import RedisClient
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.repositories.match_repository import MatchRepository
from src.application.services.match_service import MatchService
from src.application.services.user_service import UserService

from .handlers import start, match, bet, game, profile
from .middlewares.auth import AuthMiddleware
from .middlewares.rate_limit import RateLimitMiddleware

class TelegramBot:
    """Telegram бот Final 4"""
    
    def __init__(
        self,
        token: str,
        database: Database,
        redis: RedisClient
    ):
        self.bot = Bot(token=token, parse_mode=ParseMode.HTML)
        self.storage = RedisStorage.from_url(redis.redis.connection_pool.connection_kwargs['url'])
        self.dp = Dispatcher(storage=self.storage)
        
        self.database = database
        self.redis = redis
        
        # Services
        self.user_service = UserService()
        self.match_service = MatchService()
        
        self._setup_middlewares()
        self._setup_routers()
    
    def _setup_middlewares(self) -> None:
        """Настройка middleware"""
        self.dp.message.middleware(AuthMiddleware(self.database))
        self.dp.callback_query.middleware(AuthMiddleware(self.database))
        self.dp.message.middleware(RateLimitMiddleware(self.redis))
    
    def _setup_routers(self) -> None:
        """Настройка роутеров"""
        router = Router()
        
        # Include all handlers
        router.include_router(start.router)
        router.include_router(match.router)
        router.include_router(bet.router)
        router.include_router(game.router)
        router.include_router(profile.router)
        
        self.dp.include_router(router)
    
    async def start(self) -> None:
        """Запуск бота"""
        await self.dp.start_polling(
            self.bot,
            database=self.database,
            redis=self.redis,
            user_service=self.user_service,
            match_service=self.match_service
        )
    
    async def stop(self) -> None:
        """Остановка бота"""
        await self.dp.stop_polling()
        await self.bot.session.close()
```

---

## 3. Callback Data

```python
# src/platforms/telegram/callbacks/callback_data.py

from aiogram.filters.callback_data import CallbackData
from uuid import UUID
from typing import Optional

class MenuCallback(CallbackData, prefix="menu"):
    """Главное меню"""
    action: str  # play, profile, leaderboard, settings

class MatchCallback(CallbackData, prefix="match"):
    """Действия с матчем"""
    action: str  # create, join, cancel, vs_bot
    match_id: Optional[str] = None

class FormationCallback(CallbackData, prefix="formation"):
    """Выбор формации"""
    formation: str  # 1-5-3-2, 1-4-4-2, etc.

class LineupCallback(CallbackData, prefix="lineup"):
    """Выбор состава"""
    action: str  # select, confirm, back
    player_id: Optional[str] = None
    position: Optional[str] = None

class BetCallback(CallbackData, prefix="bet"):
    """Ставки"""
    action: str  # place, confirm
    bet_type: Optional[str] = None  # even_odd, high_low, exact_number
    value: Optional[str] = None  # even, odd, low, high, 1-6
    player_id: Optional[str] = None

class GameCallback(CallbackData, prefix="game"):
    """Игровой процесс"""
    action: str  # roll_dice, draw_card, apply_card, end_turn
    target_player_id: Optional[str] = None

class CardCallback(CallbackData, prefix="card"):
    """Применение карточки"""
    action: str  # apply, select_target
    card_id: Optional[str] = None
    target_player_id: Optional[str] = None

class ConfirmCallback(CallbackData, prefix="confirm"):
    """Подтверждение действия"""
    action: str  # yes, no
    context: str  # cancel_match, surrender, etc.
```

---

## 4. Keyboards

```python
# src/platforms/telegram/keyboards/inline.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Optional
from uuid import UUID

from src.core.models.team import Formation
from src.core.models.player import Player, Position
from src.core.models.bet import BetType
from src.core.models.whistle_card import WhistleCard, CardType

from ..callbacks.callback_data import (
    MenuCallback, MatchCallback, FormationCallback, LineupCallback,
    BetCallback, GameCallback, CardCallback, ConfirmCallback
)

class Keyboards:
    """Фабрика клавиатур"""
    
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Главное меню"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="⚽ Играть",
                callback_data=MenuCallback(action="play").pack()
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="👤 Профиль",
                callback_data=MenuCallback(action="profile").pack()
            ),
            InlineKeyboardButton(
                text="🏆 Рейтинг",
                callback_data=MenuCallback(action="leaderboard").pack()
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="⚙️ Настройки",
                callback_data=MenuCallback(action="settings").pack()
            )
        )
        return builder.as_markup()
    
    @staticmethod
    def play_menu() -> InlineKeyboardMarkup:
        """Меню выбора типа игры"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="🎲 Случайный соперник",
                callback_data=MatchCallback(action="create").pack()
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🤖 Против бота",
                callback_data=MatchCallback(action="vs_bot").pack()
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data=MenuCallback(action="back").pack()
            )
        )
        return builder.as_markup()
    
    @staticmethod
    def formation_select() -> InlineKeyboardMarkup:
        """Выбор формации"""
        builder = InlineKeyboardBuilder()
        
        formations = [
            ("1-5-3-2", "5 защ, 3 полуз, 2 форв"),
            ("1-5-2-3", "5 защ, 2 полуз, 3 форв"),
            ("1-4-4-2", "4 защ, 4 полуз, 2 форв"),
            ("1-4-3-3", "4 защ, 3 полуз, 3 форв"),
            ("1-3-5-2", "3 защ, 5 полуз, 2 форв"),
            ("1-3-4-3", "3 защ, 4 полуз, 3 форв"),
            ("1-3-3-4", "3 защ, 3 полуз, 4 форв"),
        ]
        
        for formation, desc in formations:
            builder.row(
                InlineKeyboardButton(
                    text=f"{formation} ({desc})",
                    callback_data=FormationCallback(formation=formation).pack()
                )
            )
        
        return builder.as_markup()
    
    @staticmethod
    def lineup_select(
        players: List[Player],
        selected_ids: List[UUID],
        formation: Formation
    ) -> InlineKeyboardMarkup:
        """Выбор состава"""
        builder = InlineKeyboardBuilder()
        
        # Группируем по позициям
        for position in [Position.GOALKEEPER, Position.DEFENDER, Position.MIDFIELDER, Position.FORWARD]:
            position_players = [p for p in players if p.position == position]
            
            builder.row(
                InlineKeyboardButton(
                    text=f"── {position.value.upper()} ──",
                    callback_data="noop"
                )
            )
            
            for player in position_players:
                is_selected = player.id in selected_ids
                emoji = "✅" if is_selected else "⬜"
                
                builder.row(
                    InlineKeyboardButton(
                        text=f"{emoji} #{player.number} {player.name}",
                        callback_data=LineupCallback(
                            action="select",
                            player_id=str(player.id)
                        ).pack()
                    )
                )
        
        builder.row(
            InlineKeyboardButton(
                text="✅ Подтвердить состав",
                callback_data=LineupCallback(action="confirm").pack()
            )
        )
        
        return builder.as_markup()
    
    @staticmethod
    def bet_type_select(
        player: Player,
        available_types: List[BetType]
    ) -> InlineKeyboardMarkup:
        """Выбор типа ставки"""
        builder = InlineKeyboardBuilder()
        
        builder.row(
            InlineKeyboardButton(
                text=f"📊 Ставка на {player.name} (#{player.number})",
                callback_data="noop"
            )
        )
        
        type_labels = {
            BetType.EVEN_ODD: "🎯 Чёт/Нечёт (отбития)",
            BetType.HIGH_LOW: "↕️ Больше/Меньше (передачи)",
            BetType.EXACT_NUMBER: "🎱 Точное число (гол)"
        }
        
        for bet_type in available_types:
            builder.row(
                InlineKeyboardButton(
                    text=type_labels[bet_type],
                    callback_data=BetCallback(
                        action="place",
                        bet_type=bet_type.value,
                        player_id=str(player.id)
                    ).pack()
                )
            )
        
        return builder.as_markup()
    
    @staticmethod
    def even_odd_select(player_id: str) -> InlineKeyboardMarkup:
        """Выбор чёт/нечёт"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="Чётное (2, 4, 6)",
                callback_data=BetCallback(
                    action="confirm",
                    bet_type="even_odd",
                    value="even",
                    player_id=player_id
                ).pack()
            ),
            InlineKeyboardButton(
                text="Нечётное (1, 3, 5)",
                callback_data=BetCallback(
                    action="confirm",
                    bet_type="even_odd",
                    value="odd",
                    player_id=player_id
                ).pack()
            )
        )
        return builder.as_markup()
    
    @staticmethod
    def high_low_select(player_id: str) -> InlineKeyboardMarkup:
        """Выбор больше/меньше"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="Меньше (1-3)",
                callback_data=BetCallback(
                    action="confirm",
                    bet_type="high_low",
                    value="low",
                    player_id=player_id
                ).pack()
            ),
            InlineKeyboardButton(
                text="Больше (4-6)",
                callback_data=BetCallback(
                    action="confirm",
                    bet_type="high_low",
                    value="high",
                    player_id=player_id
                ).pack()
            )
        )
        return builder.as_markup()
    
    @staticmethod
    def exact_number_select(player_id: str) -> InlineKeyboardMarkup:
        """Выбор точного числа"""
        builder = InlineKeyboardBuilder()
        for i in range(1, 7):
            builder.add(
                InlineKeyboardButton(
                    text=str(i),
                    callback_data=BetCallback(
                        action="confirm",
                        bet_type="exact_number",
                        value=str(i),
                        player_id=player_id
                    ).pack()
                )
            )
        builder.adjust(3)  # 2 ряда по 3 кнопки
        return builder.as_markup()
    
    @staticmethod
    def game_actions(
        can_roll: bool = True,
        can_draw_card: bool = False,
        can_end_turn: bool = False
    ) -> InlineKeyboardMarkup:
        """Игровые действия"""
        builder = InlineKeyboardBuilder()
        
        if can_roll:
            builder.row(
                InlineKeyboardButton(
                    text="🎲 Бросить кубик",
                    callback_data=GameCallback(action="roll_dice").pack()
                )
            )
        
        if can_draw_card:
            builder.row(
                InlineKeyboardButton(
                    text="🃏 Взять карточку",
                    callback_data=GameCallback(action="draw_card").pack()
                )
            )
        
        if can_end_turn:
            builder.row(
                InlineKeyboardButton(
                    text="➡️ Завершить ход",
                    callback_data=GameCallback(action="end_turn").pack()
                )
            )
        
        return builder.as_markup()
    
    @staticmethod
    def card_target_select(
        card: WhistleCard,
        targets: List[Player]
    ) -> InlineKeyboardMarkup:
        """Выбор цели для карточки"""
        builder = InlineKeyboardBuilder()
        
        card_names = {
            CardType.HAT_TRICK: "Хэт-трик (+3 гола)",
            CardType.DOUBLE: "Дубль (+2 гола)",
            CardType.GOAL: "Гол (+1 гол)",
            CardType.OFFSIDE: "Офсайд (отменить гол)",
            CardType.RED_CARD: "Удаление",
            CardType.YELLOW_CARD: "Предупреждение",
            CardType.FOUL: "Фол (-1 отбитие)",
            CardType.LOSS: "Потеря (-1 передача)",
            CardType.INTERCEPTION: "Перехват (+1 передача)",
            CardType.TACKLE: "Отбор (+1 отбитие)",
        }
        
        builder.row(
            InlineKeyboardButton(
                text=f"🃏 {card_names.get(card.card_type, card.card_type.value)}",
                callback_data="noop"
            )
        )
        
        builder.row(
            InlineKeyboardButton(
                text="Выберите игрока:",
                callback_data="noop"
            )
        )
        
        for player in targets:
            stats_text = f"О:{player.stats.saves} П:{player.stats.passes} Г:{player.stats.goals}"
            builder.row(
                InlineKeyboardButton(
                    text=f"#{player.number} {player.name} [{stats_text}]",
                    callback_data=CardCallback(
                        action="apply",
                        card_id=str(card.id),
                        target_player_id=str(player.id)
                    ).pack()
                )
            )
        
        return builder.as_markup()
    
    @staticmethod
    def confirmation(context: str, question: str) -> InlineKeyboardMarkup:
        """Подтверждение действия"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Да",
                callback_data=ConfirmCallback(action="yes", context=context).pack()
            ),
            InlineKeyboardButton(
                text="❌ Нет",
                callback_data=ConfirmCallback(action="no", context=context).pack()
            )
        )
        return builder.as_markup()
```

---

## 5. Renderers

```python
# src/platforms/telegram/renderers/match_renderer.py

from typing import Optional, List
from src.core.models.match import Match, MatchStatus, MatchPhase
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetOutcome
from src.core.models.whistle_card import WhistleCard, CardType
from src.core.models.user import User

class MatchRenderer:
    """Рендеринг сообщений о матче"""
    
    @staticmethod
    def render_match_status(match: Match, user: User) -> str:
        """Общий статус матча"""
        status_emoji = {
            MatchStatus.WAITING_FOR_OPPONENT: "⏳",
            MatchStatus.SETTING_LINEUP: "📋",
            MatchStatus.IN_PROGRESS: "⚽",
            MatchStatus.EXTRA_TIME: "⏰",
            MatchStatus.PENALTIES: "🥅",
            MatchStatus.FINISHED: "🏁",
            MatchStatus.CANCELLED: "❌"
        }
        
        status_text = {
            MatchStatus.WAITING_FOR_OPPONENT: "Ожидание соперника",
            MatchStatus.SETTING_LINEUP: "Выбор состава",
            MatchStatus.IN_PROGRESS: "Матч идёт",
            MatchStatus.EXTRA_TIME: "Дополнительное время",
            MatchStatus.PENALTIES: "Серия пенальти",
            MatchStatus.FINISHED: "Матч завершён",
            MatchStatus.CANCELLED: "Матч отменён"
        }
        
        emoji = status_emoji.get(match.status, "❓")
        text = status_text.get(match.status, "Неизвестно")
        
        lines = [
            f"{emoji} <b>Матч: {text}</b>",
            ""
        ]
        
        # Счёт
        if match.status in [MatchStatus.IN_PROGRESS, MatchStatus.EXTRA_TIME, 
                           MatchStatus.PENALTIES, MatchStatus.FINISHED]:
            lines.append(f"📊 Счёт: <b>{match.score.manager1_goals} : {match.score.manager2_goals}</b>")
            lines.append("")
        
        # Чей ход
        if match.current_turn and match.status == MatchStatus.IN_PROGRESS:
            is_my_turn = match.is_manager_turn(user.id)
            turn_text = "🟢 Ваш ход" if is_my_turn else "🔴 Ход соперника"
            lines.append(f"Ход #{match.current_turn.turn_number} | {turn_text}")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_team_stats(team: Team, is_own: bool = True) -> str:
        """Статистика команды"""
        team.calculate_stats()
        
        header = "📊 <b>Ваша команда</b>" if is_own else "📊 <b>Команда соперника</b>"
        
        lines = [
            header,
            f"Формация: {team.formation.value if team.formation else 'не выбрана'}",
            "",
            f"⛔ Отбития: {team.stats.total_saves}",
            f"↗️ Передачи: {team.stats.total_passes}",
            f"⚽ Голы: {team.stats.total_goals}",
        ]
        
        return "\n".join(lines)
    
    @staticmethod
    def render_field_players(team: Team) -> str:
        """Игроки на поле"""
        lines = ["<b>🏟 Игроки на поле:</b>", ""]
        
        position_names = {
            Position.GOALKEEPER: "🧤 Вратарь",
            Position.DEFENDER: "🛡 Защитники",
            Position.MIDFIELDER: "🏃 Полузащитники",
            Position.FORWARD: "⚡ Форварды"
        }
        
        for position in [Position.GOALKEEPER, Position.DEFENDER, 
                        Position.MIDFIELDER, Position.FORWARD]:
            players = [p for p in team.get_field_players() if p.position == position]
            if players:
                lines.append(f"<b>{position_names[position]}:</b>")
                for p in players:
                    stats = f"[О:{p.stats.saves} П:{p.stats.passes} Г:{p.stats.goals}]"
                    available = "" if p.is_available else " ❌"
                    lines.append(f"  #{p.number} {p.name} {stats}{available}")
                lines.append("")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_turn_summary(
        match: Match,
        dice_value: int,
        won_bets: List[Bet],
        card: Optional[WhistleCard]
    ) -> str:
        """Итог хода"""
        lines = [
            f"🎲 Выпало: <b>{dice_value}</b>",
            ""
        ]
        
        if won_bets:
            lines.append("✅ <b>Выигравшие ставки:</b>")
            for bet in won_bets:
                bet_desc = {
                    "even_odd": "Чёт/Нечёт",
                    "high_low": "Больше/Меньше",
                    "exact_number": f"Число {bet.exact_number}"
                }
                lines.append(f"  • {bet_desc.get(bet.bet_type.value, bet.bet_type.value)}")
            lines.append("")
        else:
            lines.append("❌ Нет выигравших ставок")
            lines.append("")
        
        if card:
            card_names = {
                CardType.HAT_TRICK: "🎩 Хэт-трик!",
                CardType.DOUBLE: "✌️ Дубль!",
                CardType.GOAL: "⚽ Гол!",
                CardType.OWN_GOAL: "😱 Автогол!",
                CardType.VAR: "📺 ВАР",
                CardType.OFFSIDE: "🚩 Офсайд",
                CardType.PENALTY: "🥅 Пенальти",
                CardType.RED_CARD: "🟥 Удаление",
                CardType.YELLOW_CARD: "🟨 Предупреждение",
                CardType.FOUL: "⚠️ Фол",
                CardType.LOSS: "💨 Потеря",
                CardType.INTERCEPTION: "🦅 Перехват",
                CardType.TACKLE: "🦵 Отбор"
            }
            lines.append(f"🃏 Карточка: {card_names.get(card.card_type, card.card_type.value)}")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_match_result(match: Match, user_id) -> str:
        """Результат матча"""
        is_winner = match.result.winner_id == user_id
        
        if is_winner:
            header = "🎉 <b>ПОБЕДА!</b> 🎉"
        else:
            header = "😔 <b>Поражение</b>"
        
        decided_text = {
            MatchPhase.MAIN_TIME: "основное время",
            MatchPhase.EXTRA_TIME: "дополнительное время",
            MatchPhase.PENALTIES: "серия пенальти"
        }
        
        lines = [
            header,
            "",
            f"📊 Итоговый счёт: <b>{match.score.manager1_goals} : {match.score.manager2_goals}</b>",
            f"⏱ Решено в: {decided_text.get(match.result.decided_by, '?')}",
        ]
        
        if match.result.decided_by_lottery:
            lines.append("🎰 Победитель определён жребием")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_player_for_bet(player: Player) -> str:
        """Информация об игроке для ставки"""
        position_names = {
            Position.GOALKEEPER: "Вратарь",
            Position.DEFENDER: "Защитник",
            Position.MIDFIELDER: "Полузащитник",
            Position.FORWARD: "Форвард"
        }
        
        lines = [
            f"<b>#{player.number} {player.name}</b>",
            f"Позиция: {position_names.get(player.position, '?')}",
            "",
            f"Текущие действия:",
            f"  ⛔ Отбития: {player.stats.saves}",
            f"  ↗️ Передачи: {player.stats.passes}",
            f"  ⚽ Голы: {player.stats.goals}",
        ]
        
        return "\n".join(lines)
```

---

## 6. Handlers

### 6.1 Start Handler

```python
# src/platforms/telegram/handlers/start.py

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

from src.core.models.user import User
from ..keyboards.inline import Keyboards
from ..callbacks.callback_data import MenuCallback

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, user: User):
    """Обработка /start"""
    await message.answer(
        f"👋 Привет, <b>{user.username}</b>!\n\n"
        f"Добро пожаловать в <b>Final 4</b> — пошаговую футбольную стратегию!\n\n"
        f"📊 Ваш рейтинг: <b>{user.rating}</b>\n"
        f"🏆 Побед: <b>{user.stats.matches_won}</b>\n\n"
        f"Выберите действие:",
        reply_markup=Keyboards.main_menu()
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработка /help"""
    help_text = """
<b>📖 Правила игры Final 4</b>

<b>Цель:</b> Победить соперника, набрав больше голов.

<b>Как играть:</b>
1. Выберите формацию (расстановку игроков)
2. Выставите 11 игроков на поле
3. На каждого игрока делайте ставки
4. Бросайте кубик — если угадали, игрок получает действия
5. Карточки «Свисток» добавляют элемент случайности

<b>Типы ставок:</b>
• Чёт/Нечёт → Отбития
• Больше/Меньше → Передачи
• Точное число → Гол

<b>Подсчёт голов:</b>
Ваши передачи "ломают" отбития соперника.
Голы забиваются, если оборона взломана.

/start — Главное меню
/profile — Ваш профиль
/leaderboard — Таблица лидеров
    """
    await message.answer(help_text)

@router.callback_query(MenuCallback.filter(F.action == "play"))
async def menu_play(callback: CallbackQuery):
    """Меню игры"""
    await callback.message.edit_text(
        "⚽ <b>Выберите режим игры:</b>",
        reply_markup=Keyboards.play_menu()
    )
    await callback.answer()

@router.callback_query(MenuCallback.filter(F.action == "back"))
async def menu_back(callback: CallbackQuery, user: User):
    """Назад в главное меню"""
    await callback.message.edit_text(
        f"👋 <b>{user.username}</b>\n\n"
        f"📊 Рейтинг: <b>{user.rating}</b>\n"
        f"🏆 Побед: <b>{user.stats.matches_won}</b>\n\n"
        f"Выберите действие:",
        reply_markup=Keyboards.main_menu()
    )
    await callback.answer()
```

### 6.2 Match Handler

```python
# src/platforms/telegram/handlers/match.py

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from src.core.models.user import User
from src.core.models.match import MatchType
from src.application.services.match_service import MatchService
from src.infrastructure.cache.session_cache import SessionCache

from ..keyboards.inline import Keyboards
from ..callbacks.callback_data import MatchCallback, FormationCallback, LineupCallback
from ..renderers.match_renderer import MatchRenderer
from ..states.match_states import MatchStates

router = Router()

@router.callback_query(MatchCallback.filter(F.action == "create"))
async def create_match(
    callback: CallbackQuery,
    user: User,
    match_service: MatchService,
    session_cache: SessionCache,
    state: FSMContext
):
    """Создать матч против случайного соперника"""
    # Проверяем лимиты
    if not user.can_play_match():
        await callback.answer("Вы достигли лимита матчей на сегодня!", show_alert=True)
        return
    
    # Ищем ожидающий матч
    waiting_match = await match_service.find_waiting_match("telegram")
    
    if waiting_match and waiting_match.manager1_id != user.id:
        # Присоединяемся к существующему
        match = await match_service.join_match(waiting_match.id, user.id)
        await session_cache.set_active_match(user.id, match.id)
        
        await callback.message.edit_text(
            "🎮 Соперник найден!\n\n"
            "Выберите формацию для вашей команды:",
            reply_markup=Keyboards.formation_select()
        )
    else:
        # Создаём новый
        match = await match_service.create_match(user.id, MatchType.RANDOM, "telegram")
        await session_cache.set_active_match(user.id, match.id)
        
        await callback.message.edit_text(
            "⏳ Матч создан!\n\n"
            "Ожидаем соперника...\n"
            "Вы получите уведомление, когда кто-то присоединится.",
            reply_markup=Keyboards.confirmation("cancel_match", "Отменить поиск?")
        )
    
    await state.set_state(MatchStates.waiting_opponent)
    await callback.answer()

@router.callback_query(MatchCallback.filter(F.action == "vs_bot"))
async def create_bot_match(
    callback: CallbackQuery,
    user: User,
    match_service: MatchService,
    session_cache: SessionCache,
    state: FSMContext
):
    """Создать матч против бота"""
    if not user.can_play_match():
        await callback.answer("Вы достигли лимита матчей на сегодня!", show_alert=True)
        return
    
    match = await match_service.create_match(user.id, MatchType.VS_BOT, "telegram")
    await session_cache.set_active_match(user.id, match.id)
    
    await callback.message.edit_text(
        "🤖 Матч против бота создан!\n\n"
        "Выберите формацию для вашей команды:",
        reply_markup=Keyboards.formation_select()
    )
    
    await state.set_state(MatchStates.selecting_formation)
    await callback.answer()

@router.callback_query(FormationCallback.filter())
async def select_formation(
    callback: CallbackQuery,
    callback_data: FormationCallback,
    user: User,
    match_service: MatchService,
    session_cache: SessionCache,
    state: FSMContext
):
    """Выбор формации"""
    match_id = await session_cache.get_active_match(user.id)
    if not match_id:
        await callback.answer("Матч не найден!", show_alert=True)
        return
    
    # Сохраняем выбранную формацию
    await state.update_data(formation=callback_data.formation)
    
    # Получаем команду пользователя
    team = await match_service.get_user_team(user.id)
    
    await callback.message.edit_text(
        f"📋 Формация: <b>{callback_data.formation}</b>\n\n"
        "Выберите 11 игроков для выхода на поле:",
        reply_markup=Keyboards.lineup_select(team.players, [], callback_data.formation)
    )
    
    await state.set_state(MatchStates.selecting_lineup)
    await state.update_data(selected_players=[])
    await callback.answer()

@router.callback_query(LineupCallback.filter(F.action == "select"))
async def toggle_player(
    callback: CallbackQuery,
    callback_data: LineupCallback,
    user: User,
    match_service: MatchService,
    state: FSMContext
):
    """Добавить/убрать игрока из состава"""
    data = await state.get_data()
    selected = data.get("selected_players", [])
    formation = data.get("formation")
    
    player_id = callback_data.player_id
    
    if player_id in selected:
        selected.remove(player_id)
    else:
        if len(selected) < 11:
            selected.append(player_id)
        else:
            await callback.answer("Уже выбрано 11 игроков!", show_alert=True)
            return
    
    await state.update_data(selected_players=selected)
    
    team = await match_service.get_user_team(user.id)
    
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.lineup_select(
            team.players,
            [UUID(pid) for pid in selected],
            formation
        )
    )
    await callback.answer()

@router.callback_query(LineupCallback.filter(F.action == "confirm"))
async def confirm_lineup(
    callback: CallbackQuery,
    user: User,
    match_service: MatchService,
    session_cache: SessionCache,
    state: FSMContext
):
    """Подтвердить состав"""
    data = await state.get_data()
    selected = data.get("selected_players", [])
    formation = data.get("formation")
    
    if len(selected) != 11:
        await callback.answer(f"Выберите 11 игроков! Сейчас: {len(selected)}", show_alert=True)
        return
    
    match_id = await session_cache.get_active_match(user.id)
    
    try:
        match = await match_service.set_lineup(
            match_id,
            user.id,
            formation,
            [UUID(pid) for pid in selected]
        )
        
        renderer = MatchRenderer()
        status_text = renderer.render_match_status(match, user)
        
        if match.status == MatchStatus.IN_PROGRESS:
            # Оба готовы, матч начался
            await callback.message.edit_text(
                f"{status_text}\n\n"
                "⚽ Матч начался!\n"
                "Сделайте ставки на вратаря:",
                reply_markup=Keyboards.bet_type_select(
                    match.get_team(user.id).get_goalkeeper(),
                    [BetType.EVEN_ODD]
                )
            )
            await state.set_state(MatchStates.placing_bets)
        else:
            # Ждём соперника
            await callback.message.edit_text(
                "✅ Состав подтверждён!\n\n"
                "Ожидаем, пока соперник выберет состав..."
            )
            await state.set_state(MatchStates.waiting_opponent_lineup)
        
        await callback.answer()
        
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
```

### 6.3 Game Handler (частичный пример)

```python
# src/platforms/telegram/handlers/game.py

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from uuid import UUID

from src.core.models.user import User
from src.application.services.match_service import MatchService
from src.infrastructure.cache.session_cache import SessionCache

from ..keyboards.inline import Keyboards
from ..callbacks.callback_data import GameCallback, CardCallback
from ..renderers.match_renderer import MatchRenderer
from ..states.match_states import MatchStates

router = Router()

@router.callback_query(GameCallback.filter(F.action == "roll_dice"))
async def roll_dice(
    callback: CallbackQuery,
    user: User,
    match_service: MatchService,
    session_cache: SessionCache
):
    """Бросок кубика"""
    match_id = await session_cache.get_active_match(user.id)
    if not match_id:
        await callback.answer("Матч не найден!", show_alert=True)
        return
    
    try:
        match, dice_value, won_bets = await match_service.roll_dice(match_id, user.id)
        
        renderer = MatchRenderer()
        turn_summary = renderer.render_turn_summary(match, dice_value, won_bets, None)
        
        # Определяем следующее действие
        if won_bets:
            # Есть выигрыш — можно взять карточку
            await callback.message.edit_text(
                turn_summary,
                reply_markup=Keyboards.game_actions(
                    can_roll=False,
                    can_draw_card=True,
                    can_end_turn=True
                )
            )
        else:
            # Нет выигрыша — сразу завершаем ход
            await callback.message.edit_text(
                turn_summary,
                reply_markup=Keyboards.game_actions(
                    can_roll=False,
                    can_draw_card=False,
                    can_end_turn=True
                )
            )
        
        await callback.answer(f"🎲 Выпало: {dice_value}")
        
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)

@router.callback_query(GameCallback.filter(F.action == "draw_card"))
async def draw_card(
    callback: CallbackQuery,
    user: User,
    match_service: MatchService,
    session_cache: SessionCache
):
    """Взять карточку Свисток"""
    match_id = await session_cache.get_active_match(user.id)
    
    try:
        match, card = await match_service.draw_whistle_card(match_id, user.id)
        
        if card:
            # Нужно выбрать цель
            target_type = card.get_target_type()
            
            if target_type in [CardTarget.SELF_PLAYER]:
                targets = match.get_team(user.id).get_field_players()
            else:
                targets = match.get_opponent_team(user.id).get_field_players()
            
            await callback.message.edit_text(
                f"🃏 Вы вытянули карточку!\n\n"
                f"Выберите цель:",
                reply_markup=Keyboards.card_target_select(card, targets)
            )
        else:
            await callback.message.edit_text(
                "🃏 Колода пуста или нет права на карточку.",
                reply_markup=Keyboards.game_actions(
                    can_roll=False,
                    can_draw_card=False,
                    can_end_turn=True
                )
            )
        
        await callback.answer()
        
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)

@router.callback_query(GameCallback.filter(F.action == "end_turn"))
async def end_turn(
    callback: CallbackQuery,
    user: User,
    match_service: MatchService,
    session_cache: SessionCache,
    state: FSMContext
):
    """Завершить ход"""
    match_id = await session_cache.get_active_match(user.id)
    
    try:
        match = await match_service.end_turn(match_id, user.id)
        
        renderer = MatchRenderer()
        
        if match.status == MatchStatus.FINISHED:
            # Матч завершён
            result_text = renderer.render_match_result(match, user.id)
            await callback.message.edit_text(
                result_text,
                reply_markup=Keyboards.main_menu()
            )
            await session_cache.clear_active_match(user.id)
            await state.clear()
        else:
            # Ход соперника
            status_text = renderer.render_match_status(match, user)
            await callback.message.edit_text(
                f"{status_text}\n\n"
                "⏳ Ожидаем ход соперника..."
            )
            await state.set_state(MatchStates.waiting_opponent_turn)
        
        await callback.answer()
        
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
```

---

## 7. FSM States

```python
# src/platforms/telegram/states/match_states.py

from aiogram.fsm.state import State, StatesGroup

class MatchStates(StatesGroup):
    """Состояния матча"""
    
    # Поиск/ожидание
    waiting_opponent = State()
    waiting_opponent_lineup = State()
    
    # Настройка
    selecting_formation = State()
    selecting_lineup = State()
    
    # Игра
    placing_bets = State()
    rolling_dice = State()
    drawing_card = State()
    applying_card = State()
    waiting_opponent_turn = State()
    
    # Пенальти
    penalty_shootout = State()
    
    # Завершение
    match_finished = State()
```

---

## 8. Middlewares

```python
# src/platforms/telegram/middlewares/auth.py

from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from uuid import uuid4
from datetime import datetime

from src.infrastructure.db.database import Database
from src.infrastructure.repositories.user_repository import UserRepository
from src.core.models.user import User, PlatformIds

class AuthMiddleware(BaseMiddleware):
    """Middleware для авторизации пользователей"""
    
    def __init__(self, database: Database):
        self.database = database
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем telegram_id
        if isinstance(event, Message):
            telegram_id = event.from_user.id
            username = event.from_user.username or event.from_user.first_name
        elif isinstance(event, CallbackQuery):
            telegram_id = event.from_user.id
            username = event.from_user.username or event.from_user.first_name
        else:
            return await handler(event, data)
        
        # Ищем или создаём пользователя
        async with self.database.session() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(telegram_id)
            
            if not user:
                # Создаём нового
                user = User(
                    id=uuid4(),
                    username=username,
                    platform_ids=PlatformIds(telegram_id=telegram_id),
                    created_at=datetime.utcnow(),
                    last_active_at=datetime.utcnow()
                )
                user = await repo.create(user)
            else:
                # Обновляем last_active
                user.last_active_at = datetime.utcnow()
                user = await repo.update(user)
        
        # Добавляем user в data
        data["user"] = user
        
        return await handler(event, data)
```

```python
# src/platforms/telegram/middlewares/rate_limit.py

from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.infrastructure.cache.redis_client import RedisClient
from src.infrastructure.cache.rate_limiter import RateLimiter

class RateLimitMiddleware(BaseMiddleware):
    """Middleware для rate limiting"""
    
    MAX_REQUESTS = 30  # запросов
    WINDOW_SECONDS = 60  # в минуту
    
    def __init__(self, redis: RedisClient):
        self.limiter = RateLimiter(redis)
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            user_id = event.from_user.id
            key = f"telegram:{user_id}"
            
            if not await self.limiter.is_allowed(key, self.MAX_REQUESTS, self.WINDOW_SECONDS):
                await event.answer("⚠️ Слишком много запросов. Подождите немного.")
                return
        
        return await handler(event, data)
```
