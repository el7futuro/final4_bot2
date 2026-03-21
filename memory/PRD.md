# Final 4 — Product Requirements Document

## Оригинальное задание

Проект: "Финал 4" — пошаговая стратегическая игра.
Текущее состояние: код привязан к Telegram, есть циклические импорты, смешана бизнес-логика и presentation-слой.
Цель: спроектировать новую архитектуру "с чистого листа".

## Архитектура

Clean Architecture с 4 слоями:
1. **Core (Domain)** — чистая бизнес-логика без зависимостей от фреймворков
2. **Application** — сервисы, координация
3. **Infrastructure** — БД, кэш, события
4. **Platforms** — адаптеры для Telegram, VK, Discord, REST API

## Целевые платформы

- Telegram (aiogram 3.x)
- VK (VKBottle)
- Discord (discord.py)
- REST API (FastAPI)

## Требования к инфраструктуре

- PostgreSQL с RLS (Row Level Security)
- Redis для кэша и сессий
- Асинхронная обработка

## Что реализовано

### Дата: Январь 2026

- [x] Техническая спецификация создана
- [x] Структура модулей определена
- [x] Pydantic схемы спроектированы
- [x] SQL схема с RLS
- [x] Интерфейсы репозиториев
- [x] GameEngine спроектирован
- [x] BetTracker спроектирован
- [x] ScoreCalculator спроектирован
- [x] WhistleDeck спроектирован
- [x] Bot AI спроектирован
- [x] Telegram адаптер спроектирован
- [x] VK адаптер спроектирован
- [x] Discord адаптер спроектирован
- [x] REST API спроектирован
- [x] Тесты спроектированы
- [x] Edge cases описаны
- [x] **CLAUDE.md конфиг создан**
- [x] **Субагенты настроены (database-architect, core-engineer, platform-adapter, qa-reviewer)**
- [x] **Rules для core/infrastructure/platforms**
- [x] **Skills (implement-feature, create-migration, debug-issue)**
- [x] **SPEC_TEMPLATE.md для новых фич**

## Backlog (P0 — критично)

- [ ] Реализация Core модуля
- [ ] Создание SQL миграций
- [ ] Реализация репозиториев
- [ ] Telegram адаптер
- [ ] Покрытие тестами > 80%

## Backlog (P1 — важно)

- [ ] VK адаптер
- [ ] Discord адаптер
- [ ] REST API
- [ ] Симуляция матчей

## Backlog (P2 — желательно)

- [ ] Турниры
- [ ] Расширенная статистика
- [ ] Мобильное приложение
- [ ] Premium функции

## Структура проекта Final 4

```
final4/
├── CLAUDE.md                    # Главный конфиг Claude Code
├── SPEC_TEMPLATE.md             # Шаблон для новых фич
├── .claude/
│   ├── agents/
│   │   ├── database-architect.md
│   │   ├── core-engineer.md
│   │   ├── platform-adapter.md
│   │   └── qa-reviewer.md
│   ├── rules/
│   │   ├── core-rules.md
│   │   ├── infrastructure-rules.md
│   │   └── platforms-rules.md
│   └── skills/
│       ├── implement-feature.md
│       ├── create-migration.md
│       └── debug-issue.md
└── docs/
    ├── README.md
    ├── 00_architecture_overview.md
    ├── 01_core_module.md
    ├── 02_infrastructure_module.md
    ├── 03_telegram_adapter.md
    ├── 04_vk_adapter.md
    ├── 05_discord_adapter.md
    ├── 06_rest_api.md
    ├── 07_testing_module.md
    └── 08_edge_cases.md
```

## Файлы спецификации

- `/app/final4/docs/README.md` — индекс
- `/app/final4/docs/00_architecture_overview.md` — архитектура
- `/app/final4/docs/01_core_module.md` — Core модуль
- `/app/final4/docs/02_infrastructure_module.md` — инфраструктура
- `/app/final4/docs/03_telegram_adapter.md` — Telegram
- `/app/final4/docs/04_vk_adapter.md` — VK
- `/app/final4/docs/05_discord_adapter.md` — Discord
- `/app/final4/docs/06_rest_api.md` — REST API
- `/app/final4/docs/07_testing_module.md` — тестирование
- `/app/final4/docs/08_edge_cases.md` — edge cases
