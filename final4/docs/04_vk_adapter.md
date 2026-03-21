# Модуль: VK Adapter

## Обзор

Адаптер для платформы ВКонтакте. Использует VKBottle для асинхронной обработки.

---

## 1. Структура модуля

```
src/platforms/vk/
├── __init__.py
├── bot.py                  # Инициализация бота
├── handlers/
│   ├── __init__.py
│   ├── start.py            # Приветствие
│   ├── match.py            # Создание/поиск матча
│   ├── bet.py              # Размещение ставок
│   ├── game.py             # Игровой процесс
│   └── profile.py          # Профиль, статистика
├── keyboards/
│   ├── __init__.py
│   └── vk_keyboards.py     # VK клавиатуры
├── payloads/
│   ├── __init__.py
│   └── payload_factory.py  # Payload factories
├── renderers/
│   ├── __init__.py
│   └── match_renderer.py   # Рендеринг (VK formatting)
└── middlewares/
    ├── __init__.py
    └── auth.py             # Авторизация
```

---

## 2. Bot Initialization

```python
# src/platforms/vk/bot.py

from vkbottle import Bot, API
from vkbottle.bot import BotLabeler

from src.infrastructure.db.database import Database
from src.infrastructure.cache.redis_client import RedisClient
from src.application.services.match_service import MatchService
from src.application.services.user_service import UserService

from .handlers import start, match, bet, game, profile
from .middlewares.auth import AuthMiddleware

class VKBot:
    """VK бот Final 4"""
    
    def __init__(
        self,
        token: str,
        group_id: int,
        database: Database,
        redis: RedisClient
    ):
        self.api = API(token=token)
        self.bot = Bot(api=self.api)
        self.group_id = group_id
        
        self.database = database
        self.redis = redis
        
        # Services
        self.user_service = UserService()
        self.match_service = MatchService()
        
        self._setup_middlewares()
        self._setup_handlers()
    
    def _setup_middlewares(self) -> None:
        """Настройка middleware"""
        self.bot.labeler.message_view.register_middleware(
            AuthMiddleware(self.database)
        )
    
    def _setup_handlers(self) -> None:
        """Настройка обработчиков"""
        labeler = BotLabeler()
        
        # Register handlers
        labeler.load(start.labeler)
        labeler.load(match.labeler)
        labeler.load(bet.labeler)
        labeler.load(game.labeler)
        labeler.load(profile.labeler)
        
        self.bot.labeler.load(labeler)
    
    async def start(self) -> None:
        """Запуск бота"""
        await self.bot.run_polling()
    
    async def stop(self) -> None:
        """Остановка бота"""
        pass  # VKBottle handles this
```

---

## 3. Payloads (VK Callback Data)

```python
# src/platforms/vk/payloads/payload_factory.py

import json
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

@dataclass
class BasePayload:
    """Базовый payload"""
    action: str
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BasePayload':
        return cls(**data)

@dataclass
class MenuPayload(BasePayload):
    """Payload главного меню"""
    action: str = "menu"
    menu_action: str = ""  # play, profile, leaderboard, settings, back

@dataclass
class MatchPayload(BasePayload):
    """Payload для матча"""
    action: str = "match"
    match_action: str = ""  # create, join, cancel, vs_bot
    match_id: Optional[str] = None

@dataclass
class FormationPayload(BasePayload):
    """Payload выбора формации"""
    action: str = "formation"
    formation: str = ""  # 1-5-3-2, etc.

@dataclass
class LineupPayload(BasePayload):
    """Payload выбора состава"""
    action: str = "lineup"
    lineup_action: str = ""  # select, confirm, back
    player_id: Optional[str] = None

@dataclass
class BetPayload(BasePayload):
    """Payload ставки"""
    action: str = "bet"
    bet_action: str = ""  # place, confirm
    bet_type: Optional[str] = None
    value: Optional[str] = None
    player_id: Optional[str] = None

@dataclass
class GamePayload(BasePayload):
    """Payload игрового процесса"""
    action: str = "game"
    game_action: str = ""  # roll_dice, draw_card, apply_card, end_turn
    target_player_id: Optional[str] = None

@dataclass
class CardPayload(BasePayload):
    """Payload карточки"""
    action: str = "card"
    card_action: str = ""  # apply, select_target
    card_id: Optional[str] = None
    target_player_id: Optional[str] = None

@dataclass
class ConfirmPayload(BasePayload):
    """Payload подтверждения"""
    action: str = "confirm"
    confirm_action: str = ""  # yes, no
    context: str = ""

def parse_payload(payload_str: str) -> Optional[BasePayload]:
    """Парсинг payload из строки"""
    try:
        data = json.loads(payload_str)
        action = data.get("action", "")
        
        payload_map = {
            "menu": MenuPayload,
            "match": MatchPayload,
            "formation": FormationPayload,
            "lineup": LineupPayload,
            "bet": BetPayload,
            "game": GamePayload,
            "card": CardPayload,
            "confirm": ConfirmPayload,
        }
        
        payload_class = payload_map.get(action, BasePayload)
        return payload_class.from_dict(data)
    except (json.JSONDecodeError, TypeError):
        return None
```

---

## 4. Keyboards

```python
# src/platforms/vk/keyboards/vk_keyboards.py

from vkbottle import Keyboard, KeyboardButtonColor, Text, Callback
from typing import List, Optional
from uuid import UUID

from src.core.models.team import Formation
from src.core.models.player import Player, Position
from src.core.models.bet import BetType
from src.core.models.whistle_card import WhistleCard, CardType

from ..payloads.payload_factory import (
    MenuPayload, MatchPayload, FormationPayload, LineupPayload,
    BetPayload, GamePayload, CardPayload, ConfirmPayload
)

class VKKeyboards:
    """Фабрика VK клавиатур"""
    
    @staticmethod
    def main_menu() -> str:
        """Главное меню"""
        keyboard = Keyboard(inline=True)
        
        keyboard.add(Callback(
            label="⚽ Играть",
            payload=MenuPayload(menu_action="play").to_json()
        ), color=KeyboardButtonColor.POSITIVE)
        
        keyboard.row()
        
        keyboard.add(Callback(
            label="👤 Профиль",
            payload=MenuPayload(menu_action="profile").to_json()
        ))
        
        keyboard.add(Callback(
            label="🏆 Рейтинг",
            payload=MenuPayload(menu_action="leaderboard").to_json()
        ))
        
        keyboard.row()
        
        keyboard.add(Callback(
            label="⚙️ Настройки",
            payload=MenuPayload(menu_action="settings").to_json()
        ))
        
        return keyboard.get_json()
    
    @staticmethod
    def play_menu() -> str:
        """Меню выбора типа игры"""
        keyboard = Keyboard(inline=True)
        
        keyboard.add(Callback(
            label="🎲 Случайный соперник",
            payload=MatchPayload(match_action="create").to_json()
        ), color=KeyboardButtonColor.POSITIVE)
        
        keyboard.row()
        
        keyboard.add(Callback(
            label="🤖 Против бота",
            payload=MatchPayload(match_action="vs_bot").to_json()
        ), color=KeyboardButtonColor.PRIMARY)
        
        keyboard.row()
        
        keyboard.add(Callback(
            label="🔙 Назад",
            payload=MenuPayload(menu_action="back").to_json()
        ))
        
        return keyboard.get_json()
    
    @staticmethod
    def formation_select() -> str:
        """Выбор формации"""
        keyboard = Keyboard(inline=True)
        
        formations = [
            "1-5-3-2", "1-5-2-3", "1-4-4-2", "1-4-3-3",
            "1-3-5-2", "1-3-4-3", "1-3-3-4"
        ]
        
        for i, formation in enumerate(formations):
            keyboard.add(Callback(
                label=formation,
                payload=FormationPayload(formation=formation).to_json()
            ))
            if (i + 1) % 2 == 0:  # 2 кнопки в ряд
                keyboard.row()
        
        return keyboard.get_json()
    
    @staticmethod
    def lineup_select(
        players: List[Player],
        selected_ids: List[UUID],
        page: int = 0,
        per_page: int = 5
    ) -> str:
        """Выбор состава (с пагинацией для VK)"""
        keyboard = Keyboard(inline=True)
        
        # VK ограничивает кнопки, поэтому пагинация
        start = page * per_page
        end = start + per_page
        page_players = players[start:end]
        
        for player in page_players:
            is_selected = player.id in selected_ids
            emoji = "✅" if is_selected else "⬜"
            
            keyboard.add(Callback(
                label=f"{emoji} #{player.number} {player.name[:15]}",
                payload=LineupPayload(
                    lineup_action="select",
                    player_id=str(player.id)
                ).to_json()
            ))
            keyboard.row()
        
        # Навигация
        nav_row = []
        if page > 0:
            keyboard.add(Callback(
                label="⬅️ Назад",
                payload=LineupPayload(lineup_action="prev_page").to_json()
            ))
        
        if end < len(players):
            keyboard.add(Callback(
                label="➡️ Далее",
                payload=LineupPayload(lineup_action="next_page").to_json()
            ))
        
        keyboard.row()
        
        keyboard.add(Callback(
            label=f"✅ Подтвердить ({len(selected_ids)}/11)",
            payload=LineupPayload(lineup_action="confirm").to_json()
        ), color=KeyboardButtonColor.POSITIVE)
        
        return keyboard.get_json()
    
    @staticmethod
    def bet_type_select(
        player: Player,
        available_types: List[BetType]
    ) -> str:
        """Выбор типа ставки"""
        keyboard = Keyboard(inline=True)
        
        type_labels = {
            BetType.EVEN_ODD: "🎯 Чёт/Нечёт",
            BetType.HIGH_LOW: "↕️ Больше/Меньше",
            BetType.EXACT_NUMBER: "🎱 Точное число"
        }
        
        for bet_type in available_types:
            keyboard.add(Callback(
                label=type_labels[bet_type],
                payload=BetPayload(
                    bet_action="place",
                    bet_type=bet_type.value,
                    player_id=str(player.id)
                ).to_json()
            ))
            keyboard.row()
        
        return keyboard.get_json()
    
    @staticmethod
    def even_odd_select(player_id: str) -> str:
        """Выбор чёт/нечёт"""
        keyboard = Keyboard(inline=True)
        
        keyboard.add(Callback(
            label="Чётное (2,4,6)",
            payload=BetPayload(
                bet_action="confirm",
                bet_type="even_odd",
                value="even",
                player_id=player_id
            ).to_json()
        ))
        
        keyboard.add(Callback(
            label="Нечётное (1,3,5)",
            payload=BetPayload(
                bet_action="confirm",
                bet_type="even_odd",
                value="odd",
                player_id=player_id
            ).to_json()
        ))
        
        return keyboard.get_json()
    
    @staticmethod
    def high_low_select(player_id: str) -> str:
        """Выбор больше/меньше"""
        keyboard = Keyboard(inline=True)
        
        keyboard.add(Callback(
            label="Меньше (1-3)",
            payload=BetPayload(
                bet_action="confirm",
                bet_type="high_low",
                value="low",
                player_id=player_id
            ).to_json()
        ))
        
        keyboard.add(Callback(
            label="Больше (4-6)",
            payload=BetPayload(
                bet_action="confirm",
                bet_type="high_low",
                value="high",
                player_id=player_id
            ).to_json()
        ))
        
        return keyboard.get_json()
    
    @staticmethod
    def exact_number_select(player_id: str) -> str:
        """Выбор точного числа"""
        keyboard = Keyboard(inline=True)
        
        for i in range(1, 7):
            keyboard.add(Callback(
                label=str(i),
                payload=BetPayload(
                    bet_action="confirm",
                    bet_type="exact_number",
                    value=str(i),
                    player_id=player_id
                ).to_json()
            ))
            if i == 3:
                keyboard.row()
        
        return keyboard.get_json()
    
    @staticmethod
    def game_actions(
        can_roll: bool = True,
        can_draw_card: bool = False,
        can_end_turn: bool = False
    ) -> str:
        """Игровые действия"""
        keyboard = Keyboard(inline=True)
        
        if can_roll:
            keyboard.add(Callback(
                label="🎲 Бросить кубик",
                payload=GamePayload(game_action="roll_dice").to_json()
            ), color=KeyboardButtonColor.POSITIVE)
            keyboard.row()
        
        if can_draw_card:
            keyboard.add(Callback(
                label="🃏 Взять карточку",
                payload=GamePayload(game_action="draw_card").to_json()
            ), color=KeyboardButtonColor.PRIMARY)
            keyboard.row()
        
        if can_end_turn:
            keyboard.add(Callback(
                label="➡️ Завершить ход",
                payload=GamePayload(game_action="end_turn").to_json()
            ))
        
        return keyboard.get_json()
    
    @staticmethod
    def card_target_select(
        card: WhistleCard,
        targets: List[Player]
    ) -> str:
        """Выбор цели для карточки"""
        keyboard = Keyboard(inline=True)
        
        # Максимум 6 кнопок для VK
        for player in targets[:6]:
            stats = f"О:{player.stats.saves} П:{player.stats.passes}"
            keyboard.add(Callback(
                label=f"#{player.number} {player.name[:10]} [{stats}]",
                payload=CardPayload(
                    card_action="apply",
                    card_id=str(card.id),
                    target_player_id=str(player.id)
                ).to_json()
            ))
            keyboard.row()
        
        return keyboard.get_json()
    
    @staticmethod
    def confirmation(context: str) -> str:
        """Подтверждение действия"""
        keyboard = Keyboard(inline=True)
        
        keyboard.add(Callback(
            label="✅ Да",
            payload=ConfirmPayload(confirm_action="yes", context=context).to_json()
        ), color=KeyboardButtonColor.POSITIVE)
        
        keyboard.add(Callback(
            label="❌ Нет",
            payload=ConfirmPayload(confirm_action="no", context=context).to_json()
        ), color=KeyboardButtonColor.NEGATIVE)
        
        return keyboard.get_json()
```

---

## 5. Handlers

### 5.1 Start Handler

```python
# src/platforms/vk/handlers/start.py

from vkbottle.bot import BotLabeler, Message
from vkbottle import BaseStateGroup

from src.core.models.user import User
from ..keyboards.vk_keyboards import VKKeyboards
from ..payloads.payload_factory import MenuPayload, parse_payload

labeler = BotLabeler()

class MenuState(BaseStateGroup):
    MAIN = "main"
    PLAY = "play"

@labeler.message(text="Начать")
@labeler.message(text="начать")
@labeler.message(text="/start")
async def cmd_start(message: Message, user: User):
    """Обработка начала"""
    await message.answer(
        f"👋 Привет, {user.username}!\n\n"
        f"Добро пожаловать в Final 4 — пошаговую футбольную стратегию!\n\n"
        f"📊 Ваш рейтинг: {user.rating}\n"
        f"🏆 Побед: {user.stats.matches_won}\n\n"
        f"Выберите действие:",
        keyboard=VKKeyboards.main_menu()
    )

@labeler.message(payload_contains={"action": "menu"})
async def menu_handler(message: Message, user: User):
    """Обработка меню"""
    payload = parse_payload(message.payload)
    
    if not isinstance(payload, MenuPayload):
        return
    
    if payload.menu_action == "play":
        await message.answer(
            "⚽ Выберите режим игры:",
            keyboard=VKKeyboards.play_menu()
        )
    
    elif payload.menu_action == "profile":
        await message.answer(
            f"👤 Профиль: {user.username}\n\n"
            f"📊 Рейтинг: {user.rating}\n"
            f"🎮 Матчей: {user.stats.matches_played}\n"
            f"🏆 Побед: {user.stats.matches_won}\n"
            f"💔 Поражений: {user.stats.matches_lost}\n"
            f"🔥 Серия побед: {user.stats.win_streak}\n"
            f"⭐ Лучшая серия: {user.stats.best_win_streak}",
            keyboard=VKKeyboards.main_menu()
        )
    
    elif payload.menu_action == "back":
        await message.answer(
            f"👋 {user.username}\n\n"
            f"📊 Рейтинг: {user.rating}\n"
            f"🏆 Побед: {user.stats.matches_won}\n\n"
            f"Выберите действие:",
            keyboard=VKKeyboards.main_menu()
        )

@labeler.message(text="/help")
@labeler.message(text="Помощь")
async def cmd_help(message: Message):
    """Обработка помощи"""
    help_text = """
📖 Правила игры Final 4

Цель: Победить соперника, набрав больше голов.

Как играть:
1. Выберите формацию (расстановку игроков)
2. Выставите 11 игроков на поле
3. На каждого игрока делайте ставки
4. Бросайте кубик — если угадали, игрок получает действия
5. Карточки «Свисток» добавляют элемент случайности

Типы ставок:
• Чёт/Нечёт → Отбития
• Больше/Меньше → Передачи
• Точное число → Гол

Подсчёт голов:
Ваши передачи "ломают" отбития соперника.
Голы забиваются, если оборона взломана.
    """
    await message.answer(help_text, keyboard=VKKeyboards.main_menu())
```

### 5.2 Match Handler

```python
# src/platforms/vk/handlers/match.py

from vkbottle.bot import BotLabeler, Message
from vkbottle import BaseStateGroup
from uuid import UUID

from src.core.models.user import User
from src.core.models.match import MatchType, MatchStatus
from src.application.services.match_service import MatchService
from src.infrastructure.cache.session_cache import SessionCache

from ..keyboards.vk_keyboards import VKKeyboards
from ..payloads.payload_factory import MatchPayload, FormationPayload, LineupPayload, parse_payload
from ..renderers.match_renderer import VKMatchRenderer

labeler = BotLabeler()

class MatchState(BaseStateGroup):
    WAITING = "waiting"
    SELECTING_FORMATION = "selecting_formation"
    SELECTING_LINEUP = "selecting_lineup"
    IN_GAME = "in_game"

@labeler.message(payload_contains={"action": "match"})
async def match_handler(
    message: Message,
    user: User,
    match_service: MatchService,
    session_cache: SessionCache
):
    """Обработка действий с матчем"""
    payload = parse_payload(message.payload)
    
    if not isinstance(payload, MatchPayload):
        return
    
    if payload.match_action == "create":
        # Проверяем лимиты
        if not user.can_play_match():
            await message.answer("⚠️ Вы достигли лимита матчей на сегодня!")
            return
        
        # Ищем ожидающий матч
        waiting_match = await match_service.find_waiting_match("vk")
        
        if waiting_match and waiting_match.manager1_id != user.id:
            match = await match_service.join_match(waiting_match.id, user.id)
            await session_cache.set_active_match(user.id, match.id)
            
            await message.answer(
                "🎮 Соперник найден!\n\n"
                "Выберите формацию для вашей команды:",
                keyboard=VKKeyboards.formation_select()
            )
        else:
            match = await match_service.create_match(user.id, MatchType.RANDOM, "vk")
            await session_cache.set_active_match(user.id, match.id)
            
            await message.answer(
                "⏳ Матч создан!\n\n"
                "Ожидаем соперника...\n"
                "Вы получите уведомление, когда кто-то присоединится.",
                keyboard=VKKeyboards.confirmation("cancel_match")
            )
    
    elif payload.match_action == "vs_bot":
        if not user.can_play_match():
            await message.answer("⚠️ Вы достигли лимита матчей на сегодня!")
            return
        
        match = await match_service.create_match(user.id, MatchType.VS_BOT, "vk")
        await session_cache.set_active_match(user.id, match.id)
        
        await message.answer(
            "🤖 Матч против бота создан!\n\n"
            "Выберите формацию для вашей команды:",
            keyboard=VKKeyboards.formation_select()
        )

@labeler.message(payload_contains={"action": "formation"})
async def formation_handler(
    message: Message,
    user: User,
    match_service: MatchService,
    session_cache: SessionCache
):
    """Выбор формации"""
    payload = parse_payload(message.payload)
    
    if not isinstance(payload, FormationPayload):
        return
    
    match_id = await session_cache.get_active_match(user.id)
    if not match_id:
        await message.answer("⚠️ Матч не найден!")
        return
    
    # Сохраняем формацию в Redis state
    await session_cache.set_user_state(user.id, {
        "formation": payload.formation,
        "selected_players": [],
        "lineup_page": 0
    })
    
    # Получаем команду
    team = await match_service.get_user_team(user.id)
    
    await message.answer(
        f"📋 Формация: {payload.formation}\n\n"
        "Выберите 11 игроков для выхода на поле:",
        keyboard=VKKeyboards.lineup_select(team.players, [], page=0)
    )

@labeler.message(payload_contains={"action": "lineup"})
async def lineup_handler(
    message: Message,
    user: User,
    match_service: MatchService,
    session_cache: SessionCache
):
    """Выбор состава"""
    payload = parse_payload(message.payload)
    
    if not isinstance(payload, LineupPayload):
        return
    
    state = await session_cache.get_user_state(user.id)
    if not state:
        await message.answer("⚠️ Сессия истекла. Начните заново.")
        return
    
    selected = state.get("selected_players", [])
    page = state.get("lineup_page", 0)
    formation = state.get("formation")
    
    team = await match_service.get_user_team(user.id)
    
    if payload.lineup_action == "select":
        player_id = payload.player_id
        
        if player_id in selected:
            selected.remove(player_id)
        else:
            if len(selected) < 11:
                selected.append(player_id)
            else:
                await message.answer("⚠️ Уже выбрано 11 игроков!")
                return
        
        state["selected_players"] = selected
        await session_cache.set_user_state(user.id, state)
        
        await message.answer(
            f"📋 Формация: {formation}\n"
            f"Выбрано: {len(selected)}/11\n\n"
            "Выберите игроков:",
            keyboard=VKKeyboards.lineup_select(
                team.players,
                [UUID(pid) for pid in selected],
                page=page
            )
        )
    
    elif payload.lineup_action == "prev_page":
        state["lineup_page"] = max(0, page - 1)
        await session_cache.set_user_state(user.id, state)
        
        await message.answer(
            f"📋 Формация: {formation}\n"
            f"Выбрано: {len(selected)}/11\n\n"
            "Выберите игроков:",
            keyboard=VKKeyboards.lineup_select(
                team.players,
                [UUID(pid) for pid in selected],
                page=state["lineup_page"]
            )
        )
    
    elif payload.lineup_action == "next_page":
        state["lineup_page"] = page + 1
        await session_cache.set_user_state(user.id, state)
        
        await message.answer(
            f"📋 Формация: {formation}\n"
            f"Выбрано: {len(selected)}/11\n\n"
            "Выберите игроков:",
            keyboard=VKKeyboards.lineup_select(
                team.players,
                [UUID(pid) for pid in selected],
                page=state["lineup_page"]
            )
        )
    
    elif payload.lineup_action == "confirm":
        if len(selected) != 11:
            await message.answer(f"⚠️ Выберите 11 игроков! Сейчас: {len(selected)}")
            return
        
        match_id = await session_cache.get_active_match(user.id)
        
        try:
            match = await match_service.set_lineup(
                match_id,
                user.id,
                formation,
                [UUID(pid) for pid in selected]
            )
            
            renderer = VKMatchRenderer()
            
            if match.status == MatchStatus.IN_PROGRESS:
                goalkeeper = match.get_team(user.id).get_goalkeeper()
                
                await message.answer(
                    f"{renderer.render_match_status(match, user)}\n\n"
                    "⚽ Матч начался!\n"
                    f"Сделайте ставку на вратаря {goalkeeper.name}:",
                    keyboard=VKKeyboards.bet_type_select(
                        goalkeeper,
                        [BetType.EVEN_ODD]
                    )
                )
            else:
                await message.answer(
                    "✅ Состав подтверждён!\n\n"
                    "Ожидаем, пока соперник выберет состав..."
                )
        
        except ValueError as e:
            await message.answer(f"⚠️ Ошибка: {e}")
```

---

## 6. Renderer (VK-specific)

```python
# src/platforms/vk/renderers/match_renderer.py

from typing import Optional, List
from src.core.models.match import Match, MatchStatus, MatchPhase
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetOutcome
from src.core.models.whistle_card import WhistleCard, CardType
from src.core.models.user import User

class VKMatchRenderer:
    """Рендеринг сообщений для VK (plain text, no HTML)"""
    
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
        
        lines = [f"{emoji} Матч: {text}"]
        
        if match.status in [MatchStatus.IN_PROGRESS, MatchStatus.EXTRA_TIME,
                           MatchStatus.PENALTIES, MatchStatus.FINISHED]:
            lines.append(f"📊 Счёт: {match.score.manager1_goals} : {match.score.manager2_goals}")
        
        if match.current_turn and match.status == MatchStatus.IN_PROGRESS:
            is_my_turn = match.is_manager_turn(user.id)
            turn_text = "🟢 Ваш ход" if is_my_turn else "🔴 Ход соперника"
            lines.append(f"Ход #{match.current_turn.turn_number} | {turn_text}")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_team_stats(team: Team, is_own: bool = True) -> str:
        """Статистика команды"""
        team.calculate_stats()
        
        header = "📊 Ваша команда" if is_own else "📊 Команда соперника"
        
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
    def render_turn_summary(
        match: Match,
        dice_value: int,
        won_bets: List[Bet],
        card: Optional[WhistleCard]
    ) -> str:
        """Итог хода"""
        lines = [f"🎲 Выпало: {dice_value}", ""]
        
        if won_bets:
            lines.append("✅ Выигравшие ставки:")
            for bet in won_bets:
                bet_desc = {
                    "even_odd": "Чёт/Нечёт",
                    "high_low": "Больше/Меньше",
                    "exact_number": f"Число {bet.exact_number}"
                }
                lines.append(f"  • {bet_desc.get(bet.bet_type.value, bet.bet_type.value)}")
        else:
            lines.append("❌ Нет выигравших ставок")
        
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
            lines.append("")
            lines.append(f"🃏 Карточка: {card_names.get(card.card_type, card.card_type.value)}")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_match_result(match: Match, user_id) -> str:
        """Результат матча"""
        is_winner = match.result.winner_id == user_id
        
        if is_winner:
            header = "🎉 ПОБЕДА! 🎉"
        else:
            header = "😔 Поражение"
        
        decided_text = {
            MatchPhase.MAIN_TIME: "основное время",
            MatchPhase.EXTRA_TIME: "дополнительное время",
            MatchPhase.PENALTIES: "серия пенальти"
        }
        
        lines = [
            header,
            "",
            f"📊 Итоговый счёт: {match.score.manager1_goals} : {match.score.manager2_goals}",
            f"⏱ Решено в: {decided_text.get(match.result.decided_by, '?')}",
        ]
        
        if match.result.decided_by_lottery:
            lines.append("🎰 Победитель определён жребием")
        
        return "\n".join(lines)
```

---

## 7. Middleware

```python
# src/platforms/vk/middlewares/auth.py

from vkbottle import BaseMiddleware
from vkbottle.bot import Message
from uuid import uuid4
from datetime import datetime

from src.infrastructure.db.database import Database
from src.infrastructure.repositories.user_repository import UserRepository
from src.core.models.user import User, PlatformIds

class AuthMiddleware(BaseMiddleware[Message]):
    """Middleware для авторизации VK пользователей"""
    
    def __init__(self, database: Database):
        self.database = database
    
    async def pre(self):
        vk_id = self.event.from_id
        
        # Получаем информацию о пользователе из VK API
        users_info = await self.event.ctx_api.users.get(user_ids=[vk_id])
        vk_user = users_info[0] if users_info else None
        
        username = f"{vk_user.first_name} {vk_user.last_name}" if vk_user else f"VK User {vk_id}"
        
        async with self.database.session() as session:
            repo = UserRepository(session)
            user = await repo.get_by_vk_id(vk_id)
            
            if not user:
                user = User(
                    id=uuid4(),
                    username=username,
                    platform_ids=PlatformIds(vk_id=vk_id),
                    created_at=datetime.utcnow(),
                    last_active_at=datetime.utcnow()
                )
                user = await repo.create(user)
            else:
                user.last_active_at = datetime.utcnow()
                user = await repo.update(user)
        
        self.send({"user": user})
```
