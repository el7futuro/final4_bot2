# Final 4 — Техническая спецификация

## Содержание

1. [Обзор архитектуры](./00_architecture_overview.md)
   - Диаграмма слоёв
   - Принципы изоляции
   - Правила зависимостей
   - Структура репозитория

2. [Модуль Core](./01_core_module.md)
   - Pydantic модели (Player, Team, Match, Bet, WhistleCard, User)
   - GameEngine
   - BetTracker
   - ActionCalculator
   - ScoreCalculator
   - WhistleDeck
   - Bot AI
   - Интерфейсы репозиториев

3. [Модуль Infrastructure](./02_infrastructure_module.md)
   - SQL Schema (PostgreSQL)
   - Row Level Security (RLS)
   - SQLAlchemy Models
   - Repository Implementations
   - Redis Cache
   - Event Bus

4. [Адаптер Telegram](./03_telegram_adapter.md)
   - Bot Initialization
   - Callback Data
   - Inline Keyboards
   - Message Renderers
   - Handlers (Start, Match, Bet, Game, Profile)
   - FSM States
   - Middlewares (Auth, RateLimit)

5. [Адаптер VK](./04_vk_adapter.md)
   - Bot Initialization
   - Payloads (VK Callback)
   - VK Keyboards
   - VK Renderers
   - Handlers
   - Middlewares

6. [Адаптер Discord](./05_discord_adapter.md)
   - Bot Initialization
   - Discord Embeds
   - Discord Views (Buttons, Selects)
   - Cogs
   - Slash Commands

7. [REST API](./06_rest_api.md)
   - FastAPI App
   - API Schemas
   - Endpoints (Auth, Users, Matches, Bets, Leaderboard)
   - Dependencies (Auth, Database)
   - JWT Authentication

8. [Модуль Testing](./07_testing_module.md)
   - Pytest Configuration
   - Unit Tests (GameEngine, BetTracker, ScoreCalculator, WhistleDeck, BotAI)
   - Integration Tests (Repositories, Full Match)
   - Match Simulation Script

9. [Edge Cases](./08_edge_cases.md)
   - Ошибки валидации
   - Ошибки инфраструктуры
   - Состояния матча и переходы
   - Таймауты
   - Конкурентность
   - Восстановление после сбоев
   - Graceful Degradation

---

## Быстрый старт для субагентов

### Core Engineer

1. Прочитать [01_core_module.md](./01_core_module.md)
2. Реализовать модели в `src/core/models/`
3. Реализовать движок в `src/core/engine/`
4. Запустить тесты: `pytest tests/unit/core/ -v`

### Database Architect

1. Прочитать [02_infrastructure_module.md](./02_infrastructure_module.md)
2. Создать миграции в `src/infrastructure/db/migrations/`
3. Реализовать репозитории в `src/infrastructure/repositories/`
4. Запустить тесты: `pytest tests/integration/ -v`

### Platform Adapter (Telegram)

1. Прочитать [03_telegram_adapter.md](./03_telegram_adapter.md)
2. Реализовать в `src/platforms/telegram/`
3. Использовать готовые сервисы из `src/application/`

### Platform Adapter (VK)

1. Прочитать [04_vk_adapter.md](./04_vk_adapter.md)
2. Реализовать в `src/platforms/vk/`

### Platform Adapter (Discord)

1. Прочитать [05_discord_adapter.md](./05_discord_adapter.md)
2. Реализовать в `src/platforms/discord/`

### API Developer

1. Прочитать [06_rest_api.md](./06_rest_api.md)
2. Реализовать в `src/platforms/api/`

---

## Стек технологий

| Компонент | Технология | Версия |
|-----------|------------|--------|
| Language | Python | 3.11+ |
| Core Models | Pydantic | 2.x |
| Database | PostgreSQL | 15+ |
| ORM | SQLAlchemy | 2.0+ |
| Cache | Redis | 7+ |
| Telegram | aiogram | 3.x |
| VK | VKBottle | 4.x |
| Discord | discord.py | 2.x |
| REST API | FastAPI | 0.100+ |
| Tests | pytest | 7+ |
| Async | asyncio | stdlib |

---

## Критерии готовности

- [ ] Покрытие Core тестами > 80%
- [ ] Все SQL миграции созданы и протестированы
- [ ] Telegram адаптер работает через новую архитектуру
- [ ] VK адаптер работает
- [ ] Discord адаптер работает
- [ ] REST API документирован (OpenAPI)
- [ ] Симуляция матча проходит без ошибок
- [ ] Edge cases обработаны
