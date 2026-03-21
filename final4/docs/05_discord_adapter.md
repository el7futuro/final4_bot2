# Модуль: Discord Adapter

## Обзор

Адаптер для платформы Discord. Использует discord.py для асинхронной обработки.
Discord использует slash commands и Views (кнопки/select menus).

---

## 1. Структура модуля

```
src/platforms/discord/
├── __init__.py
├── bot.py                  # Инициализация бота
├── cogs/
│   ├── __init__.py
│   ├── general.py          # Общие команды
│   ├── match.py            # Команды матча
│   ├── game.py             # Игровой процесс
│   └── profile.py          # Профиль
├── views/
│   ├── __init__.py
│   ├── menu_views.py       # Меню views
│   ├── match_views.py      # Match views
│   ├── bet_views.py        # Betting views
│   └── game_views.py       # Game views
├── embeds/
│   ├── __init__.py
│   └── match_embeds.py     # Discord Embeds
└── utils/
    ├── __init__.py
    └── auth.py             # Авторизация
```

---

## 2. Bot Initialization

```python
# src/platforms/discord/bot.py

import discord
from discord import app_commands
from discord.ext import commands

from src.infrastructure.db.database import Database
from src.infrastructure.cache.redis_client import RedisClient
from src.application.services.match_service import MatchService
from src.application.services.user_service import UserService

from .cogs import general, match, game, profile

class Final4Bot(commands.Bot):
    """Discord бот Final 4"""
    
    def __init__(
        self,
        token: str,
        database: Database,
        redis: RedisClient
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            description="Final 4 - Пошаговая футбольная стратегия"
        )
        
        self.token = token
        self.database = database
        self.redis = redis
        
        # Services
        self.user_service = UserService()
        self.match_service = MatchService()
    
    async def setup_hook(self) -> None:
        """Вызывается при запуске бота"""
        # Load cogs
        await self.add_cog(general.GeneralCog(self))
        await self.add_cog(match.MatchCog(self))
        await self.add_cog(game.GameCog(self))
        await self.add_cog(profile.ProfileCog(self))
        
        # Sync slash commands
        await self.tree.sync()
    
    async def on_ready(self) -> None:
        """Бот готов"""
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print(f"Connected to {len(self.guilds)} guilds")
        
        # Set presence
        await self.change_presence(
            activity=discord.Game(name="/play | Final 4")
        )
    
    def run_bot(self) -> None:
        """Запуск бота"""
        self.run(self.token)
```

---

## 3. Discord Embeds

```python
# src/platforms/discord/embeds/match_embeds.py

import discord
from typing import Optional, List
from src.core.models.match import Match, MatchStatus, MatchPhase
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetOutcome
from src.core.models.whistle_card import WhistleCard, CardType
from src.core.models.user import User

class MatchEmbeds:
    """Фабрика Discord Embeds для матча"""
    
    COLORS = {
        "primary": discord.Color.blue(),
        "success": discord.Color.green(),
        "warning": discord.Color.yellow(),
        "danger": discord.Color.red(),
        "info": discord.Color.blurple(),
    }
    
    @staticmethod
    def main_menu(user: User) -> discord.Embed:
        """Главное меню"""
        embed = discord.Embed(
            title="⚽ Final 4",
            description=(
                f"Добро пожаловать, **{user.username}**!\n\n"
                "Пошаговая футбольная стратегия с элементами настольной игры."
            ),
            color=MatchEmbeds.COLORS["primary"]
        )
        
        embed.add_field(
            name="📊 Ваша статистика",
            value=(
                f"Рейтинг: **{user.rating}**\n"
                f"Побед: **{user.stats.matches_won}**\n"
                f"Матчей: **{user.stats.matches_played}**"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🔥 Серия",
            value=(
                f"Текущая: **{user.stats.win_streak}**\n"
                f"Лучшая: **{user.stats.best_win_streak}**"
            ),
            inline=True
        )
        
        embed.set_footer(text="Выберите действие ниже")
        
        return embed
    
    @staticmethod
    def match_status(match: Match, user: User) -> discord.Embed:
        """Статус матча"""
        status_info = {
            MatchStatus.WAITING_FOR_OPPONENT: ("⏳ Ожидание соперника", MatchEmbeds.COLORS["warning"]),
            MatchStatus.SETTING_LINEUP: ("📋 Выбор состава", MatchEmbeds.COLORS["info"]),
            MatchStatus.IN_PROGRESS: ("⚽ Матч идёт", MatchEmbeds.COLORS["success"]),
            MatchStatus.EXTRA_TIME: ("⏰ Дополнительное время", MatchEmbeds.COLORS["warning"]),
            MatchStatus.PENALTIES: ("🥅 Серия пенальти", MatchEmbeds.COLORS["danger"]),
            MatchStatus.FINISHED: ("🏁 Матч завершён", MatchEmbeds.COLORS["primary"]),
            MatchStatus.CANCELLED: ("❌ Матч отменён", MatchEmbeds.COLORS["danger"]),
        }
        
        title, color = status_info.get(match.status, ("❓ Неизвестно", MatchEmbeds.COLORS["info"]))
        
        embed = discord.Embed(title=title, color=color)
        
        # Счёт
        if match.status in [MatchStatus.IN_PROGRESS, MatchStatus.EXTRA_TIME,
                           MatchStatus.PENALTIES, MatchStatus.FINISHED]:
            embed.add_field(
                name="📊 Счёт",
                value=f"**{match.score.manager1_goals}** : **{match.score.manager2_goals}**",
                inline=False
            )
        
        # Чей ход
        if match.current_turn and match.status == MatchStatus.IN_PROGRESS:
            is_my_turn = match.is_manager_turn(user.id)
            turn_emoji = "🟢" if is_my_turn else "🔴"
            turn_text = "Ваш ход" if is_my_turn else "Ход соперника"
            
            embed.add_field(
                name="🎯 Ход",
                value=f"{turn_emoji} **{turn_text}** (#{match.current_turn.turn_number})",
                inline=False
            )
        
        return embed
    
    @staticmethod
    def team_stats(team: Team, is_own: bool = True) -> discord.Embed:
        """Статистика команды"""
        team.calculate_stats()
        
        title = "📊 Ваша команда" if is_own else "📊 Команда соперника"
        color = MatchEmbeds.COLORS["success"] if is_own else MatchEmbeds.COLORS["danger"]
        
        embed = discord.Embed(title=title, color=color)
        
        embed.add_field(
            name="Формация",
            value=team.formation.value if team.formation else "Не выбрана",
            inline=True
        )
        
        embed.add_field(
            name="⛔ Отбития",
            value=str(team.stats.total_saves),
            inline=True
        )
        
        embed.add_field(
            name="↗️ Передачи",
            value=str(team.stats.total_passes),
            inline=True
        )
        
        embed.add_field(
            name="⚽ Голы",
            value=str(team.stats.total_goals),
            inline=True
        )
        
        return embed
    
    @staticmethod
    def field_players(team: Team) -> discord.Embed:
        """Игроки на поле"""
        embed = discord.Embed(
            title="🏟 Игроки на поле",
            color=MatchEmbeds.COLORS["info"]
        )
        
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
                player_lines = []
                for p in players:
                    status = "❌" if not p.is_available else ""
                    stats = f"[О:{p.stats.saves} П:{p.stats.passes} Г:{p.stats.goals}]"
                    player_lines.append(f"#{p.number} {p.name} {stats} {status}")
                
                embed.add_field(
                    name=position_names[position],
                    value="\n".join(player_lines),
                    inline=False
                )
        
        return embed
    
    @staticmethod
    def turn_summary(
        dice_value: int,
        won_bets: List[Bet],
        card: Optional[WhistleCard]
    ) -> discord.Embed:
        """Итог хода"""
        embed = discord.Embed(
            title=f"🎲 Выпало: {dice_value}",
            color=MatchEmbeds.COLORS["primary"]
        )
        
        if won_bets:
            bet_lines = []
            for bet in won_bets:
                bet_desc = {
                    "even_odd": "✅ Чёт/Нечёт → Отбития",
                    "high_low": "✅ Больше/Меньше → Передачи",
                    "exact_number": f"✅ Число {bet.exact_number} → Гол!"
                }
                bet_lines.append(bet_desc.get(bet.bet_type.value, bet.bet_type.value))
            
            embed.add_field(
                name="🎯 Выигравшие ставки",
                value="\n".join(bet_lines),
                inline=False
            )
        else:
            embed.add_field(
                name="❌ Результат",
                value="Нет выигравших ставок",
                inline=False
            )
        
        if card:
            card_info = {
                CardType.HAT_TRICK: ("🎩 Хэт-трик!", "+3 гола"),
                CardType.DOUBLE: ("✌️ Дубль!", "+2 гола"),
                CardType.GOAL: ("⚽ Гол!", "+1 гол"),
                CardType.OWN_GOAL: ("😱 Автогол!", "Соперник +1 гол"),
                CardType.VAR: ("📺 ВАР", "Отмена карточки соперника"),
                CardType.OFFSIDE: ("🚩 Офсайд", "Отмена гола соперника"),
                CardType.PENALTY: ("🥅 Пенальти", "Дополнительный бросок"),
                CardType.RED_CARD: ("🟥 Удаление", "Игрок теряет все действия"),
                CardType.YELLOW_CARD: ("🟨 Предупреждение", "-1 действие"),
                CardType.FOUL: ("⚠️ Фол", "-1 отбитие"),
                CardType.LOSS: ("💨 Потеря", "-1 передача"),
                CardType.INTERCEPTION: ("🦅 Перехват", "+1 передача"),
                CardType.TACKLE: ("🦵 Отбор", "+1 отбитие"),
            }
            
            name, effect = card_info.get(card.card_type, (card.card_type.value, ""))
            
            embed.add_field(
                name=f"🃏 Карточка: {name}",
                value=effect,
                inline=False
            )
        
        return embed
    
    @staticmethod
    def match_result(match: Match, user_id) -> discord.Embed:
        """Результат матча"""
        is_winner = match.result.winner_id == user_id
        
        if is_winner:
            embed = discord.Embed(
                title="🎉 ПОБЕДА! 🎉",
                color=MatchEmbeds.COLORS["success"]
            )
        else:
            embed = discord.Embed(
                title="😔 Поражение",
                color=MatchEmbeds.COLORS["danger"]
            )
        
        embed.add_field(
            name="📊 Итоговый счёт",
            value=f"**{match.score.manager1_goals}** : **{match.score.manager2_goals}**",
            inline=True
        )
        
        decided_text = {
            MatchPhase.MAIN_TIME: "Основное время",
            MatchPhase.EXTRA_TIME: "Дополнительное время",
            MatchPhase.PENALTIES: "Серия пенальти"
        }
        
        embed.add_field(
            name="⏱ Решено",
            value=decided_text.get(match.result.decided_by, "?"),
            inline=True
        )
        
        if match.result.decided_by_lottery:
            embed.set_footer(text="🎰 Победитель определён жребием")
        
        return embed
    
    @staticmethod
    def player_for_bet(player: Player, available_bets: List) -> discord.Embed:
        """Информация об игроке для ставки"""
        position_names = {
            Position.GOALKEEPER: "🧤 Вратарь",
            Position.DEFENDER: "🛡 Защитник",
            Position.MIDFIELDER: "🏃 Полузащитник",
            Position.FORWARD: "⚡ Форвард"
        }
        
        embed = discord.Embed(
            title=f"#{player.number} {player.name}",
            description=position_names.get(player.position, "?"),
            color=MatchEmbeds.COLORS["info"]
        )
        
        embed.add_field(
            name="Текущие действия",
            value=(
                f"⛔ Отбития: **{player.stats.saves}**\n"
                f"↗️ Передачи: **{player.stats.passes}**\n"
                f"⚽ Голы: **{player.stats.goals}**"
            ),
            inline=False
        )
        
        embed.set_footer(text="Выберите тип ставки ниже")
        
        return embed
```

---

## 4. Discord Views

```python
# src/platforms/discord/views/menu_views.py

import discord
from discord.ui import View, Button, Select
from typing import Optional

from src.core.models.user import User

class MainMenuView(View):
    """Главное меню"""
    
    def __init__(self, user: User, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.user = user
    
    @discord.ui.button(label="⚽ Играть", style=discord.ButtonStyle.success, row=0)
    async def play_button(self, interaction: discord.Interaction, button: Button):
        """Кнопка играть"""
        view = PlayMenuView(self.user)
        await interaction.response.edit_message(
            content="Выберите режим игры:",
            embed=None,
            view=view
        )
    
    @discord.ui.button(label="👤 Профиль", style=discord.ButtonStyle.primary, row=1)
    async def profile_button(self, interaction: discord.Interaction, button: Button):
        """Кнопка профиль"""
        from ..embeds.match_embeds import MatchEmbeds
        embed = discord.Embed(
            title=f"👤 {self.user.username}",
            color=discord.Color.blue()
        )
        embed.add_field(name="📊 Рейтинг", value=str(self.user.rating), inline=True)
        embed.add_field(name="🎮 Матчей", value=str(self.user.stats.matches_played), inline=True)
        embed.add_field(name="🏆 Побед", value=str(self.user.stats.matches_won), inline=True)
        embed.add_field(name="💔 Поражений", value=str(self.user.stats.matches_lost), inline=True)
        embed.add_field(name="🔥 Серия", value=str(self.user.stats.win_streak), inline=True)
        embed.add_field(name="⭐ Лучшая", value=str(self.user.stats.best_win_streak), inline=True)
        
        await interaction.response.edit_message(embed=embed, view=BackToMenuView(self.user))
    
    @discord.ui.button(label="🏆 Рейтинг", style=discord.ButtonStyle.primary, row=1)
    async def leaderboard_button(self, interaction: discord.Interaction, button: Button):
        """Кнопка рейтинг"""
        await interaction.response.send_message("🏆 Таблица лидеров (скоро)", ephemeral=True)

class PlayMenuView(View):
    """Меню выбора игры"""
    
    def __init__(self, user: User, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.user = user
    
    @discord.ui.button(label="🎲 Случайный соперник", style=discord.ButtonStyle.success)
    async def random_match(self, interaction: discord.Interaction, button: Button):
        """Поиск случайного соперника"""
        # Будет обработано в cog
        await interaction.response.defer()
        # Emit custom event
        interaction.client.dispatch("match_create", interaction, self.user, "random")
    
    @discord.ui.button(label="🤖 Против бота", style=discord.ButtonStyle.primary)
    async def bot_match(self, interaction: discord.Interaction, button: Button):
        """Игра против бота"""
        await interaction.response.defer()
        interaction.client.dispatch("match_create", interaction, self.user, "vs_bot")
    
    @discord.ui.button(label="🔙 Назад", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        """Назад"""
        from ..embeds.match_embeds import MatchEmbeds
        embed = MatchEmbeds.main_menu(self.user)
        await interaction.response.edit_message(embed=embed, view=MainMenuView(self.user))

class BackToMenuView(View):
    """Кнопка назад в меню"""
    
    def __init__(self, user: User, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.user = user
    
    @discord.ui.button(label="🔙 В меню", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        from ..embeds.match_embeds import MatchEmbeds
        embed = MatchEmbeds.main_menu(self.user)
        await interaction.response.edit_message(embed=embed, view=MainMenuView(self.user))
```

```python
# src/platforms/discord/views/match_views.py

import discord
from discord.ui import View, Button, Select
from typing import List, Optional
from uuid import UUID

from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.models.user import User

class FormationSelectView(View):
    """Выбор формации"""
    
    def __init__(self, user: User, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.user = user
        self.add_formation_select()
    
    def add_formation_select(self):
        options = [
            discord.SelectOption(label="1-5-3-2", description="5 защ, 3 полуз, 2 форв"),
            discord.SelectOption(label="1-5-2-3", description="5 защ, 2 полуз, 3 форв"),
            discord.SelectOption(label="1-4-4-2", description="4 защ, 4 полуз, 2 форв"),
            discord.SelectOption(label="1-4-3-3", description="4 защ, 3 полуз, 3 форв"),
            discord.SelectOption(label="1-3-5-2", description="3 защ, 5 полуз, 2 форв"),
            discord.SelectOption(label="1-3-4-3", description="3 защ, 4 полуз, 3 форв"),
            discord.SelectOption(label="1-3-3-4", description="3 защ, 3 полуз, 4 форв"),
        ]
        
        select = Select(
            placeholder="Выберите формацию...",
            options=options,
            custom_id="formation_select"
        )
        select.callback = self.formation_callback
        self.add_item(select)
    
    async def formation_callback(self, interaction: discord.Interaction):
        formation = interaction.data["values"][0]
        await interaction.response.defer()
        interaction.client.dispatch("formation_selected", interaction, self.user, formation)

class LineupSelectView(View):
    """Выбор состава"""
    
    def __init__(
        self,
        user: User,
        players: List[Player],
        selected_ids: List[UUID],
        formation: str,
        timeout: float = 600.0
    ):
        super().__init__(timeout=timeout)
        self.user = user
        self.players = players
        self.selected_ids = selected_ids
        self.formation = formation
        self.add_position_selects()
        self.add_confirm_button()
    
    def add_position_selects(self):
        """Добавить select для каждой позиции"""
        position_map = {
            Position.GOALKEEPER: "🧤 Вратарь",
            Position.DEFENDER: "🛡 Защитники",
            Position.MIDFIELDER: "🏃 Полузащитники",
            Position.FORWARD: "⚡ Форварды"
        }
        
        for position, label in position_map.items():
            position_players = [p for p in self.players if p.position == position]
            
            if not position_players:
                continue
            
            options = []
            for player in position_players[:25]:  # Discord limit
                is_selected = player.id in self.selected_ids
                options.append(discord.SelectOption(
                    label=f"#{player.number} {player.name}",
                    value=str(player.id),
                    default=is_selected,
                    emoji="✅" if is_selected else "⬜"
                ))
            
            max_values = len(position_players)
            if position == Position.GOALKEEPER:
                max_values = 1
            
            select = Select(
                placeholder=label,
                options=options,
                min_values=0,
                max_values=max_values,
                custom_id=f"lineup_{position.value}"
            )
            select.callback = self.create_select_callback(position)
            self.add_item(select)
    
    def create_select_callback(self, position: Position):
        async def callback(interaction: discord.Interaction):
            selected_values = interaction.data.get("values", [])
            
            # Убираем старые выборы этой позиции
            position_players = [p for p in self.players if p.position == position]
            for p in position_players:
                if p.id in self.selected_ids:
                    self.selected_ids.remove(p.id)
            
            # Добавляем новые
            for value in selected_values:
                self.selected_ids.append(UUID(value))
            
            await interaction.response.edit_message(
                content=f"📋 Формация: **{self.formation}**\nВыбрано: **{len(self.selected_ids)}/11**",
                view=self
            )
        
        return callback
    
    def add_confirm_button(self):
        button = Button(
            label="✅ Подтвердить состав",
            style=discord.ButtonStyle.success,
            custom_id="confirm_lineup",
            row=4
        )
        button.callback = self.confirm_callback
        self.add_item(button)
    
    async def confirm_callback(self, interaction: discord.Interaction):
        if len(self.selected_ids) != 11:
            await interaction.response.send_message(
                f"⚠️ Выберите 11 игроков! Сейчас: {len(self.selected_ids)}",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        interaction.client.dispatch(
            "lineup_confirmed",
            interaction,
            self.user,
            self.formation,
            self.selected_ids
        )
```

```python
# src/platforms/discord/views/bet_views.py

import discord
from discord.ui import View, Button, Select
from typing import List
from uuid import UUID

from src.core.models.player import Player
from src.core.models.bet import BetType
from src.core.models.user import User

class BetTypeView(View):
    """Выбор типа ставки"""
    
    def __init__(
        self,
        user: User,
        player: Player,
        available_types: List[BetType],
        timeout: float = 120.0
    ):
        super().__init__(timeout=timeout)
        self.user = user
        self.player = player
        self.add_bet_buttons(available_types)
    
    def add_bet_buttons(self, available_types: List[BetType]):
        type_info = {
            BetType.EVEN_ODD: ("🎯 Чёт/Нечёт", discord.ButtonStyle.primary),
            BetType.HIGH_LOW: ("↕️ Больше/Меньше", discord.ButtonStyle.primary),
            BetType.EXACT_NUMBER: ("🎱 Точное число", discord.ButtonStyle.success),
        }
        
        for bet_type in available_types:
            label, style = type_info.get(bet_type, (bet_type.value, discord.ButtonStyle.secondary))
            
            button = Button(
                label=label,
                style=style,
                custom_id=f"bet_type_{bet_type.value}"
            )
            button.callback = self.create_callback(bet_type)
            self.add_item(button)
    
    def create_callback(self, bet_type: BetType):
        async def callback(interaction: discord.Interaction):
            if bet_type == BetType.EVEN_ODD:
                view = EvenOddView(self.user, self.player)
            elif bet_type == BetType.HIGH_LOW:
                view = HighLowView(self.user, self.player)
            elif bet_type == BetType.EXACT_NUMBER:
                view = ExactNumberView(self.user, self.player)
            else:
                return
            
            await interaction.response.edit_message(
                content=f"Ставка на **{self.player.name}** ({bet_type.value}):",
                view=view
            )
        
        return callback

class EvenOddView(View):
    """Выбор чёт/нечёт"""
    
    def __init__(self, user: User, player: Player, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.user = user
        self.player = player
    
    @discord.ui.button(label="Чётное (2, 4, 6)", style=discord.ButtonStyle.primary)
    async def even_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        interaction.client.dispatch(
            "bet_placed",
            interaction, self.user, self.player.id,
            "even_odd", "even"
        )
    
    @discord.ui.button(label="Нечётное (1, 3, 5)", style=discord.ButtonStyle.primary)
    async def odd_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        interaction.client.dispatch(
            "bet_placed",
            interaction, self.user, self.player.id,
            "even_odd", "odd"
        )

class HighLowView(View):
    """Выбор больше/меньше"""
    
    def __init__(self, user: User, player: Player, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.user = user
        self.player = player
    
    @discord.ui.button(label="Меньше (1-3)", style=discord.ButtonStyle.primary)
    async def low_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        interaction.client.dispatch(
            "bet_placed",
            interaction, self.user, self.player.id,
            "high_low", "low"
        )
    
    @discord.ui.button(label="Больше (4-6)", style=discord.ButtonStyle.primary)
    async def high_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        interaction.client.dispatch(
            "bet_placed",
            interaction, self.user, self.player.id,
            "high_low", "high"
        )

class ExactNumberView(View):
    """Выбор точного числа"""
    
    def __init__(self, user: User, player: Player, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.user = user
        self.player = player
        self.add_number_buttons()
    
    def add_number_buttons(self):
        for i in range(1, 7):
            button = Button(
                label=str(i),
                style=discord.ButtonStyle.success,
                custom_id=f"exact_{i}"
            )
            button.callback = self.create_callback(i)
            self.add_item(button)
    
    def create_callback(self, number: int):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()
            interaction.client.dispatch(
                "bet_placed",
                interaction, self.user, self.player.id,
                "exact_number", str(number)
            )
        
        return callback
```

```python
# src/platforms/discord/views/game_views.py

import discord
from discord.ui import View, Button, Select
from typing import List, Optional
from uuid import UUID

from src.core.models.player import Player
from src.core.models.whistle_card import WhistleCard, CardType
from src.core.models.user import User

class GameActionsView(View):
    """Игровые действия"""
    
    def __init__(
        self,
        user: User,
        can_roll: bool = True,
        can_draw_card: bool = False,
        can_end_turn: bool = False,
        timeout: float = 300.0
    ):
        super().__init__(timeout=timeout)
        self.user = user
        
        if can_roll:
            roll_btn = Button(
                label="🎲 Бросить кубик",
                style=discord.ButtonStyle.success,
                custom_id="roll_dice"
            )
            roll_btn.callback = self.roll_callback
            self.add_item(roll_btn)
        
        if can_draw_card:
            card_btn = Button(
                label="🃏 Взять карточку",
                style=discord.ButtonStyle.primary,
                custom_id="draw_card"
            )
            card_btn.callback = self.draw_card_callback
            self.add_item(card_btn)
        
        if can_end_turn:
            end_btn = Button(
                label="➡️ Завершить ход",
                style=discord.ButtonStyle.secondary,
                custom_id="end_turn"
            )
            end_btn.callback = self.end_turn_callback
            self.add_item(end_btn)
    
    async def roll_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        interaction.client.dispatch("dice_roll", interaction, self.user)
    
    async def draw_card_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        interaction.client.dispatch("card_draw", interaction, self.user)
    
    async def end_turn_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        interaction.client.dispatch("turn_end", interaction, self.user)

class CardTargetView(View):
    """Выбор цели для карточки"""
    
    def __init__(
        self,
        user: User,
        card: WhistleCard,
        targets: List[Player],
        timeout: float = 120.0
    ):
        super().__init__(timeout=timeout)
        self.user = user
        self.card = card
        
        options = []
        for player in targets[:25]:  # Discord limit
            stats = f"О:{player.stats.saves} П:{player.stats.passes} Г:{player.stats.goals}"
            options.append(discord.SelectOption(
                label=f"#{player.number} {player.name}",
                description=stats,
                value=str(player.id)
            ))
        
        select = Select(
            placeholder="Выберите игрока...",
            options=options,
            custom_id="card_target"
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        target_id = interaction.data["values"][0]
        await interaction.response.defer()
        interaction.client.dispatch(
            "card_apply",
            interaction, self.user, self.card.id, UUID(target_id)
        )
```

---

## 5. Cogs

```python
# src/platforms/discord/cogs/general.py

import discord
from discord import app_commands
from discord.ext import commands
from uuid import uuid4
from datetime import datetime

from src.core.models.user import User, PlatformIds
from src.infrastructure.repositories.user_repository import UserRepository

from ..embeds.match_embeds import MatchEmbeds
from ..views.menu_views import MainMenuView

class GeneralCog(commands.Cog):
    """Общие команды"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def get_or_create_user(self, discord_user: discord.User) -> User:
        """Получить или создать пользователя"""
        async with self.bot.database.session() as session:
            repo = UserRepository(session)
            user = await repo.get_by_discord_id(discord_user.id)
            
            if not user:
                user = User(
                    id=uuid4(),
                    username=discord_user.display_name,
                    platform_ids=PlatformIds(discord_id=discord_user.id),
                    created_at=datetime.utcnow(),
                    last_active_at=datetime.utcnow()
                )
                user = await repo.create(user)
            else:
                user.last_active_at = datetime.utcnow()
                user = await repo.update(user)
            
            return user
    
    @app_commands.command(name="play", description="Начать игру Final 4")
    async def play_command(self, interaction: discord.Interaction):
        """Slash command /play"""
        user = await self.get_or_create_user(interaction.user)
        
        embed = MatchEmbeds.main_menu(user)
        view = MainMenuView(user)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="profile", description="Посмотреть профиль")
    async def profile_command(self, interaction: discord.Interaction):
        """Slash command /profile"""
        user = await self.get_or_create_user(interaction.user)
        
        embed = discord.Embed(
            title=f"👤 {user.username}",
            color=discord.Color.blue()
        )
        embed.add_field(name="📊 Рейтинг", value=str(user.rating), inline=True)
        embed.add_field(name="🎮 Матчей", value=str(user.stats.matches_played), inline=True)
        embed.add_field(name="🏆 Побед", value=str(user.stats.matches_won), inline=True)
        embed.add_field(name="💔 Поражений", value=str(user.stats.matches_lost), inline=True)
        embed.add_field(name="🔥 Серия", value=str(user.stats.win_streak), inline=True)
        embed.add_field(name="⭐ Лучшая", value=str(user.stats.best_win_streak), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="help", description="Правила игры")
    async def help_command(self, interaction: discord.Interaction):
        """Slash command /help"""
        embed = discord.Embed(
            title="📖 Правила игры Final 4",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🎯 Цель",
            value="Победить соперника, набрав больше голов.",
            inline=False
        )
        
        embed.add_field(
            name="🎮 Как играть",
            value=(
                "1. Выберите формацию (расстановку)\n"
                "2. Выставите 11 игроков на поле\n"
                "3. На каждого игрока делайте ставки\n"
                "4. Бросайте кубик — угадали → действия\n"
                "5. Карточки «Свисток» добавляют случайность"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎲 Типы ставок",
            value=(
                "• **Чёт/Нечёт** → Отбития\n"
                "• **Больше/Меньше** → Передачи\n"
                "• **Точное число** → Гол"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(GeneralCog(bot))
```
