# Final 4 - Product Requirements Document

## Обзор проекта

**Final 4** — пошаговая мультиплатформенная футбольная стратегия. Игроки управляют виртуальными футбольными командами, делают ставки на игроков, бросают кубик и используют карточки "Свисток" для влияния на матч.

## Архитектура

Проект использует **Clean Architecture** со строгим разделением слоёв:

```
/app/final4/
├── src/
│   ├── core/              # Чистая бизнес-логика (БЕЗ импортов фреймворков)
│   │   ├── models/        # Pydantic модели (Player, Team, Match, Bet, etc.)
│   │   ├── engine/        # Игровой движок, калькуляторы, колода карточек
│   │   ├── ai/            # ИИ для бота-соперника
│   │   └── interfaces/    # Абстрактные репозитории
│   │
│   ├── infrastructure/    # Работа с внешними системами
│   │   ├── db/            # SQLAlchemy модели, подключение к PostgreSQL
│   │   ├── cache/         # Redis клиент, кэш сессий, rate limiter
│   │   ├── repositories/  # Реализации репозиториев
│   │   └── events/        # Шина событий
│   │
│   ├── application/       # Application services
│   │   └── services/      # UserService, MatchService
│   │
│   └── platforms/         # Платформенные адаптеры
│       └── telegram/      # Telegram бот (aiogram 3.x)
│           ├── handlers/  # Хендлеры команд и callback
│           ├── keyboards/ # Inline клавиатуры
│           ├── renderers/ # Рендеринг сообщений
│           └── states/    # FSM состояния
│
├── tests/                 # Unit и интеграционные тесты
├── scripts/               # Утилиты (simulate_match.py)
└── docs/                  # Документация и спецификации
```

## Ключевые правила архитектуры

### ✅ Core Module — БЕЗ ВНЕШНИХ ЗАВИСИМОСТЕЙ
- Использует ТОЛЬКО: `pydantic`, `uuid`, `datetime`, `typing`, `enum`, `dataclasses`
- НЕ импортирует: `aiogram`, `sqlalchemy`, `vkbottle`, `discord`, `redis`

### ✅ База данных
- PostgreSQL 15+ с Row Level Security (RLS)
- UUID первичные ключи
- JSONB для гибких данных (состав команды, колода карточек)

## Стек технологий

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.11+ |
| Валидация | Pydantic v2 |
| БД | PostgreSQL 15+ (asyncpg, SQLAlchemy 2.0) |
| Кэш | Redis 5.0+ |
| Telegram | aiogram 3.3+ |
| Тесты | pytest, pytest-asyncio |

## Реализовано

### Core Module ✅
- [x] Модели: Player, Team, Match, Bet, WhistleCard, User
- [x] GameEngine — главный игровой движок
- [x] BetTracker — валидация ставок по правилам
- [x] ActionCalculator — расчёт действий при выигрыше
- [x] ScoreCalculator — подсчёт итогового счёта
- [x] WhistleDeck — управление колодой карточек
- [x] Final4BotAI — ИИ бота-соперника

### Infrastructure Module ✅
- [x] Database — подключение к PostgreSQL
- [x] SQLAlchemy модели (UserModel, TeamModel, MatchModel)
- [x] Redis клиент и кэш сессий
- [x] Репозитории (UserRepository, TeamRepository, MatchRepository)
- [x] EventBus — шина событий

### Application Layer ✅
- [x] UserService — управление пользователями
- [x] MatchService — управление матчами

### Telegram Adapter ✅
- [x] Handlers: start, profile, match, game
- [x] Keyboards: главное меню, выбор формации, игровые действия
- [x] MatchRenderer — рендеринг игрового состояния
- [x] FSM States — состояния матча

### Testing ✅
- [x] Unit тесты Core модуля (16 тестов, 100% pass)
- [x] Скрипт симуляции матча

## Не реализовано / Требует доработки

### P0 (Высокий приоритет)
- [ ] Alembic миграции с RLS политиками
- [ ] Интеграционные тесты с БД
- [ ] Полный игровой цикл в Telegram боте

### P1 (Средний приоритет)
- [ ] VK адаптер (vkbottle)
- [ ] Discord адаптер (discord.py)
- [ ] REST API для веб-клиента

### P2 (Низкий приоритет)
- [ ] Турнирная система
- [ ] Система достижений
- [ ] Платные подписки (Stripe/ЮKassa)

## Credentials

- **Telegram Bot Token**: Хранится в `/app/final4/.env` (BOT_TOKEN)
- **PostgreSQL**: Требует настройки (DATABASE_URL)
- **Redis**: Требует настройки (REDIS_URL)

## Запуск

```bash
# Установка зависимостей
cd /app/final4
pip install -r requirements.txt

# Запуск тестов
pytest tests/unit/core/ -v

# Симуляция матча (без платформы)
python scripts/simulate_match.py

# Запуск Telegram бота (требует PostgreSQL/Redis)
python run_bot.py
```

## Последнее обновление

**Дата**: Декабрь 2025

**Статус**: MVP в разработке. Core модуль завершён и протестирован. Telegram адаптер структурирован. Требуется интеграционное тестирование.
