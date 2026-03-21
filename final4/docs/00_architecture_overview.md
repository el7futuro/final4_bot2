# Техническая спецификация: Final 4

## Обзор архитектуры

### Диаграмма слоёв

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Telegram   │  │     VK      │  │   Discord   │  │      REST API       │ │
│  │  (aiogram)  │  │ (vkbottle)  │  │(discord.py) │  │     (FastAPI)       │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
└─────────┼────────────────┼────────────────┼────────────────────┼────────────┘
          │                │                │                    │
          └────────────────┴────────────────┴────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  MatchService   │  │   UserService   │  │     TournamentService       │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────────┬──────────────┘  │
└───────────┼────────────────────┼─────────────────────────┼──────────────────┘
            │                    │                         │
            └────────────────────┼─────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DOMAIN LAYER (CORE)                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ GameEngine  │  │  BetTracker │  │   BotAI     │  │    GameRules        │ │
│  │             │  │             │  │             │  │                     │ │
│  │ - Match     │  │ - Bet       │  │ - Strategy  │  │ - Formations        │ │
│  │ - Team      │  │ - BetType   │  │ - Evaluate  │  │ - PositionRules     │ │
│  │ - Player    │  │ - BetResult │  │ - MakeMove  │  │ - ActionCalculator  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        WhistleCardDeck                                  │ │
│  │  - Card types: HatTrick, Double, Goal, OwnGoal, VAR, Offside, etc.     │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       INFRASTRUCTURE LAYER                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  PostgreSQL     │  │     Redis       │  │      Event Bus              │  │
│  │  (SQLAlchemy)   │  │    (Cache)      │  │   (Internal Pub/Sub)        │  │
│  │                 │  │                 │  │                             │  │
│  │  - UserRepo     │  │  - SessionCache │  │  - MatchEvents              │  │
│  │  - MatchRepo    │  │  - RateLimiter  │  │  - UserEvents               │  │
│  │  - BetRepo      │  │  - Leaderboard  │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Принципы изоляции

| Принцип | Описание | Применение |
|---------|----------|------------|
| **Dependency Inversion** | Верхние слои зависят от абстракций, не от реализаций | Core не импортирует aiogram/vkbottle/discord |
| **Clean Architecture** | Бизнес-логика изолирована от фреймворков | GameEngine не знает о Telegram |
| **Repository Pattern** | Абстракция доступа к данным | MatchRepository, UserRepository |
| **Adapter Pattern** | Преобразование интерфейсов платформ | TelegramAdapter, VKAdapter |
| **Event-Driven** | Слабая связанность через события | MatchCreated, BetPlaced events |

### Правила зависимостей

```
CORE (Domain Layer)
├── НЕ импортирует: aiogram, vkbottle, discord, sqlalchemy, redis
├── Импортирует: pydantic, typing, uuid, datetime, random, enum
└── Экспортирует: доменные модели, интерфейсы репозиториев

INFRASTRUCTURE
├── Импортирует: core (интерфейсы), sqlalchemy, redis
└── Экспортирует: реализации репозиториев

PLATFORMS (Adapters)
├── Импортирует: core (модели, сервисы), infrastructure (репозитории)
└── НЕ импортирует: другие платформы (telegram не импортирует vk)

APPLICATION (Services)
├── Импортирует: core (доменные модели), infrastructure (репозитории)
└── Экспортирует: сервисы для платформ
```

### Структура репозитория

```
final4/
├── src/
│   ├── core/                          # DOMAIN LAYER
│   │   ├── __init__.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── player.py              # Player, Position, PlayerStats
│   │   │   ├── team.py                # Team, Formation, LineUp
│   │   │   ├── match.py               # Match, MatchStatus, MatchResult
│   │   │   ├── bet.py                 # Bet, BetType, BetOutcome
│   │   │   ├── whistle_card.py        # WhistleCard, CardType, CardEffect
│   │   │   └── user.py                # User, UserPlan, UserStats
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── game_engine.py         # GameEngine class
│   │   │   ├── bet_tracker.py         # BetTracker class
│   │   │   ├── action_calculator.py   # ActionCalculator
│   │   │   ├── score_calculator.py    # ScoreCalculator
│   │   │   └── whistle_deck.py        # WhistleDeck class
│   │   ├── ai/
│   │   │   ├── __init__.py
│   │   │   ├── bot_ai.py              # Final4BotAI
│   │   │   └── strategies.py          # AI strategies
│   │   ├── rules/
│   │   │   ├── __init__.py
│   │   │   ├── formations.py          # Formation rules
│   │   │   ├── positions.py           # Position rules
│   │   │   └── betting_rules.py       # Betting constraints
│   │   └── interfaces/
│   │       ├── __init__.py
│   │       ├── repositories.py        # Abstract repositories
│   │       └── services.py            # Service interfaces
│   │
│   ├── application/                   # APPLICATION LAYER
│   │   ├── __init__.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── match_service.py       # MatchService
│   │   │   ├── user_service.py        # UserService
│   │   │   └── tournament_service.py  # TournamentService
│   │   └── dto/
│   │       ├── __init__.py
│   │       ├── match_dto.py           # Match DTOs
│   │       └── user_dto.py            # User DTOs
│   │
│   ├── infrastructure/                # INFRASTRUCTURE LAYER
│   │   ├── __init__.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── database.py            # Database connection
│   │   │   ├── models.py              # SQLAlchemy models
│   │   │   └── migrations/            # Alembic migrations
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── user_repository.py     # UserRepository impl
│   │   │   ├── match_repository.py    # MatchRepository impl
│   │   │   └── bet_repository.py      # BetRepository impl
│   │   ├── cache/
│   │   │   ├── __init__.py
│   │   │   ├── redis_client.py        # Redis connection
│   │   │   ├── session_cache.py       # Session management
│   │   │   └── rate_limiter.py        # Rate limiting
│   │   └── events/
│   │       ├── __init__.py
│   │       └── event_bus.py           # Internal event bus
│   │
│   └── platforms/                     # PRESENTATION LAYER
│       ├── __init__.py
│       ├── telegram/
│       │   ├── __init__.py
│       │   ├── bot.py                 # Bot initialization
│       │   ├── handlers/
│       │   │   ├── __init__.py
│       │   │   ├── start.py           # /start command
│       │   │   ├── match.py           # Match handlers
│       │   │   ├── bet.py             # Betting handlers
│       │   │   └── profile.py         # Profile handlers
│       │   ├── keyboards/
│       │   │   ├── __init__.py
│       │   │   └── inline.py          # Inline keyboards
│       │   ├── callbacks/
│       │   │   ├── __init__.py
│       │   │   └── callback_data.py   # Callback data factories
│       │   └── renderers/
│       │       ├── __init__.py
│       │       └── match_renderer.py  # Message rendering
│       ├── vk/
│       │   ├── __init__.py
│       │   ├── bot.py
│       │   ├── handlers/
│       │   ├── keyboards/
│       │   └── renderers/
│       ├── discord/
│       │   ├── __init__.py
│       │   ├── bot.py
│       │   ├── cogs/
│       │   └── views/
│       └── api/
│           ├── __init__.py
│           ├── main.py                # FastAPI app
│           ├── routes/
│           │   ├── __init__.py
│           │   ├── matches.py
│           │   ├── users.py
│           │   └── auth.py
│           └── schemas/
│               ├── __init__.py
│               └── responses.py
│
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── test_game_engine.py
│   │   │   ├── test_bet_tracker.py
│   │   │   ├── test_action_calculator.py
│   │   │   └── test_bot_ai.py
│   │   └── application/
│   │       └── test_match_service.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_repositories.py
│   │   └── test_full_match.py
│   └── fixtures/
│       ├── __init__.py
│       └── match_fixtures.py
│
├── scripts/
│   ├── simulate_match.py              # Match simulation
│   └── seed_data.py                   # Test data seeding
│
├── config/
│   ├── __init__.py
│   └── settings.py                    # Pydantic settings
│
├── alembic.ini
├── pyproject.toml
├── requirements.txt
└── README.md
```

### Потоки данных

```
[Создание матча]
User -> Platform Adapter -> MatchService -> GameEngine -> MatchRepository -> DB
                                                      -> Redis (session)
                                                      -> EventBus (MatchCreated)

[Размещение ставки]
User -> Platform Adapter -> MatchService -> BetTracker -> BetRepository -> DB
                                         -> GameEngine (validate)
                                         -> EventBus (BetPlaced)

[Бросок кубика]
User -> Platform Adapter -> MatchService -> GameEngine.roll_dice()
                                         -> ActionCalculator.calculate()
                                         -> WhistleDeck.draw_card()
                                         -> ScoreCalculator.update()
                                         -> MatchRepository.save()
                                         -> EventBus (TurnCompleted)
```

### Версионирование API

| Версия | Путь | Статус |
|--------|------|--------|
| v1 | `/api/v1/*` | Текущая |

### Форматы данных

- **Внутренний обмен**: Pydantic models
- **REST API**: JSON (snake_case)
- **База данных**: PostgreSQL (snake_case)
- **Кэш**: JSON-сериализация через orjson
