# Модуль: Core (Доменный слой)

## Обзор

Core содержит всю бизнес-логику игры без зависимостей от внешних фреймворков.
Импортирует только стандартную библиотеку Python + Pydantic.

---

## 1. Модели данных (Pydantic Schemas)

### 1.1 Player (Футболист)

```python
# src/core/models/player.py

from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field

class Position(str, Enum):
    GOALKEEPER = "goalkeeper"      # Вратарь
    DEFENDER = "defender"          # Защитник
    MIDFIELDER = "midfielder"      # Полузащитник
    FORWARD = "forward"            # Форвард

class PlayerStats(BaseModel):
    """Полезные действия футболиста в матче"""
    saves: int = Field(default=0, ge=0, description="Отбития")
    passes: int = Field(default=0, ge=0, description="Передачи")
    goals: int = Field(default=0, ge=0, description="Голы")

class Player(BaseModel):
    """Футболист в команде"""
    id: UUID
    name: str = Field(min_length=1, max_length=50)
    position: Position
    number: int = Field(ge=1, le=99)
    stats: PlayerStats = Field(default_factory=PlayerStats)
    is_on_field: bool = Field(default=False)
    is_available: bool = Field(default=True)  # Не удалён
    yellow_cards: int = Field(default=0, ge=0, le=2)

    def add_saves(self, count: int) -> None:
        """Добавить отбития"""
        self.stats.saves += count

    def add_passes(self, count: int) -> None:
        """Добавить передачи"""
        self.stats.passes += count

    def add_goals(self, count: int) -> None:
        """Добавить голы"""
        self.stats.goals += count

    def remove_action(self, action_type: str) -> bool:
        """Удалить одно действие. Возвращает True если успешно."""
        if action_type == "save" and self.stats.saves > 0:
            self.stats.saves -= 1
            return True
        elif action_type == "pass" and self.stats.passes > 0:
            self.stats.passes -= 1
            return True
        elif action_type == "goal" and self.stats.goals > 0:
            self.stats.goals -= 1
            return True
        return False

    def clear_stats(self) -> None:
        """Обнулить все действия (удаление)"""
        self.stats = PlayerStats()
        self.is_available = False
```

### 1.2 Team (Команда)

```python
# src/core/models/team.py

from enum import Enum
from uuid import UUID
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator

from .player import Player, Position

class Formation(str, Enum):
    """Допустимые расстановки"""
    F_5_3_2 = "1-5-3-2"
    F_5_2_3 = "1-5-2-3"
    F_4_4_2 = "1-4-4-2"
    F_4_3_3 = "1-4-3-3"
    F_3_5_2 = "1-3-5-2"
    F_3_4_3 = "1-3-4-3"
    F_3_3_4 = "1-3-3-4"

FORMATION_STRUCTURE = {
    Formation.F_5_3_2: {"goalkeeper": 1, "defender": 5, "midfielder": 3, "forward": 2},
    Formation.F_5_2_3: {"goalkeeper": 1, "defender": 5, "midfielder": 2, "forward": 3},
    Formation.F_4_4_2: {"goalkeeper": 1, "defender": 4, "midfielder": 4, "forward": 2},
    Formation.F_4_3_3: {"goalkeeper": 1, "defender": 4, "midfielder": 3, "forward": 3},
    Formation.F_3_5_2: {"goalkeeper": 1, "defender": 3, "midfielder": 5, "forward": 2},
    Formation.F_3_4_3: {"goalkeeper": 1, "defender": 3, "midfielder": 4, "forward": 3},
    Formation.F_3_3_4: {"goalkeeper": 1, "defender": 3, "midfielder": 3, "forward": 4},
}

class TeamStats(BaseModel):
    """Суммарная статистика команды"""
    total_saves: int = Field(default=0, ge=0)
    total_passes: int = Field(default=0, ge=0)
    total_goals: int = Field(default=0, ge=0)

class Team(BaseModel):
    """Команда менеджера"""
    id: UUID
    manager_id: UUID
    name: str = Field(min_length=1, max_length=100)
    players: List[Player] = Field(default_factory=list, max_length=16)
    formation: Optional[Formation] = None
    stats: TeamStats = Field(default_factory=TeamStats)

    @model_validator(mode='after')
    def validate_squad_size(self) -> 'Team':
        if len(self.players) > 16:
            raise ValueError("Максимум 16 футболистов в составе")
        return self

    def get_players_by_position(self, position: Position) -> List[Player]:
        """Получить игроков по позиции"""
        return [p for p in self.players if p.position == position]

    def get_field_players(self) -> List[Player]:
        """Получить игроков на поле"""
        return [p for p in self.players if p.is_on_field]

    def get_goalkeeper(self) -> Optional[Player]:
        """Получить вратаря на поле"""
        gks = [p for p in self.players if p.position == Position.GOALKEEPER and p.is_on_field]
        return gks[0] if gks else None

    def set_formation(self, formation: Formation) -> None:
        """Установить расстановку"""
        self.formation = formation

    def set_lineup(self, player_ids: List[UUID]) -> bool:
        """Выставить состав на поле. Возвращает True если валидно."""
        if not self.formation:
            return False
        
        # Сначала снимаем всех с поля
        for p in self.players:
            p.is_on_field = False
        
        # Выставляем выбранных
        selected = [p for p in self.players if p.id in player_ids]
        if len(selected) != 11:
            return False
        
        # Проверяем соответствие формации
        structure = FORMATION_STRUCTURE[self.formation]
        for position, count in structure.items():
            pos_players = [p for p in selected if p.position.value == position]
            if len(pos_players) != count:
                return False
        
        for p in selected:
            p.is_on_field = True
        return True

    def calculate_stats(self) -> TeamStats:
        """Пересчитать суммарную статистику"""
        self.stats = TeamStats(
            total_saves=sum(p.stats.saves for p in self.players),
            total_passes=sum(p.stats.passes for p in self.players),
            total_goals=sum(p.stats.goals for p in self.players)
        )
        return self.stats
```

### 1.3 Bet (Ставка)

```python
# src/core/models/bet.py

from enum import Enum
from uuid import UUID
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator

class BetType(str, Enum):
    """Типы ставок"""
    EVEN_ODD = "even_odd"           # Чёт/нечет -> отбития
    HIGH_LOW = "high_low"           # Больше/меньше -> передачи
    EXACT_NUMBER = "exact_number"   # Точное число -> гол

class EvenOddChoice(str, Enum):
    EVEN = "even"   # Чётное (2, 4, 6)
    ODD = "odd"     # Нечётное (1, 3, 5)

class HighLowChoice(str, Enum):
    LOW = "low"     # 1-3 (Меньше)
    HIGH = "high"   # 4-6 (Больше)

class BetOutcome(str, Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"

class Bet(BaseModel):
    """Ставка менеджера на футболиста"""
    id: UUID
    match_id: UUID
    manager_id: UUID
    player_id: UUID
    turn_number: int = Field(ge=1)
    bet_type: BetType
    
    # Значение ставки зависит от типа
    even_odd_choice: Optional[EvenOddChoice] = None
    high_low_choice: Optional[HighLowChoice] = None
    exact_number: Optional[int] = Field(default=None, ge=1, le=6)
    
    dice_roll: Optional[int] = Field(default=None, ge=1, le=6)
    outcome: BetOutcome = Field(default=BetOutcome.PENDING)

    @model_validator(mode='after')
    def validate_bet_value(self) -> 'Bet':
        if self.bet_type == BetType.EVEN_ODD and self.even_odd_choice is None:
            raise ValueError("even_odd_choice обязателен для EVEN_ODD ставки")
        if self.bet_type == BetType.HIGH_LOW and self.high_low_choice is None:
            raise ValueError("high_low_choice обязателен для HIGH_LOW ставки")
        if self.bet_type == BetType.EXACT_NUMBER and self.exact_number is None:
            raise ValueError("exact_number обязателен для EXACT_NUMBER ставки")
        return self

    def resolve(self, dice_roll: int) -> BetOutcome:
        """Определить результат ставки по броску кубика"""
        self.dice_roll = dice_roll
        
        if self.bet_type == BetType.EVEN_ODD:
            is_even = dice_roll % 2 == 0
            won = (self.even_odd_choice == EvenOddChoice.EVEN and is_even) or \
                  (self.even_odd_choice == EvenOddChoice.ODD and not is_even)
        
        elif self.bet_type == BetType.HIGH_LOW:
            is_high = dice_roll >= 4
            won = (self.high_low_choice == HighLowChoice.HIGH and is_high) or \
                  (self.high_low_choice == HighLowChoice.LOW and not is_high)
        
        elif self.bet_type == BetType.EXACT_NUMBER:
            won = self.exact_number == dice_roll
        
        else:
            won = False
        
        self.outcome = BetOutcome.WON if won else BetOutcome.LOST
        return self.outcome

class PlayerBets(BaseModel):
    """Ставки на одного футболиста в ход"""
    player_id: UUID
    bets: List[Bet] = Field(default_factory=list, max_length=2)
    
    def add_bet(self, bet: Bet) -> bool:
        """Добавить ставку. Максимум 2 на игрока."""
        if len(self.bets) >= 2:
            return False
        self.bets.append(bet)
        return True
```

### 1.4 WhistleCard (Карточки "Свисток")

```python
# src/core/models/whistle_card.py

from enum import Enum
from uuid import UUID
from typing import Optional
from pydantic import BaseModel, Field

class CardType(str, Enum):
    """Типы карточек Свисток"""
    HAT_TRICK = "hat_trick"       # Хэт-трик: +3 гола
    DOUBLE = "double"             # Дубль: +2 гола
    GOAL = "goal"                 # Гол: +1 гол
    OWN_GOAL = "own_goal"         # Автогол: соперник +1 гол
    VAR = "var"                   # ВАР: отмена карточки соперника
    OFFSIDE = "offside"           # Офсайд: отмена гола соперника
    PENALTY = "penalty"           # Пенальти: доп. бросок
    RED_CARD = "red_card"         # Удаление: игрок теряет все действия
    YELLOW_CARD = "yellow_card"   # Предупреждение: -1 действие
    FOUL = "foul"                 # Фол: -1 отбитие
    LOSS = "loss"                 # Потеря: -1 передача
    INTERCEPTION = "interception" # Перехват: +1 передача
    TACKLE = "tackle"             # Отбор: +1 отбитие

# Количество карточек каждого типа в колоде
CARD_DISTRIBUTION = {
    CardType.HAT_TRICK: 1,
    CardType.DOUBLE: 1,
    CardType.GOAL: 2,
    CardType.OWN_GOAL: 1,
    CardType.VAR: 2,
    CardType.OFFSIDE: 2,
    CardType.PENALTY: 2,
    CardType.RED_CARD: 2,
    CardType.YELLOW_CARD: 3,
    CardType.FOUL: 6,
    CardType.LOSS: 6,
    CardType.INTERCEPTION: 6,
    CardType.TACKLE: 6,
}
# Итого: 40 карточек

class CardTarget(str, Enum):
    """Цель применения карточки"""
    SELF_PLAYER = "self_player"       # Свой игрок
    OPPONENT_PLAYER = "opponent_player" # Игрок соперника
    SELF_TEAM = "self_team"           # Своя команда
    OPPONENT_TEAM = "opponent_team"   # Команда соперника

class WhistleCard(BaseModel):
    """Карточка Свисток"""
    id: UUID
    card_type: CardType
    is_used: bool = Field(default=False)
    
    # Применение карточки
    applied_to_player_id: Optional[UUID] = None
    applied_by_manager_id: Optional[UUID] = None
    turn_applied: Optional[int] = None
    
    # Для VAR - какую карточку отменяет
    cancelled_card_id: Optional[UUID] = None

    def get_target_type(self) -> CardTarget:
        """Определить тип цели для карточки"""
        if self.card_type in [CardType.HAT_TRICK, CardType.DOUBLE, CardType.GOAL, 
                               CardType.INTERCEPTION, CardType.TACKLE]:
            return CardTarget.SELF_PLAYER
        elif self.card_type in [CardType.OWN_GOAL]:
            return CardTarget.OPPONENT_TEAM
        elif self.card_type in [CardType.OFFSIDE, CardType.RED_CARD, 
                                 CardType.YELLOW_CARD, CardType.FOUL, CardType.LOSS]:
            return CardTarget.OPPONENT_PLAYER
        elif self.card_type in [CardType.VAR]:
            return CardTarget.OPPONENT_TEAM  # Отменяет карточку соперника
        elif self.card_type in [CardType.PENALTY]:
            return CardTarget.SELF_PLAYER
        return CardTarget.SELF_PLAYER

class CardEffect(BaseModel):
    """Эффект применения карточки"""
    card_id: UUID
    card_type: CardType
    target_player_id: Optional[UUID] = None
    target_manager_id: Optional[UUID] = None
    
    goals_added: int = Field(default=0)
    goals_removed: int = Field(default=0)
    saves_added: int = Field(default=0)
    saves_removed: int = Field(default=0)
    passes_added: int = Field(default=0)
    passes_removed: int = Field(default=0)
    player_removed: bool = Field(default=False)
    card_cancelled_id: Optional[UUID] = None
    requires_penalty_roll: bool = Field(default=False)
```

### 1.5 Match (Матч)

```python
# src/core/models/match.py

from enum import Enum
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

from .team import Team
from .bet import Bet
from .whistle_card import WhistleCard

class MatchStatus(str, Enum):
    WAITING_FOR_OPPONENT = "waiting_for_opponent"
    SETTING_LINEUP = "setting_lineup"
    IN_PROGRESS = "in_progress"
    EXTRA_TIME = "extra_time"
    PENALTIES = "penalties"
    FINISHED = "finished"
    CANCELLED = "cancelled"

class MatchType(str, Enum):
    RANDOM = "random"           # Против случайного
    VS_BOT = "vs_bot"           # Против бота
    TOURNAMENT = "tournament"   # Турнир

class MatchPhase(str, Enum):
    MAIN_TIME = "main_time"
    EXTRA_TIME = "extra_time"
    PENALTIES = "penalties"

class TurnState(BaseModel):
    """Состояние текущего хода"""
    turn_number: int = Field(ge=1)
    current_manager_id: UUID
    player_being_bet_on: Optional[UUID] = None
    bets_placed: List[UUID] = Field(default_factory=list)  # ID ставок
    dice_rolled: bool = Field(default=False)
    dice_value: Optional[int] = Field(default=None, ge=1, le=6)
    card_drawn: bool = Field(default=False)
    card_id: Optional[UUID] = None
    card_applied: bool = Field(default=False)
    waiting_for_penalty_roll: bool = Field(default=False)

class MatchScore(BaseModel):
    """Счёт матча"""
    manager1_goals: int = Field(default=0, ge=0)
    manager2_goals: int = Field(default=0, ge=0)

class MatchResult(BaseModel):
    """Результат матча"""
    winner_id: Optional[UUID] = None  # None = ничья (не должно быть)
    loser_id: Optional[UUID] = None
    final_score: MatchScore
    decided_by: MatchPhase  # Когда определился победитель
    decided_by_lottery: bool = Field(default=False)  # Жребий

class Match(BaseModel):
    """Матч между двумя менеджерами"""
    id: UUID
    match_type: MatchType
    status: MatchStatus = Field(default=MatchStatus.WAITING_FOR_OPPONENT)
    phase: MatchPhase = Field(default=MatchPhase.MAIN_TIME)
    
    # Участники
    manager1_id: UUID
    manager2_id: Optional[UUID] = None  # None если ждём соперника
    team1: Optional[Team] = None
    team2: Optional[Team] = None
    
    # Ход игры
    current_turn: TurnState = None
    total_turns_main: int = Field(default=0)  # Сколько ходов сыграно в основное время
    total_turns_extra: int = Field(default=0)
    
    # Ставки и карточки
    bets: List[Bet] = Field(default_factory=list)
    whistle_cards_drawn: List[WhistleCard] = Field(default_factory=list)
    whistle_deck: List[WhistleCard] = Field(default_factory=list)  # Оставшиеся карточки
    
    # Результат
    score: MatchScore = Field(default_factory=MatchScore)
    result: Optional[MatchResult] = None
    
    # Метаданные
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    platform: str = Field(description="telegram/vk/discord/api")

    def is_manager_turn(self, manager_id: UUID) -> bool:
        """Проверить, ход ли этого менеджера"""
        return self.current_turn and self.current_turn.current_manager_id == manager_id

    def get_opponent_id(self, manager_id: UUID) -> Optional[UUID]:
        """Получить ID соперника"""
        if manager_id == self.manager1_id:
            return self.manager2_id
        elif manager_id == self.manager2_id:
            return self.manager1_id
        return None

    def get_team(self, manager_id: UUID) -> Optional[Team]:
        """Получить команду менеджера"""
        if manager_id == self.manager1_id:
            return self.team1
        elif manager_id == self.manager2_id:
            return self.team2
        return None

    def get_opponent_team(self, manager_id: UUID) -> Optional[Team]:
        """Получить команду соперника"""
        opponent_id = self.get_opponent_id(manager_id)
        return self.get_team(opponent_id) if opponent_id else None
```

### 1.6 User (Пользователь)

```python
# src/core/models/user.py

from enum import Enum
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel, Field

class UserPlan(str, Enum):
    FREE = "free"
    PREMIUM = "premium"
    PRO = "pro"

class PlatformIds(BaseModel):
    """ID пользователя на разных платформах"""
    telegram_id: Optional[int] = None
    vk_id: Optional[int] = None
    discord_id: Optional[int] = None

class UserStats(BaseModel):
    """Статистика пользователя"""
    matches_played: int = Field(default=0, ge=0)
    matches_won: int = Field(default=0, ge=0)
    matches_lost: int = Field(default=0, ge=0)
    matches_draw: int = Field(default=0, ge=0)  # До пенальти
    tournaments_won: int = Field(default=0, ge=0)
    goals_scored: int = Field(default=0, ge=0)
    goals_conceded: int = Field(default=0, ge=0)
    win_streak: int = Field(default=0, ge=0)
    best_win_streak: int = Field(default=0, ge=0)

class DailyLimits(BaseModel):
    """Дневные лимиты"""
    matches_today: int = Field(default=0, ge=0)
    last_match_date: Optional[datetime] = None

class User(BaseModel):
    """Пользователь системы"""
    id: UUID
    username: str = Field(min_length=1, max_length=50)
    platform_ids: PlatformIds = Field(default_factory=PlatformIds)
    
    plan: UserPlan = Field(default=UserPlan.FREE)
    plan_expires_at: Optional[datetime] = None
    
    stats: UserStats = Field(default_factory=UserStats)
    daily_limits: DailyLimits = Field(default_factory=DailyLimits)
    
    rating: int = Field(default=1000, ge=0)  # ELO-like rating
    
    created_at: datetime
    last_active_at: datetime
    is_banned: bool = Field(default=False)
    ban_reason: Optional[str] = None

    def can_play_match(self) -> bool:
        """Проверить, может ли играть (лимиты)"""
        if self.is_banned:
            return False
        
        if self.plan == UserPlan.FREE:
            # Бесплатно — 3 матча в день
            if self.daily_limits.matches_today >= 3:
                return False
        
        return True

    def increment_daily_matches(self) -> None:
        """Увеличить счётчик матчей за день"""
        self.daily_limits.matches_today += 1
        self.daily_limits.last_match_date = datetime.utcnow()

    def reset_daily_limits(self) -> None:
        """Сбросить дневные лимиты (вызывать в полночь)"""
        self.daily_limits.matches_today = 0
```

---

## 2. Игровой движок (Game Engine)

### 2.1 GameEngine

```python
# src/core/engine/game_engine.py

from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, List, Tuple
import random

from ..models.match import Match, MatchStatus, MatchType, MatchPhase, TurnState, MatchResult, MatchScore
from ..models.team import Team, Formation
from ..models.player import Player, Position
from ..models.bet import Bet, BetType, BetOutcome
from ..models.whistle_card import WhistleCard
from .bet_tracker import BetTracker
from .action_calculator import ActionCalculator
from .score_calculator import ScoreCalculator
from .whistle_deck import WhistleDeck

class GameEngine:
    """Главный игровой движок"""
    
    def __init__(self):
        self.bet_tracker = BetTracker()
        self.action_calculator = ActionCalculator()
        self.score_calculator = ScoreCalculator()
    
    def create_match(
        self,
        manager_id: UUID,
        match_type: MatchType,
        platform: str
    ) -> Match:
        """Создать новый матч"""
        match = Match(
            id=uuid4(),
            match_type=match_type,
            manager1_id=manager_id,
            created_at=datetime.utcnow(),
            platform=platform,
            whistle_deck=WhistleDeck.create_deck()
        )
        
        if match_type == MatchType.VS_BOT:
            match.manager2_id = UUID('00000000-0000-0000-0000-000000000001')  # Bot ID
            match.status = MatchStatus.SETTING_LINEUP
        
        return match
    
    def join_match(self, match: Match, manager_id: UUID) -> Match:
        """Присоединиться к матчу"""
        if match.status != MatchStatus.WAITING_FOR_OPPONENT:
            raise ValueError("Матч не ожидает соперника")
        if match.manager2_id is not None:
            raise ValueError("Матч уже имеет соперника")
        if match.manager1_id == manager_id:
            raise ValueError("Нельзя играть против себя")
        
        match.manager2_id = manager_id
        match.status = MatchStatus.SETTING_LINEUP
        return match
    
    def set_team_lineup(
        self,
        match: Match,
        manager_id: UUID,
        team: Team,
        formation: Formation,
        player_ids: List[UUID]
    ) -> Match:
        """Установить состав команды"""
        if match.status != MatchStatus.SETTING_LINEUP:
            raise ValueError("Нельзя менять состав в текущем статусе")
        
        team.set_formation(formation)
        if not team.set_lineup(player_ids):
            raise ValueError("Невалидный состав для формации")
        
        if manager_id == match.manager1_id:
            match.team1 = team
        elif manager_id == match.manager2_id:
            match.team2 = team
        else:
            raise ValueError("Менеджер не участвует в матче")
        
        # Проверяем, оба ли готовы
        if match.team1 and match.team2:
            match = self._start_match(match)
        
        return match
    
    def _start_match(self, match: Match) -> Match:
        """Начать матч"""
        match.status = MatchStatus.IN_PROGRESS
        match.started_at = datetime.utcnow()
        match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=match.manager1_id  # Создатель ходит первым
        )
        return match
    
    def place_bet(
        self,
        match: Match,
        manager_id: UUID,
        player_id: UUID,
        bet: Bet
    ) -> Tuple[Match, Bet]:
        """Разместить ставку"""
        if not match.is_manager_turn(manager_id):
            raise ValueError("Сейчас не ваш ход")
        
        team = match.get_team(manager_id)
        player = next((p for p in team.players if p.id == player_id), None)
        if not player or not player.is_on_field:
            raise ValueError("Игрок не на поле")
        
        # Валидация правил ставок
        self.bet_tracker.validate_bet(match, manager_id, player, bet)
        
        bet.id = uuid4()
        bet.match_id = match.id
        bet.manager_id = manager_id
        bet.player_id = player_id
        bet.turn_number = match.current_turn.turn_number
        
        match.bets.append(bet)
        match.current_turn.bets_placed.append(bet.id)
        
        return match, bet
    
    def roll_dice(self, match: Match, manager_id: UUID) -> Tuple[Match, int, List[Bet]]:
        """Бросить кубик и определить результаты ставок"""
        if not match.is_manager_turn(manager_id):
            raise ValueError("Сейчас не ваш ход")
        if match.current_turn.dice_rolled:
            raise ValueError("Кубик уже брошен в этот ход")
        
        # Бросок
        dice_value = random.randint(1, 6)
        match.current_turn.dice_rolled = True
        match.current_turn.dice_value = dice_value
        
        # Определяем результаты ставок этого хода
        turn_bets = [b for b in match.bets if b.id in match.current_turn.bets_placed]
        won_bets = []
        
        for bet in turn_bets:
            outcome = bet.resolve(dice_value)
            if outcome == BetOutcome.WON:
                won_bets.append(bet)
                # Начисляем действия
                team = match.get_team(manager_id)
                player = next(p for p in team.players if p.id == bet.player_id)
                self.action_calculator.apply_bet_result(player, bet)
        
        return match, dice_value, won_bets
    
    def draw_whistle_card(self, match: Match, manager_id: UUID) -> Tuple[Match, Optional[WhistleCard]]:
        """Взять карточку Свисток (если есть выигравшие ставки)"""
        if not match.is_manager_turn(manager_id):
            raise ValueError("Сейчас не ваш ход")
        if match.current_turn.card_drawn:
            raise ValueError("Карточка уже взята в этот ход")
        
        # Проверяем, есть ли выигравшие ставки
        turn_bets = [b for b in match.bets if b.id in match.current_turn.bets_placed]
        won_any = any(b.outcome == BetOutcome.WON for b in turn_bets)
        
        if not won_any:
            match.current_turn.card_drawn = True
            return match, None
        
        if not match.whistle_deck:
            match.current_turn.card_drawn = True
            return match, None
        
        card = match.whistle_deck.pop(0)
        card.applied_by_manager_id = manager_id
        card.turn_applied = match.current_turn.turn_number
        match.current_turn.card_drawn = True
        match.current_turn.card_id = card.id
        match.whistle_cards_drawn.append(card)
        
        return match, card
    
    def apply_whistle_card(
        self,
        match: Match,
        manager_id: UUID,
        card: WhistleCard,
        target_player_id: Optional[UUID] = None
    ) -> Match:
        """Применить карточку Свисток"""
        # Логика применения карточки - см. WhistleDeck
        effect = WhistleDeck.get_card_effect(card, match, manager_id, target_player_id)
        match = WhistleDeck.apply_effect(match, effect)
        
        card.is_used = True
        card.applied_to_player_id = target_player_id
        match.current_turn.card_applied = True
        
        return match
    
    def end_turn(self, match: Match, manager_id: UUID) -> Match:
        """Завершить ход и передать другому игроку"""
        if not match.is_manager_turn(manager_id):
            raise ValueError("Сейчас не ваш ход")
        
        # Пересчитываем статистику команд
        match.team1.calculate_stats()
        match.team2.calculate_stats()
        
        # Увеличиваем счётчик ходов
        if match.phase == MatchPhase.MAIN_TIME:
            match.total_turns_main += 1
        else:
            match.total_turns_extra += 1
        
        # Проверяем, закончился ли матч
        # В основное время: 11 ходов каждый (по числу игроков на поле)
        if match.phase == MatchPhase.MAIN_TIME and match.total_turns_main >= 22:
            return self._end_main_time(match)
        
        # Дополнительное время: 5 ходов каждый
        if match.phase == MatchPhase.EXTRA_TIME and match.total_turns_extra >= 10:
            return self._end_extra_time(match)
        
        # Передаём ход сопернику
        next_manager = match.get_opponent_id(manager_id)
        match.current_turn = TurnState(
            turn_number=match.current_turn.turn_number + 1,
            current_manager_id=next_manager
        )
        
        return match
    
    def _end_main_time(self, match: Match) -> Match:
        """Завершить основное время"""
        score = self.score_calculator.calculate_score(match.team1, match.team2)
        match.score = score
        
        if score.manager1_goals != score.manager2_goals:
            return self._finish_match(match, MatchPhase.MAIN_TIME)
        
        # Ничья — дополнительное время
        match.phase = MatchPhase.EXTRA_TIME
        match.status = MatchStatus.EXTRA_TIME
        match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=match.manager1_id
        )
        return match
    
    def _end_extra_time(self, match: Match) -> Match:
        """Завершить дополнительное время"""
        score = self.score_calculator.calculate_score(match.team1, match.team2)
        match.score = score
        
        if score.manager1_goals != score.manager2_goals:
            return self._finish_match(match, MatchPhase.EXTRA_TIME)
        
        # Всё ещё ничья — пенальти
        match.phase = MatchPhase.PENALTIES
        match.status = MatchStatus.PENALTIES
        return self._start_penalties(match)
    
    def _start_penalties(self, match: Match) -> Match:
        """Начать серию пенальти"""
        match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=match.manager1_id
        )
        return match
    
    def execute_penalty_kick(self, match: Match, manager_id: UUID, player_id: UUID) -> Tuple[Match, bool]:
        """Выполнить пенальти. Возвращает (match, забит ли гол)"""
        if match.phase != MatchPhase.PENALTIES:
            raise ValueError("Не фаза пенальти")
        
        team = match.get_team(manager_id)
        player = next(p for p in team.players if p.id == player_id)
        
        # Гол забивается если есть передача
        goal_scored = player.stats.passes > 0
        
        if goal_scored:
            if manager_id == match.manager1_id:
                match.score.manager1_goals += 1
            else:
                match.score.manager2_goals += 1
        
        return match, goal_scored
    
    def _finish_match(self, match: Match, decided_by: MatchPhase) -> Match:
        """Завершить матч с результатом"""
        match.status = MatchStatus.FINISHED
        match.finished_at = datetime.utcnow()
        
        if match.score.manager1_goals > match.score.manager2_goals:
            winner_id = match.manager1_id
            loser_id = match.manager2_id
        else:
            winner_id = match.manager2_id
            loser_id = match.manager1_id
        
        match.result = MatchResult(
            winner_id=winner_id,
            loser_id=loser_id,
            final_score=match.score,
            decided_by=decided_by
        )
        
        return match
    
    def finish_by_lottery(self, match: Match) -> Match:
        """Определить победителя жребием (после всех пенальти)"""
        winner_id = random.choice([match.manager1_id, match.manager2_id])
        loser_id = match.manager2_id if winner_id == match.manager1_id else match.manager1_id
        
        match.status = MatchStatus.FINISHED
        match.finished_at = datetime.utcnow()
        match.result = MatchResult(
            winner_id=winner_id,
            loser_id=loser_id,
            final_score=match.score,
            decided_by=MatchPhase.PENALTIES,
            decided_by_lottery=True
        )
        
        return match
```

### 2.2 BetTracker

```python
# src/core/engine/bet_tracker.py

from uuid import UUID
from typing import List, Dict
from collections import defaultdict

from ..models.match import Match
from ..models.player import Player, Position
from ..models.bet import Bet, BetType
from ..models.team import Formation, FORMATION_STRUCTURE

class BetTracker:
    """Отслеживание и валидация ставок"""
    
    def validate_bet(self, match: Match, manager_id: UUID, player: Player, bet: Bet) -> None:
        """Валидировать ставку согласно правилам"""
        
        # 1. Ставка на чёт/нечёт только для 6 игроков (не форварды)
        if bet.bet_type == BetType.EVEN_ODD:
            if player.position == Position.FORWARD:
                raise ValueError("Форварды не могут иметь ставку на чёт/нечёт")
            
            # Проверяем лимит 6 игроков
            even_odd_count = self._count_even_odd_bets(match, manager_id)
            if even_odd_count >= 6:
                raise ValueError("Максимум 6 ставок на чёт/нечёт")
        
        # 2. Ставка на вратаря — обязательно чёт/нечёт
        if player.position == Position.GOALKEEPER:
            if bet.bet_type != BetType.EVEN_ODD:
                raise ValueError("Вратарь может иметь только ставку на чёт/нечёт")
        
        # 3. Ставки на гол — лимиты по позициям
        if bet.bet_type == BetType.EXACT_NUMBER:
            self._validate_goal_bet(match, manager_id, player)
        
        # 4. Максимум 2 ставки на игрока
        player_bets = [b for b in match.bets 
                       if b.manager_id == manager_id 
                       and b.player_id == player.id
                       and b.turn_number == match.current_turn.turn_number]
        if len(player_bets) >= 2:
            raise ValueError("Максимум 2 ставки на игрока за ход")
    
    def _count_even_odd_bets(self, match: Match, manager_id: UUID) -> int:
        """Подсчитать количество ставок на чёт/нечёт у менеджера"""
        return len([b for b in match.bets 
                    if b.manager_id == manager_id 
                    and b.bet_type == BetType.EVEN_ODD])
    
    def _validate_goal_bet(self, match: Match, manager_id: UUID, player: Player) -> None:
        """Валидировать ставку на гол"""
        team = match.get_team(manager_id)
        goal_bets = [b for b in match.bets 
                     if b.manager_id == manager_id 
                     and b.bet_type == BetType.EXACT_NUMBER]
        
        # Подсчёт по позициям
        goal_bets_by_position: Dict[Position, int] = defaultdict(int)
        for bet in goal_bets:
            bet_player = next(p for p in team.players if p.id == bet.player_id)
            goal_bets_by_position[bet_player.position] += 1
        
        # Правила:
        # - Защитники: только 1 защитник может иметь ставку на гол
        # - Полузащитники: всего 3 ставки на гол
        # - Форварды: всего 4 ставки на гол
        
        if player.position == Position.DEFENDER:
            defenders_with_goals = set(
                b.player_id for b in goal_bets 
                if next(p for p in team.players if p.id == b.player_id).position == Position.DEFENDER
            )
            if player.id not in defenders_with_goals and len(defenders_with_goals) >= 1:
                raise ValueError("Только 1 защитник может иметь ставку на гол")
        
        elif player.position == Position.MIDFIELDER:
            if goal_bets_by_position[Position.MIDFIELDER] >= 3:
                raise ValueError("Максимум 3 ставки на гол для полузащитников")
        
        elif player.position == Position.FORWARD:
            if goal_bets_by_position[Position.FORWARD] >= 4:
                raise ValueError("Максимум 4 ставки на гол для форвардов")
        
        elif player.position == Position.GOALKEEPER:
            raise ValueError("Вратарь не может иметь ставку на гол")
    
    def get_available_bet_types(self, match: Match, manager_id: UUID, player: Player) -> List[BetType]:
        """Получить доступные типы ставок для игрока"""
        available = []
        
        # Чёт/нечёт
        if player.position != Position.FORWARD:
            even_odd_count = self._count_even_odd_bets(match, manager_id)
            if even_odd_count < 6:
                available.append(BetType.EVEN_ODD)
        
        # Больше/меньше — всегда доступно
        available.append(BetType.HIGH_LOW)
        
        # Точное число (гол)
        if player.position != Position.GOALKEEPER:
            try:
                self._validate_goal_bet(match, manager_id, player)
                available.append(BetType.EXACT_NUMBER)
            except ValueError:
                pass
        
        return available
```

### 2.3 ActionCalculator

```python
# src/core/engine/action_calculator.py

from ..models.player import Player, Position
from ..models.bet import Bet, BetType, BetOutcome

class ActionCalculator:
    """Расчёт полезных действий"""
    
    # Полезные действия при выигрыше ставки
    ACTIONS_BY_POSITION = {
        Position.GOALKEEPER: {"saves": 3, "passes": 0},
        Position.DEFENDER: {"saves": 2, "passes": 1},
        Position.MIDFIELDER: {"saves": 1, "passes": 2},
        Position.FORWARD: {"saves": 0, "passes": 1},
    }
    
    def apply_bet_result(self, player: Player, bet: Bet) -> None:
        """Применить результат выигранной ставки к игроку"""
        if bet.outcome != BetOutcome.WON:
            return
        
        if bet.bet_type == BetType.EVEN_ODD:
            # Чёт/нечёт -> отбития
            saves = self.ACTIONS_BY_POSITION[player.position]["saves"]
            player.add_saves(saves)
        
        elif bet.bet_type == BetType.HIGH_LOW:
            # Больше/меньше -> передачи
            passes = self.ACTIONS_BY_POSITION[player.position]["passes"]
            player.add_passes(passes)
        
        elif bet.bet_type == BetType.EXACT_NUMBER:
            # Точное число -> гол
            player.add_goals(1)
    
    def calculate_team_totals(self, players: list) -> dict:
        """Рассчитать суммы по команде"""
        return {
            "total_saves": sum(p.stats.saves for p in players),
            "total_passes": sum(p.stats.passes for p in players),
            "total_goals": sum(p.stats.goals for p in players),
        }
```

### 2.4 ScoreCalculator

```python
# src/core/engine/score_calculator.py

from ..models.team import Team
from ..models.match import MatchScore

class ScoreCalculator:
    """Расчёт итогового счёта матча"""
    
    def calculate_score(self, team1: Team, team2: Team) -> MatchScore:
        """
        Рассчитать итоговый счёт.
        
        Алгоритм:
        1. Берём отбития соперника, вычитаем свои передачи
        2. Если передач >= отбитий — все голы засчитываются
        3. Если отбитий больше — голы тратятся на уничтожение отбитий (1 гол = 2 отбития)
        4. Оставшиеся голы засчитываются
        """
        team1.calculate_stats()
        team2.calculate_stats()
        
        goals1 = self._calculate_goals_scored(
            own_passes=team1.stats.total_passes,
            own_goals=team1.stats.total_goals,
            opponent_saves=team2.stats.total_saves
        )
        
        goals2 = self._calculate_goals_scored(
            own_passes=team2.stats.total_passes,
            own_goals=team2.stats.total_goals,
            opponent_saves=team1.stats.total_saves
        )
        
        return MatchScore(manager1_goals=goals1, manager2_goals=goals2)
    
    def _calculate_goals_scored(
        self,
        own_passes: int,
        own_goals: int,
        opponent_saves: int
    ) -> int:
        """Рассчитать забитые голы для одной команды"""
        
        # Остаточные отбития после применения передач
        remaining_saves = opponent_saves - own_passes
        
        if remaining_saves <= 0:
            # Оборона взломана, все голы засчитываются
            return own_goals
        
        # Голы тратятся на уничтожение отбитий: 1 гол = 2 отбития
        goals_needed_to_clear = (remaining_saves + 1) // 2  # Округление вверх
        
        # Оставшиеся голы после уничтожения отбитий
        scored_goals = max(0, own_goals - goals_needed_to_clear)
        
        return scored_goals
```

### 2.5 WhistleDeck

```python
# src/core/engine/whistle_deck.py

from uuid import uuid4
from typing import List, Optional
import random

from ..models.whistle_card import (
    WhistleCard, CardType, CardEffect, CardTarget, CARD_DISTRIBUTION
)
from ..models.match import Match
from uuid import UUID

class WhistleDeck:
    """Колода карточек Свисток"""
    
    @staticmethod
    def create_deck() -> List[WhistleCard]:
        """Создать и перемешать колоду"""
        deck = []
        for card_type, count in CARD_DISTRIBUTION.items():
            for _ in range(count):
                deck.append(WhistleCard(id=uuid4(), card_type=card_type))
        random.shuffle(deck)
        return deck
    
    @staticmethod
    def get_card_effect(
        card: WhistleCard,
        match: Match,
        manager_id: UUID,
        target_player_id: Optional[UUID]
    ) -> CardEffect:
        """Определить эффект карточки"""
        effect = CardEffect(card_id=card.id, card_type=card.card_type)
        
        if card.card_type == CardType.HAT_TRICK:
            effect.target_player_id = target_player_id
            effect.goals_added = 3
        
        elif card.card_type == CardType.DOUBLE:
            effect.target_player_id = target_player_id
            effect.goals_added = 2
        
        elif card.card_type == CardType.GOAL:
            effect.target_player_id = target_player_id
            effect.goals_added = 1
        
        elif card.card_type == CardType.OWN_GOAL:
            effect.target_manager_id = match.get_opponent_id(manager_id)
            effect.goals_added = 1
        
        elif card.card_type == CardType.VAR:
            # Отменяет последнюю карточку соперника
            opponent_cards = [c for c in match.whistle_cards_drawn 
                            if c.applied_by_manager_id == match.get_opponent_id(manager_id)
                            and c.turn_applied == match.current_turn.turn_number
                            and not c.is_used]
            if opponent_cards:
                effect.card_cancelled_id = opponent_cards[-1].id
        
        elif card.card_type == CardType.OFFSIDE:
            effect.target_player_id = target_player_id  # Игрок соперника
            effect.goals_removed = 1
        
        elif card.card_type == CardType.PENALTY:
            effect.target_player_id = target_player_id
            effect.requires_penalty_roll = True
        
        elif card.card_type == CardType.RED_CARD:
            effect.target_player_id = target_player_id  # Игрок соперника
            effect.player_removed = True
        
        elif card.card_type == CardType.YELLOW_CARD:
            effect.target_player_id = target_player_id  # Игрок соперника
            # Соперник выбирает какое действие убрать
        
        elif card.card_type == CardType.FOUL:
            effect.target_player_id = target_player_id
            effect.saves_removed = 1
        
        elif card.card_type == CardType.LOSS:
            effect.target_player_id = target_player_id
            effect.passes_removed = 1
        
        elif card.card_type == CardType.INTERCEPTION:
            effect.target_player_id = target_player_id
            effect.passes_added = 1
        
        elif card.card_type == CardType.TACKLE:
            effect.target_player_id = target_player_id
            effect.saves_added = 1
        
        return effect
    
    @staticmethod
    def apply_effect(match: Match, effect: CardEffect) -> Match:
        """Применить эффект к матчу"""
        
        if effect.target_player_id:
            # Находим игрока
            player = None
            for team in [match.team1, match.team2]:
                if team:
                    p = next((p for p in team.players if p.id == effect.target_player_id), None)
                    if p:
                        player = p
                        break
            
            if player:
                if effect.goals_added > 0:
                    player.add_goals(effect.goals_added)
                if effect.goals_removed > 0:
                    for _ in range(effect.goals_removed):
                        player.remove_action("goal")
                if effect.saves_added > 0:
                    player.add_saves(effect.saves_added)
                if effect.saves_removed > 0:
                    for _ in range(effect.saves_removed):
                        player.remove_action("save")
                if effect.passes_added > 0:
                    player.add_passes(effect.passes_added)
                if effect.passes_removed > 0:
                    for _ in range(effect.passes_removed):
                        player.remove_action("pass")
                if effect.player_removed:
                    player.clear_stats()
        
        if effect.card_cancelled_id:
            # Отменяем эффект карточки
            cancelled = next((c for c in match.whistle_cards_drawn 
                            if c.id == effect.card_cancelled_id), None)
            if cancelled:
                cancelled.is_used = False  # Помечаем как неиспользованную
        
        if effect.requires_penalty_roll:
            match.current_turn.waiting_for_penalty_roll = True
        
        return match
```

---

## 3. Bot AI (Искусственный интеллект)

```python
# src/core/ai/bot_ai.py

from uuid import UUID
from typing import List, Tuple, Optional
import random

from ..models.match import Match
from ..models.team import Team, Formation
from ..models.player import Player, Position
from ..models.bet import Bet, BetType, EvenOddChoice, HighLowChoice

class AIStrategy:
    """Базовая стратегия бота"""
    
    def choose_formation(self, team: Team) -> Formation:
        raise NotImplementedError
    
    def choose_lineup(self, team: Team, formation: Formation) -> List[UUID]:
        raise NotImplementedError
    
    def choose_bets(self, match: Match, player: Player) -> List[Bet]:
        raise NotImplementedError

class RandomStrategy(AIStrategy):
    """Случайная стратегия — для простого бота"""
    
    def choose_formation(self, team: Team) -> Formation:
        return random.choice(list(Formation))
    
    def choose_lineup(self, team: Team, formation: Formation) -> List[UUID]:
        from ..models.team import FORMATION_STRUCTURE
        
        structure = FORMATION_STRUCTURE[formation]
        lineup = []
        
        for position, count in structure.items():
            players = [p for p in team.players 
                      if p.position.value == position and p.is_available]
            selected = random.sample(players, min(count, len(players)))
            lineup.extend([p.id for p in selected])
        
        return lineup
    
    def choose_bets(self, match: Match, player: Player) -> List[Bet]:
        bets = []
        
        # Обязательная ставка на чёт/нечёт для вратаря
        if player.position == Position.GOALKEEPER:
            bets.append(Bet(
                id=UUID(int=0),  # Временный
                match_id=match.id,
                manager_id=match.manager2_id,
                player_id=player.id,
                turn_number=match.current_turn.turn_number,
                bet_type=BetType.EVEN_ODD,
                even_odd_choice=random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
            ))
            return bets
        
        # Первая ставка
        bet1_type = random.choice([BetType.EVEN_ODD, BetType.HIGH_LOW, BetType.EXACT_NUMBER])
        bets.append(self._create_bet(match, player, bet1_type))
        
        # Вторая ставка (опционально)
        if random.random() > 0.3:
            bet2_type = random.choice([BetType.HIGH_LOW, BetType.EXACT_NUMBER])
            bets.append(self._create_bet(match, player, bet2_type))
        
        return bets
    
    def _create_bet(self, match: Match, player: Player, bet_type: BetType) -> Bet:
        bet = Bet(
            id=UUID(int=0),
            match_id=match.id,
            manager_id=match.manager2_id,
            player_id=player.id,
            turn_number=match.current_turn.turn_number,
            bet_type=bet_type
        )
        
        if bet_type == BetType.EVEN_ODD:
            bet.even_odd_choice = random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
        elif bet_type == BetType.HIGH_LOW:
            bet.high_low_choice = random.choice([HighLowChoice.LOW, HighLowChoice.HIGH])
        elif bet_type == BetType.EXACT_NUMBER:
            bet.exact_number = random.randint(1, 6)
        
        return bet

class SmartStrategy(AIStrategy):
    """Умная стратегия — анализирует вероятности"""
    
    def choose_formation(self, team: Team) -> Formation:
        # Выбираем формацию с наибольшим числом атакующих игроков
        # если у нас сильные форварды
        forwards = team.get_players_by_position(Position.FORWARD)
        if len(forwards) >= 4:
            return Formation.F_3_3_4
        return Formation.F_4_3_3
    
    def choose_lineup(self, team: Team, formation: Formation) -> List[UUID]:
        # Выбираем лучших игроков по каждой позиции
        # (в будущем можно добавить рейтинги игроков)
        return RandomStrategy().choose_lineup(team, formation)
    
    def choose_bets(self, match: Match, player: Player) -> List[Bet]:
        # Умная стратегия: чаще ставим на более вероятные исходы
        bets = []
        
        if player.position == Position.GOALKEEPER:
            # Вратарь — чёт (50% vs 50%, но психологически люди чаще выбирают нечёт)
            bets.append(Bet(
                id=UUID(int=0),
                match_id=match.id,
                manager_id=match.manager2_id,
                player_id=player.id,
                turn_number=match.current_turn.turn_number,
                bet_type=BetType.EVEN_ODD,
                even_odd_choice=EvenOddChoice.EVEN
            ))
            return bets
        
        # Для полевых игроков — комбинируем ставки
        # HIGH_LOW имеет 50% шанс, EXACT_NUMBER — ~17%
        
        # Первая ставка — всегда HIGH_LOW (более надёжно)
        bets.append(Bet(
            id=UUID(int=0),
            match_id=match.id,
            manager_id=match.manager2_id,
            player_id=player.id,
            turn_number=match.current_turn.turn_number,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=random.choice([HighLowChoice.LOW, HighLowChoice.HIGH])
        ))
        
        # Вторая ставка — точное число для форвардов (нужны голы)
        if player.position == Position.FORWARD:
            bets.append(Bet(
                id=UUID(int=0),
                match_id=match.id,
                manager_id=match.manager2_id,
                player_id=player.id,
                turn_number=match.current_turn.turn_number,
                bet_type=BetType.EXACT_NUMBER,
                exact_number=random.randint(1, 6)
            ))
        
        return bets

class Final4BotAI:
    """Главный класс бота"""
    
    BOT_USER_ID = UUID('00000000-0000-0000-0000-000000000001')
    
    def __init__(self, strategy: AIStrategy = None):
        self.strategy = strategy or SmartStrategy()
    
    def prepare_team(self, team: Team) -> Tuple[Formation, List[UUID]]:
        """Подготовить команду к матчу"""
        formation = self.strategy.choose_formation(team)
        lineup = self.strategy.choose_lineup(team, formation)
        return formation, lineup
    
    def make_turn(self, match: Match) -> List[Bet]:
        """Сделать ход (выбрать ставки)"""
        team = match.get_team(self.BOT_USER_ID)
        current_player = self._get_current_player(match, team)
        
        if not current_player:
            return []
        
        return self.strategy.choose_bets(match, current_player)
    
    def _get_current_player(self, match: Match, team: Team) -> Optional[Player]:
        """Определить текущего игрока для ставки"""
        field_players = team.get_field_players()
        turn = match.current_turn.turn_number
        
        # Порядок: вратарь, защитники, полузащитники, форварды
        order = []
        order.append(team.get_goalkeeper())
        order.extend([p for p in field_players if p.position == Position.DEFENDER])
        order.extend([p for p in field_players if p.position == Position.MIDFIELDER])
        order.extend([p for p in field_players if p.position == Position.FORWARD])
        
        # Индекс в цикле
        idx = (turn - 1) % len(order)
        return order[idx] if idx < len(order) else None
    
    def choose_whistle_card_target(
        self,
        match: Match,
        card_type: str,
        targets: List[Player]
    ) -> Optional[UUID]:
        """Выбрать цель для карточки Свисток"""
        if not targets:
            return None
        
        # Для негативных карточек — выбираем игрока с наибольшим количеством действий
        if card_type in ['offside', 'red_card', 'yellow_card', 'foul', 'loss']:
            best = max(targets, key=lambda p: p.stats.goals + p.stats.passes + p.stats.saves)
            return best.id
        
        # Для позитивных — выбираем форварда или полузащитника
        forwards = [p for p in targets if p.position == Position.FORWARD]
        if forwards:
            return random.choice(forwards).id
        
        mids = [p for p in targets if p.position == Position.MIDFIELDER]
        if mids:
            return random.choice(mids).id
        
        return random.choice(targets).id
```

---

## 4. Интерфейсы репозиториев

```python
# src/core/interfaces/repositories.py

from abc import ABC, abstractmethod
from uuid import UUID
from typing import List, Optional
from datetime import datetime

from ..models.user import User
from ..models.match import Match, MatchStatus
from ..models.bet import Bet

class IUserRepository(ABC):
    """Интерфейс репозитория пользователей"""
    
    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        pass
    
    @abstractmethod
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        pass
    
    @abstractmethod
    async def get_by_vk_id(self, vk_id: int) -> Optional[User]:
        pass
    
    @abstractmethod
    async def get_by_discord_id(self, discord_id: int) -> Optional[User]:
        pass
    
    @abstractmethod
    async def create(self, user: User) -> User:
        pass
    
    @abstractmethod
    async def update(self, user: User) -> User:
        pass
    
    @abstractmethod
    async def get_leaderboard(self, limit: int = 100) -> List[User]:
        pass

class IMatchRepository(ABC):
    """Интерфейс репозитория матчей"""
    
    @abstractmethod
    async def get_by_id(self, match_id: UUID) -> Optional[Match]:
        pass
    
    @abstractmethod
    async def create(self, match: Match) -> Match:
        pass
    
    @abstractmethod
    async def update(self, match: Match) -> Match:
        pass
    
    @abstractmethod
    async def get_waiting_matches(self, platform: str) -> List[Match]:
        pass
    
    @abstractmethod
    async def get_user_matches(
        self,
        user_id: UUID,
        status: Optional[MatchStatus] = None,
        limit: int = 10
    ) -> List[Match]:
        pass
    
    @abstractmethod
    async def get_user_match_history(
        self,
        user_id: UUID,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Match]:
        pass

class IBetRepository(ABC):
    """Интерфейс репозитория ставок"""
    
    @abstractmethod
    async def get_by_id(self, bet_id: UUID) -> Optional[Bet]:
        pass
    
    @abstractmethod
    async def create(self, bet: Bet) -> Bet:
        pass
    
    @abstractmethod
    async def get_match_bets(self, match_id: UUID) -> List[Bet]:
        pass
    
    @abstractmethod
    async def get_user_bets_in_match(self, match_id: UUID, user_id: UUID) -> List[Bet]:
        pass
```
