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

## Файлы спецификации

- `/app/docs/specs/README.md` — индекс
- `/app/docs/specs/00_architecture_overview.md` — архитектура
- `/app/docs/specs/01_core_module.md` — Core модуль
- `/app/docs/specs/02_infrastructure_module.md` — инфраструктура
- `/app/docs/specs/03_telegram_adapter.md` — Telegram
- `/app/docs/specs/04_vk_adapter.md` — VK
- `/app/docs/specs/05_discord_adapter.md` — Discord
- `/app/docs/specs/06_rest_api.md` — REST API
- `/app/docs/specs/07_testing_module.md` — тестирование
- `/app/docs/specs/08_edge_cases.md` — edge cases
