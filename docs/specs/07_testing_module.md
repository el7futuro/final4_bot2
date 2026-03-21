# Модуль: Testing (Тестирование)

## Обзор

Модуль тестирования включает unit-тесты для Core, интеграционные тесты и симуляцию полного матча.

---

## 1. Структура тестов

```
tests/
├── __init__.py
├── conftest.py                 # Pytest fixtures
├── unit/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── test_game_engine.py
│   │   ├── test_bet_tracker.py
│   │   ├── test_action_calculator.py
│   │   ├── test_score_calculator.py
│   │   ├── test_whistle_deck.py
│   │   └── test_bot_ai.py
│   └── application/
│       ├── __init__.py
│       └── test_match_service.py
├── integration/
│   ├── __init__.py
│   ├── test_repositories.py
│   └── test_full_match.py
└── fixtures/
    ├── __init__.py
    ├── match_fixtures.py
    └── team_fixtures.py
```

---

## 2. Pytest Configuration

```python
# tests/conftest.py

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime
from typing import List

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.core.models.player import Player, Position, PlayerStats
from src.core.models.team import Team, Formation
from src.core.models.match import Match, MatchType, MatchStatus
from src.core.models.user import User, PlatformIds, UserStats, DailyLimits
from src.core.engine.game_engine import GameEngine
from src.infrastructure.db.models import Base

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/final4_test"

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()

@pytest.fixture
async def db_session(test_engine):
    """Create test database session."""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    
    async with session_factory() as session:
        yield session
        await session.rollback()

@pytest.fixture
def game_engine():
    """Create game engine instance."""
    return GameEngine()

@pytest.fixture
def sample_user() -> User:
    """Create sample user."""
    return User(
        id=uuid4(),
        username="TestUser",
        platform_ids=PlatformIds(telegram_id=123456789),
        stats=UserStats(),
        daily_limits=DailyLimits(),
        rating=1000,
        created_at=datetime.utcnow(),
        last_active_at=datetime.utcnow()
    )

@pytest.fixture
def sample_players() -> List[Player]:
    """Create sample 16 players for a team."""
    players = []
    
    # 1 Goalkeeper
    players.append(Player(
        id=uuid4(),
        name="Вратарь",
        position=Position.GOALKEEPER,
        number=1
    ))
    
    # 5 Defenders
    for i in range(5):
        players.append(Player(
            id=uuid4(),
            name=f"Защитник {i+1}",
            position=Position.DEFENDER,
            number=2 + i
        ))
    
    # 6 Midfielders
    for i in range(6):
        players.append(Player(
            id=uuid4(),
            name=f"Полузащитник {i+1}",
            position=Position.MIDFIELDER,
            number=7 + i
        ))
    
    # 4 Forwards
    for i in range(4):
        players.append(Player(
            id=uuid4(),
            name=f"Форвард {i+1}",
            position=Position.FORWARD,
            number=13 + i
        ))
    
    return players

@pytest.fixture
def sample_team(sample_user, sample_players) -> Team:
    """Create sample team."""
    return Team(
        id=uuid4(),
        manager_id=sample_user.id,
        name="Test Team",
        players=sample_players
    )

@pytest.fixture
def sample_match(sample_user) -> Match:
    """Create sample match."""
    return Match(
        id=uuid4(),
        match_type=MatchType.VS_BOT,
        manager1_id=sample_user.id,
        created_at=datetime.utcnow(),
        platform="test"
    )
```

---

## 3. Unit Tests

### 3.1 GameEngine Tests

```python
# tests/unit/core/test_game_engine.py

import pytest
from uuid import uuid4
from datetime import datetime

from src.core.models.match import Match, MatchType, MatchStatus, MatchPhase
from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.engine.game_engine import GameEngine

class TestGameEngine:
    """Тесты игрового движка"""
    
    def test_create_match(self, game_engine, sample_user):
        """Тест создания матча"""
        match = game_engine.create_match(
            sample_user.id,
            MatchType.RANDOM,
            "telegram"
        )
        
        assert match.id is not None
        assert match.manager1_id == sample_user.id
        assert match.manager2_id is None
        assert match.status == MatchStatus.WAITING_FOR_OPPONENT
        assert match.platform == "telegram"
    
    def test_create_bot_match(self, game_engine, sample_user):
        """Тест создания матча против бота"""
        match = game_engine.create_match(
            sample_user.id,
            MatchType.VS_BOT,
            "telegram"
        )
        
        assert match.manager2_id is not None  # Bot ID
        assert match.status == MatchStatus.SETTING_LINEUP
    
    def test_join_match(self, game_engine, sample_user, sample_match):
        """Тест присоединения к матчу"""
        second_user_id = uuid4()
        
        sample_match.status = MatchStatus.WAITING_FOR_OPPONENT
        
        match = game_engine.join_match(sample_match, second_user_id)
        
        assert match.manager2_id == second_user_id
        assert match.status == MatchStatus.SETTING_LINEUP
    
    def test_join_match_already_has_opponent(self, game_engine, sample_match):
        """Тест: нельзя присоединиться если есть соперник"""
        sample_match.manager2_id = uuid4()
        
        with pytest.raises(ValueError, match="Матч уже имеет соперника"):
            game_engine.join_match(sample_match, uuid4())
    
    def test_join_match_cannot_play_self(self, game_engine, sample_match):
        """Тест: нельзя играть против себя"""
        with pytest.raises(ValueError, match="Нельзя играть против себя"):
            game_engine.join_match(sample_match, sample_match.manager1_id)
    
    def test_set_team_lineup(self, game_engine, sample_match, sample_team):
        """Тест установки состава"""
        sample_match.status = MatchStatus.SETTING_LINEUP
        sample_match.manager2_id = uuid4()
        
        # Select 11 players for 4-4-2
        player_ids = []
        gk = [p for p in sample_team.players if p.position == Position.GOALKEEPER]
        defs = [p for p in sample_team.players if p.position == Position.DEFENDER]
        mids = [p for p in sample_team.players if p.position == Position.MIDFIELDER]
        fwds = [p for p in sample_team.players if p.position == Position.FORWARD]
        
        player_ids.append(gk[0].id)
        player_ids.extend([p.id for p in defs[:4]])
        player_ids.extend([p.id for p in mids[:4]])
        player_ids.extend([p.id for p in fwds[:2]])
        
        match = game_engine.set_team_lineup(
            sample_match,
            sample_match.manager1_id,
            sample_team,
            Formation.F_4_4_2,
            player_ids
        )
        
        assert match.team1 == sample_team
        assert sample_team.formation == Formation.F_4_4_2
        assert len(sample_team.get_field_players()) == 11
    
    def test_roll_dice_range(self, game_engine, sample_match, sample_team, sample_user):
        """Тест: кубик возвращает значение 1-6"""
        # Setup match
        sample_match.status = MatchStatus.IN_PROGRESS
        sample_match.manager2_id = uuid4()
        sample_match.team1 = sample_team
        
        from src.core.models.match import TurnState
        sample_match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=sample_user.id
        )
        
        # Roll dice multiple times
        for _ in range(100):
            match_copy = sample_match.model_copy(deep=True)
            match_copy.current_turn.dice_rolled = False
            
            match, dice_value, _ = game_engine.roll_dice(match_copy, sample_user.id)
            
            assert 1 <= dice_value <= 6


class TestMatchPhases:
    """Тесты фаз матча"""
    
    def test_end_main_time_triggers_extra_time_on_draw(self, game_engine):
        """Тест: ничья в основное время → дополнительное время"""
        match = Match(
            id=uuid4(),
            match_type=MatchType.VS_BOT,
            manager1_id=uuid4(),
            manager2_id=uuid4(),
            status=MatchStatus.IN_PROGRESS,
            phase=MatchPhase.MAIN_TIME,
            total_turns_main=21,
            created_at=datetime.utcnow(),
            platform="test"
        )
        
        # Setup teams with equal stats (will result in draw)
        from src.core.models.team import Team, TeamStats
        team1 = Team(id=uuid4(), manager_id=match.manager1_id, name="Team 1")
        team2 = Team(id=uuid4(), manager_id=match.manager2_id, name="Team 2")
        team1.stats = TeamStats(total_saves=5, total_passes=5, total_goals=2)
        team2.stats = TeamStats(total_saves=5, total_passes=5, total_goals=2)
        match.team1 = team1
        match.team2 = team2
        
        from src.core.models.match import TurnState
        match.current_turn = TurnState(
            turn_number=22,
            current_manager_id=match.manager1_id
        )
        
        # End turn should trigger end of main time
        result = game_engine.end_turn(match, match.manager1_id)
        
        assert result.phase == MatchPhase.EXTRA_TIME
        assert result.status == MatchStatus.EXTRA_TIME
```

### 3.2 BetTracker Tests

```python
# tests/unit/core/test_bet_tracker.py

import pytest
from uuid import uuid4

from src.core.models.match import Match, MatchType, MatchStatus, TurnState
from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice
from src.core.engine.bet_tracker import BetTracker

class TestBetTracker:
    """Тесты трекера ставок"""
    
    @pytest.fixture
    def bet_tracker(self):
        return BetTracker()
    
    @pytest.fixture
    def match_with_team(self, sample_match, sample_team):
        """Матч с настроенной командой"""
        sample_match.team1 = sample_team
        sample_match.status = MatchStatus.IN_PROGRESS
        sample_match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=sample_match.manager1_id
        )
        return sample_match
    
    def test_goalkeeper_only_even_odd(self, bet_tracker, match_with_team):
        """Тест: вратарь может иметь только ставку на чёт/нечёт"""
        goalkeeper = match_with_team.team1.get_goalkeeper()
        
        # Even/odd should work
        even_odd_bet = Bet(
            id=uuid4(),
            match_id=match_with_team.id,
            manager_id=match_with_team.manager1_id,
            player_id=goalkeeper.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.EVEN
        )
        
        # Should not raise
        bet_tracker.validate_bet(
            match_with_team,
            match_with_team.manager1_id,
            goalkeeper,
            even_odd_bet
        )
        
        # Goal bet should fail
        goal_bet = Bet(
            id=uuid4(),
            match_id=match_with_team.id,
            manager_id=match_with_team.manager1_id,
            player_id=goalkeeper.id,
            turn_number=1,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=3
        )
        
        with pytest.raises(ValueError, match="Вратарь может иметь только"):
            bet_tracker.validate_bet(
                match_with_team,
                match_with_team.manager1_id,
                goalkeeper,
                goal_bet
            )
    
    def test_forward_no_even_odd(self, bet_tracker, match_with_team):
        """Тест: форвард не может иметь ставку на чёт/нечёт"""
        forward = [p for p in match_with_team.team1.players 
                   if p.position == Position.FORWARD][0]
        
        even_odd_bet = Bet(
            id=uuid4(),
            match_id=match_with_team.id,
            manager_id=match_with_team.manager1_id,
            player_id=forward.id,
            turn_number=1,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.ODD
        )
        
        with pytest.raises(ValueError, match="Форварды не могут"):
            bet_tracker.validate_bet(
                match_with_team,
                match_with_team.manager1_id,
                forward,
                even_odd_bet
            )
    
    def test_max_six_even_odd_bets(self, bet_tracker, match_with_team):
        """Тест: максимум 6 ставок на чёт/нечёт"""
        # Add 6 even/odd bets
        defenders = [p for p in match_with_team.team1.players 
                    if p.position == Position.DEFENDER]
        
        for i in range(6):
            match_with_team.bets.append(Bet(
                id=uuid4(),
                match_id=match_with_team.id,
                manager_id=match_with_team.manager1_id,
                player_id=defenders[i % len(defenders)].id,
                turn_number=1,
                bet_type=BetType.EVEN_ODD,
                even_odd_choice=EvenOddChoice.EVEN
            ))
        
        # 7th should fail
        seventh_bet = Bet(
            id=uuid4(),
            match_id=match_with_team.id,
            manager_id=match_with_team.manager1_id,
            player_id=defenders[0].id,
            turn_number=2,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=EvenOddChoice.ODD
        )
        
        with pytest.raises(ValueError, match="Максимум 6"):
            bet_tracker.validate_bet(
                match_with_team,
                match_with_team.manager1_id,
                defenders[0],
                seventh_bet
            )
    
    def test_get_available_bet_types(self, bet_tracker, match_with_team):
        """Тест получения доступных типов ставок"""
        # Goalkeeper: only EVEN_ODD
        goalkeeper = match_with_team.team1.get_goalkeeper()
        gk_types = bet_tracker.get_available_bet_types(
            match_with_team,
            match_with_team.manager1_id,
            goalkeeper
        )
        assert BetType.EVEN_ODD in gk_types
        assert BetType.EXACT_NUMBER not in gk_types
        
        # Forward: HIGH_LOW and EXACT_NUMBER, no EVEN_ODD
        forward = [p for p in match_with_team.team1.players 
                   if p.position == Position.FORWARD][0]
        fwd_types = bet_tracker.get_available_bet_types(
            match_with_team,
            match_with_team.manager1_id,
            forward
        )
        assert BetType.HIGH_LOW in fwd_types
        assert BetType.EXACT_NUMBER in fwd_types
        assert BetType.EVEN_ODD not in fwd_types
```

### 3.3 ScoreCalculator Tests

```python
# tests/unit/core/test_score_calculator.py

import pytest
from uuid import uuid4

from src.core.models.team import Team, TeamStats
from src.core.engine.score_calculator import ScoreCalculator

class TestScoreCalculator:
    """Тесты калькулятора счёта"""
    
    @pytest.fixture
    def calculator(self):
        return ScoreCalculator()
    
    def test_goals_scored_when_defense_broken(self, calculator):
        """Тест: все голы засчитываются если оборона сломана"""
        team1 = Team(id=uuid4(), manager_id=uuid4(), name="Team 1")
        team2 = Team(id=uuid4(), manager_id=uuid4(), name="Team 2")
        
        # Team 1: 6 passes, 2 goals vs Team 2: 6 saves
        # 6 passes >= 6 saves → defense broken → 2 goals scored
        team1.stats = TeamStats(total_saves=0, total_passes=6, total_goals=2)
        team2.stats = TeamStats(total_saves=6, total_passes=0, total_goals=0)
        
        score = calculator.calculate_score(team1, team2)
        
        assert score.manager1_goals == 2
    
    def test_goals_consumed_to_break_defense(self, calculator):
        """Тест: голы расходуются на пробитие обороны"""
        team1 = Team(id=uuid4(), manager_id=uuid4(), name="Team 1")
        team2 = Team(id=uuid4(), manager_id=uuid4(), name="Team 2")
        
        # Team 1: 7 passes, 3 goals vs Team 2: 10 saves
        # 10 - 7 = 3 remaining saves
        # Need 2 goals to clear 3 saves (1 goal = 2 saves)
        # 3 - 2 = 1 goal scored
        team1.stats = TeamStats(total_saves=0, total_passes=7, total_goals=3)
        team2.stats = TeamStats(total_saves=10, total_passes=0, total_goals=0)
        
        score = calculator.calculate_score(team1, team2)
        
        assert score.manager1_goals == 1
    
    def test_example_from_rules(self, calculator):
        """Тест примера из правил"""
        # Team 1: 2G, 6P, 10S
        # Team 2: 3G, 7P, 6S
        
        team1 = Team(id=uuid4(), manager_id=uuid4(), name="Team 1")
        team2 = Team(id=uuid4(), manager_id=uuid4(), name="Team 2")
        
        team1.stats = TeamStats(total_saves=10, total_passes=6, total_goals=2)
        team2.stats = TeamStats(total_saves=6, total_passes=7, total_goals=3)
        
        score = calculator.calculate_score(team1, team2)
        
        # Team 1 goals: 6S (opp) - 6P = 0 remaining → 2 goals scored
        assert score.manager1_goals == 2
        
        # Team 2 goals: 10S (opp) - 7P = 3 remaining
        # Need ceil(3/2) = 2 goals to clear
        # 3G - 2 = 1 goal scored
        assert score.manager2_goals == 1
    
    def test_no_goals_if_all_consumed(self, calculator):
        """Тест: 0 голов если все ушли на пробитие обороны"""
        team1 = Team(id=uuid4(), manager_id=uuid4(), name="Team 1")
        team2 = Team(id=uuid4(), manager_id=uuid4(), name="Team 2")
        
        # Team 1: 2 passes, 1 goal vs Team 2: 10 saves
        # 10 - 2 = 8 remaining saves
        # Need 4 goals to clear
        # 1 goal < 4 needed → 0 scored
        team1.stats = TeamStats(total_saves=0, total_passes=2, total_goals=1)
        team2.stats = TeamStats(total_saves=10, total_passes=0, total_goals=0)
        
        score = calculator.calculate_score(team1, team2)
        
        assert score.manager1_goals == 0
```

### 3.4 WhistleDeck Tests

```python
# tests/unit/core/test_whistle_deck.py

import pytest
from uuid import uuid4

from src.core.models.whistle_card import CardType, CARD_DISTRIBUTION
from src.core.engine.whistle_deck import WhistleDeck

class TestWhistleDeck:
    """Тесты колоды Свисток"""
    
    def test_create_deck_has_40_cards(self):
        """Тест: колода содержит 40 карточек"""
        deck = WhistleDeck.create_deck()
        assert len(deck) == 40
    
    def test_create_deck_correct_distribution(self):
        """Тест: распределение карточек соответствует правилам"""
        deck = WhistleDeck.create_deck()
        
        counts = {}
        for card in deck:
            counts[card.card_type] = counts.get(card.card_type, 0) + 1
        
        for card_type, expected_count in CARD_DISTRIBUTION.items():
            assert counts.get(card_type, 0) == expected_count, \
                f"{card_type}: expected {expected_count}, got {counts.get(card_type, 0)}"
    
    def test_create_deck_is_shuffled(self):
        """Тест: колода перемешана (не всегда одинаковый порядок)"""
        decks = [WhistleDeck.create_deck() for _ in range(10)]
        
        # Compare first cards - they shouldn't all be the same
        first_cards = [deck[0].card_type for deck in decks]
        
        # At least some variation expected
        assert len(set(first_cards)) > 1
    
    def test_hat_trick_effect(self):
        """Тест эффекта Хэт-трик"""
        from src.core.models.whistle_card import WhistleCard
        from src.core.models.match import Match, MatchType
        from datetime import datetime
        
        card = WhistleCard(id=uuid4(), card_type=CardType.HAT_TRICK)
        match = Match(
            id=uuid4(),
            match_type=MatchType.VS_BOT,
            manager1_id=uuid4(),
            created_at=datetime.utcnow(),
            platform="test"
        )
        
        target_player_id = uuid4()
        
        effect = WhistleDeck.get_card_effect(
            card, match, match.manager1_id, target_player_id
        )
        
        assert effect.goals_added == 3
        assert effect.target_player_id == target_player_id
```

### 3.5 Bot AI Tests

```python
# tests/unit/core/test_bot_ai.py

import pytest
from uuid import uuid4

from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.models.match import Match, MatchType, MatchStatus, TurnState
from src.core.ai.bot_ai import Final4BotAI, RandomStrategy, SmartStrategy

class TestBotAI:
    """Тесты AI бота"""
    
    @pytest.fixture
    def bot_ai(self):
        return Final4BotAI(strategy=SmartStrategy())
    
    def test_prepare_team_returns_valid_lineup(self, bot_ai, sample_team):
        """Тест: бот возвращает валидный состав"""
        formation, lineup = bot_ai.prepare_team(sample_team)
        
        assert formation in Formation
        assert len(lineup) == 11
        
        # All IDs should be from team
        team_ids = [p.id for p in sample_team.players]
        for player_id in lineup:
            assert player_id in team_ids
    
    def test_make_turn_returns_bets(self, bot_ai, sample_match, sample_team):
        """Тест: бот возвращает ставки"""
        sample_match.manager2_id = Final4BotAI.BOT_USER_ID
        sample_match.team2 = sample_team
        sample_team.set_formation(Formation.F_4_4_2)
        
        # Set lineup
        player_ids = []
        gk = [p for p in sample_team.players if p.position == Position.GOALKEEPER]
        defs = [p for p in sample_team.players if p.position == Position.DEFENDER]
        mids = [p for p in sample_team.players if p.position == Position.MIDFIELDER]
        fwds = [p for p in sample_team.players if p.position == Position.FORWARD]
        
        player_ids.append(gk[0].id)
        player_ids.extend([p.id for p in defs[:4]])
        player_ids.extend([p.id for p in mids[:4]])
        player_ids.extend([p.id for p in fwds[:2]])
        
        sample_team.set_lineup(player_ids)
        
        sample_match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=Final4BotAI.BOT_USER_ID
        )
        
        bets = bot_ai.make_turn(sample_match)
        
        assert len(bets) >= 1
        assert all(b.manager_id == Final4BotAI.BOT_USER_ID for b in bets)
```

---

## 4. Integration Tests

```python
# tests/integration/test_repositories.py

import pytest
from uuid import uuid4
from datetime import datetime

from src.core.models.user import User, PlatformIds, UserStats, DailyLimits
from src.infrastructure.repositories.user_repository import UserRepository

@pytest.mark.asyncio
class TestUserRepository:
    """Интеграционные тесты репозитория пользователей"""
    
    async def test_create_and_get_user(self, db_session):
        """Тест создания и получения пользователя"""
        repo = UserRepository(db_session)
        
        user = User(
            id=uuid4(),
            username="IntegrationTestUser",
            platform_ids=PlatformIds(telegram_id=987654321),
            stats=UserStats(),
            daily_limits=DailyLimits(),
            rating=1000,
            created_at=datetime.utcnow(),
            last_active_at=datetime.utcnow()
        )
        
        created = await repo.create(user)
        assert created.id == user.id
        
        fetched = await repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.username == "IntegrationTestUser"
    
    async def test_get_by_telegram_id(self, db_session):
        """Тест получения по Telegram ID"""
        repo = UserRepository(db_session)
        
        telegram_id = 111222333
        user = User(
            id=uuid4(),
            username="TelegramUser",
            platform_ids=PlatformIds(telegram_id=telegram_id),
            stats=UserStats(),
            daily_limits=DailyLimits(),
            rating=1000,
            created_at=datetime.utcnow(),
            last_active_at=datetime.utcnow()
        )
        
        await repo.create(user)
        
        fetched = await repo.get_by_telegram_id(telegram_id)
        assert fetched is not None
        assert fetched.id == user.id
    
    async def test_update_user(self, db_session):
        """Тест обновления пользователя"""
        repo = UserRepository(db_session)
        
        user = User(
            id=uuid4(),
            username="UpdateTestUser",
            platform_ids=PlatformIds(telegram_id=444555666),
            stats=UserStats(),
            daily_limits=DailyLimits(),
            rating=1000,
            created_at=datetime.utcnow(),
            last_active_at=datetime.utcnow()
        )
        
        await repo.create(user)
        
        user.rating = 1500
        user.stats.matches_won = 10
        
        updated = await repo.update(user)
        
        assert updated.rating == 1500
        assert updated.stats.matches_won == 10
    
    async def test_leaderboard_ordered_by_rating(self, db_session):
        """Тест: лидерборд отсортирован по рейтингу"""
        repo = UserRepository(db_session)
        
        # Create users with different ratings
        users = []
        for i, rating in enumerate([800, 1200, 1000, 1500, 900]):
            user = User(
                id=uuid4(),
                username=f"LeaderboardUser{i}",
                platform_ids=PlatformIds(telegram_id=700000000 + i),
                stats=UserStats(),
                daily_limits=DailyLimits(),
                rating=rating,
                created_at=datetime.utcnow(),
                last_active_at=datetime.utcnow()
            )
            await repo.create(user)
            users.append(user)
        
        leaderboard = await repo.get_leaderboard(10)
        
        ratings = [u.rating for u in leaderboard]
        assert ratings == sorted(ratings, reverse=True)
```

```python
# tests/integration/test_full_match.py

import pytest
from uuid import uuid4

from src.core.models.match import MatchType, MatchStatus, MatchPhase
from src.core.models.team import Formation
from src.core.models.player import Position
from src.core.models.bet import BetType, EvenOddChoice, HighLowChoice
from src.core.engine.game_engine import GameEngine

@pytest.mark.asyncio
class TestFullMatch:
    """Интеграционный тест полного матча"""
    
    async def test_complete_match_flow(self, sample_players):
        """Тест полного прохождения матча"""
        engine = GameEngine()
        
        # Create players for both teams
        team1_players = sample_players.copy()
        team2_players = [
            p.model_copy(update={"id": uuid4(), "name": f"Opp {p.name}"})
            for p in sample_players
        ]
        
        # Create match
        user1_id = uuid4()
        user2_id = uuid4()
        
        match = engine.create_match(user1_id, MatchType.RANDOM, "test")
        assert match.status == MatchStatus.WAITING_FOR_OPPONENT
        
        # Join match
        match = engine.join_match(match, user2_id)
        assert match.status == MatchStatus.SETTING_LINEUP
        
        # Setup teams
        from src.core.models.team import Team
        
        team1 = Team(id=uuid4(), manager_id=user1_id, name="Team 1", players=team1_players)
        team2 = Team(id=uuid4(), manager_id=user2_id, name="Team 2", players=team2_players)
        
        # Select lineup for 4-4-2
        def get_lineup_ids(team):
            ids = []
            ids.append([p.id for p in team.players if p.position == Position.GOALKEEPER][0])
            ids.extend([p.id for p in team.players if p.position == Position.DEFENDER][:4])
            ids.extend([p.id for p in team.players if p.position == Position.MIDFIELDER][:4])
            ids.extend([p.id for p in team.players if p.position == Position.FORWARD][:2])
            return ids
        
        match = engine.set_team_lineup(match, user1_id, team1, Formation.F_4_4_2, get_lineup_ids(team1))
        match = engine.set_team_lineup(match, user2_id, team2, Formation.F_4_4_2, get_lineup_ids(team2))
        
        assert match.status == MatchStatus.IN_PROGRESS
        assert match.current_turn is not None
        
        # Play a few turns
        for turn in range(4):
            current_user = match.current_turn.current_manager_id
            team = match.get_team(current_user)
            
            # Place bet on goalkeeper
            gk = team.get_goalkeeper()
            from src.core.models.bet import Bet
            
            bet = Bet(
                id=uuid4(),
                match_id=match.id,
                manager_id=current_user,
                player_id=gk.id,
                turn_number=match.current_turn.turn_number,
                bet_type=BetType.EVEN_ODD,
                even_odd_choice=EvenOddChoice.EVEN
            )
            
            match, bet = engine.place_bet(match, current_user, gk.id, bet)
            
            # Roll dice
            match, dice_value, won_bets = engine.roll_dice(match, current_user)
            assert 1 <= dice_value <= 6
            
            # Draw card if won
            if won_bets:
                match, card = engine.draw_whistle_card(match, current_user)
            
            # End turn
            match = engine.end_turn(match, current_user)
        
        # Verify match is still in progress or finished
        assert match.status in [MatchStatus.IN_PROGRESS, MatchStatus.EXTRA_TIME, 
                                MatchStatus.PENALTIES, MatchStatus.FINISHED]
```

---

## 5. Match Simulation Script

```python
# scripts/simulate_match.py

"""
Скрипт симуляции полного матча для тестирования игровой механики.

Использование:
    python scripts/simulate_match.py [--verbose] [--seed SEED]
"""

import argparse
import random
from uuid import uuid4
from datetime import datetime
from typing import Tuple

from src.core.models.match import Match, MatchType, MatchStatus, MatchPhase
from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice
from src.core.engine.game_engine import GameEngine
from src.core.ai.bot_ai import Final4BotAI, SmartStrategy

def create_team(manager_id, name: str) -> Team:
    """Создать команду с 16 игроками"""
    players = []
    
    # Goalkeeper
    players.append(Player(
        id=uuid4(), name=f"{name} GK", position=Position.GOALKEEPER, number=1
    ))
    
    # Defenders
    for i in range(5):
        players.append(Player(
            id=uuid4(), name=f"{name} DEF{i+1}", position=Position.DEFENDER, number=2+i
        ))
    
    # Midfielders
    for i in range(6):
        players.append(Player(
            id=uuid4(), name=f"{name} MID{i+1}", position=Position.MIDFIELDER, number=7+i
        ))
    
    # Forwards
    for i in range(4):
        players.append(Player(
            id=uuid4(), name=f"{name} FWD{i+1}", position=Position.FORWARD, number=13+i
        ))
    
    return Team(id=uuid4(), manager_id=manager_id, name=name, players=players)

def get_lineup_for_formation(team: Team, formation: Formation) -> list:
    """Получить состав для формации"""
    from src.core.models.team import FORMATION_STRUCTURE
    
    structure = FORMATION_STRUCTURE[formation]
    lineup = []
    
    for position_str, count in structure.items():
        position = Position(position_str)
        players = [p for p in team.players if p.position == position]
        lineup.extend([p.id for p in players[:count]])
    
    return lineup

def simulate_turn(engine: GameEngine, match: Match, verbose: bool) -> Match:
    """Симулировать один ход"""
    current_user = match.current_turn.current_manager_id
    team = match.get_team(current_user)
    field_players = team.get_field_players()
    
    # Choose player for bet (cycle through)
    turn_index = (match.current_turn.turn_number - 1) % len(field_players)
    player = field_players[turn_index]
    
    if verbose:
        print(f"\n  Turn {match.current_turn.turn_number}: Manager betting on {player.name}")
    
    # Place bet based on position
    if player.position == Position.GOALKEEPER:
        bet = Bet(
            id=uuid4(), match_id=match.id, manager_id=current_user,
            player_id=player.id, turn_number=match.current_turn.turn_number,
            bet_type=BetType.EVEN_ODD,
            even_odd_choice=random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
        )
    elif player.position == Position.FORWARD:
        bet_type = random.choice([BetType.HIGH_LOW, BetType.EXACT_NUMBER])
        if bet_type == BetType.HIGH_LOW:
            bet = Bet(
                id=uuid4(), match_id=match.id, manager_id=current_user,
                player_id=player.id, turn_number=match.current_turn.turn_number,
                bet_type=BetType.HIGH_LOW,
                high_low_choice=random.choice([HighLowChoice.LOW, HighLowChoice.HIGH])
            )
        else:
            bet = Bet(
                id=uuid4(), match_id=match.id, manager_id=current_user,
                player_id=player.id, turn_number=match.current_turn.turn_number,
                bet_type=BetType.EXACT_NUMBER,
                exact_number=random.randint(1, 6)
            )
    else:
        bet_type = random.choice([BetType.EVEN_ODD, BetType.HIGH_LOW])
        if bet_type == BetType.EVEN_ODD:
            bet = Bet(
                id=uuid4(), match_id=match.id, manager_id=current_user,
                player_id=player.id, turn_number=match.current_turn.turn_number,
                bet_type=BetType.EVEN_ODD,
                even_odd_choice=random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
            )
        else:
            bet = Bet(
                id=uuid4(), match_id=match.id, manager_id=current_user,
                player_id=player.id, turn_number=match.current_turn.turn_number,
                bet_type=BetType.HIGH_LOW,
                high_low_choice=random.choice([HighLowChoice.LOW, HighLowChoice.HIGH])
            )
    
    match, bet = engine.place_bet(match, current_user, player.id, bet)
    
    if verbose:
        print(f"    Bet: {bet.bet_type.value}")
    
    # Roll dice
    match, dice_value, won_bets = engine.roll_dice(match, current_user)
    
    if verbose:
        print(f"    Dice: {dice_value}, Won: {len(won_bets)} bets")
    
    # Draw card if won
    if won_bets:
        match, card = engine.draw_whistle_card(match, current_user)
        if card and verbose:
            print(f"    Card: {card.card_type.value}")
    
    # End turn
    match = engine.end_turn(match, current_user)
    
    return match

def main():
    parser = argparse.ArgumentParser(description="Simulate a Final 4 match")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    args = parser.parse_args()
    
    if args.seed:
        random.seed(args.seed)
    
    engine = GameEngine()
    
    # Create users
    user1_id = uuid4()
    user2_id = uuid4()
    
    print("=" * 60)
    print("FINAL 4 MATCH SIMULATION")
    print("=" * 60)
    
    # Create match
    match = engine.create_match(user1_id, MatchType.RANDOM, "simulation")
    match = engine.join_match(match, user2_id)
    
    print(f"\nMatch ID: {match.id}")
    print(f"Manager 1: {user1_id}")
    print(f"Manager 2: {user2_id}")
    
    # Create and setup teams
    team1 = create_team(user1_id, "Team Alpha")
    team2 = create_team(user2_id, "Team Beta")
    
    formation1 = random.choice(list(Formation))
    formation2 = random.choice(list(Formation))
    
    lineup1 = get_lineup_for_formation(team1, formation1)
    lineup2 = get_lineup_for_formation(team2, formation2)
    
    match = engine.set_team_lineup(match, user1_id, team1, formation1, lineup1)
    match = engine.set_team_lineup(match, user2_id, team2, formation2, lineup2)
    
    print(f"\nTeam 1 Formation: {formation1.value}")
    print(f"Team 2 Formation: {formation2.value}")
    print(f"\nMatch Status: {match.status.value}")
    print("-" * 60)
    
    # Play match
    turn_count = 0
    max_turns = 100  # Safety limit
    
    while match.status not in [MatchStatus.FINISHED, MatchStatus.CANCELLED] and turn_count < max_turns:
        match = simulate_turn(engine, match, args.verbose)
        turn_count += 1
        
        if not args.verbose and turn_count % 10 == 0:
            print(f"  Turn {turn_count}... Score: {match.score.manager1_goals}-{match.score.manager2_goals}")
    
    # Results
    print("\n" + "=" * 60)
    print("MATCH RESULT")
    print("=" * 60)
    
    print(f"Final Score: {match.score.manager1_goals} - {match.score.manager2_goals}")
    print(f"Status: {match.status.value}")
    print(f"Phase: {match.phase.value}")
    print(f"Total Turns: {turn_count}")
    
    if match.result:
        print(f"\nWinner: {match.result.winner_id}")
        print(f"Decided by: {match.result.decided_by.value}")
        if match.result.decided_by_lottery:
            print("(Decided by lottery)")
    
    # Team stats
    print("\n" + "-" * 60)
    print("TEAM STATISTICS")
    print("-" * 60)
    
    match.team1.calculate_stats()
    match.team2.calculate_stats()
    
    print(f"\nTeam Alpha:")
    print(f"  Saves: {match.team1.stats.total_saves}")
    print(f"  Passes: {match.team1.stats.total_passes}")
    print(f"  Goals: {match.team1.stats.total_goals}")
    
    print(f"\nTeam Beta:")
    print(f"  Saves: {match.team2.stats.total_saves}")
    print(f"  Passes: {match.team2.stats.total_passes}")
    print(f"  Goals: {match.team2.stats.total_goals}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
```

---

## 6. Test Commands

```bash
# Запуск всех тестов
pytest tests/ -v

# Только unit-тесты
pytest tests/unit/ -v

# Только интеграционные тесты
pytest tests/integration/ -v --asyncio-mode=auto

# С покрытием
pytest tests/ -v --cov=src --cov-report=html

# Конкретный файл
pytest tests/unit/core/test_game_engine.py -v

# Конкретный тест
pytest tests/unit/core/test_game_engine.py::TestGameEngine::test_create_match -v

# Симуляция матча
python scripts/simulate_match.py --verbose --seed 42
```
