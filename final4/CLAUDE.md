# Final 4 — Мультиплатформенная стратегическая игра

## Обзор
Пошаговая игра с механикой ставок на броски кубика. Чистая архитектура: Core изолирован от платформ.

## Стек
- **Core**: Python 3.11+, Pydantic v2
- **БД**: PostgreSQL 15+, SQLAlchemy 2.0 (async)
- **Кэш**: Redis
- **Telegram**: aiogram 3.x
- **VK**: VKBottle
- **Discord**: discord.py
- **Тесты**: pytest + pytest-asyncio + pytest-cov

## Архитектура
```
src/
├── core/           # Чистая бизнес-логика (НЕТ импортов aiogram/vkbottle/discord)
├── infrastructure/ # БД, кэш, репозитории, события
├── platforms/      # Адаптеры (telegram/, vk/, discord/)
└── shared/         # Общие утилиты
```

## Правила
- **Core запрещено импортировать из infrastructure или platforms**
- Все тесты проходят без запуска ботов
- Покрытие core тестами >80%
- RLS включен для всех таблиц

## Команды
```bash
pytest tests/unit/              # тесты core
pytest tests/integration/       # тесты с БД
python scripts/simulate_match.py # симуляция матча
alembic upgrade head            # миграции
```

## Субагенты
См. `.claude/agents/` — database-architect, core-engineer, platform-adapter, qa-reviewer

## Спецификации
Полная документация в `docs/specs/`:
- `00_architecture_overview.md` — архитектура
- `01_core_module.md` — Core модуль
- `02_infrastructure_module.md` — БД и Redis
- `03_telegram_adapter.md` — Telegram
- `04_vk_adapter.md` — VK
- `05_discord_adapter.md` — Discord
- `06_rest_api.md` — REST API
- `07_testing_module.md` — тесты
- `08_edge_cases.md` — edge cases

## Игровые правила (кратко)
- 16 игроков в команде (1 вратарь, 5 защитников, 6 полузащитников, 4 форварда)
- 11 на поле, 7 формаций
- Ставки: чёт/нечёт → отбития, больше/меньше → передачи, точное число → гол
- Победа: передачи ломают отбития, оставшиеся голы засчитываются
- При ничьей: дополнительное время → пенальти → жребий

## Зависимости
```
pydantic>=2.0
sqlalchemy[asyncio]>=2.0
asyncpg
redis
aiogram>=3.0
vkbottle>=4.0
discord.py>=2.0
pytest>=7.0
pytest-asyncio
pytest-cov
alembic
```
