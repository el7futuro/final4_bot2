# Настройка окружения Final 4

## Быстрый старт (Docker)

```bash
# 1. Запустить PostgreSQL и Redis
cd /app/final4
docker-compose up -d

# 2. Проверить статус
docker-compose ps
# Должно быть: postgres (healthy), redis (healthy)

# 3. Скопировать .env
cp .env.example .env
# Заполнить токены ботов!
```

## Ручная установка

### PostgreSQL

```bash
# macOS
brew install postgresql@15
brew services start postgresql@15

# Ubuntu
sudo apt install postgresql-15
sudo systemctl start postgresql

# Создать БД
psql -U postgres
CREATE USER final4 WITH PASSWORD 'final4_password';
CREATE DATABASE final4 OWNER final4;
\c final4
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### Redis

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu
sudo apt install redis-server
sudo systemctl start redis
```

## Проверка

```bash
# PostgreSQL
pg_isready -h localhost -p 5432
# /var/run/postgresql:5432 - accepting connections

# Redis
redis-cli ping
# PONG
```

## Миграции

```bash
# После запуска PostgreSQL
cd /app/final4
alembic upgrade head
```

## Токены ботов

| Платформа | Где получить |
|-----------|--------------|
| Telegram | https://t.me/BotFather → /newbot |
| VK | https://vk.com/dev → Создать приложение |
| Discord | https://discord.com/developers/applications |

## Конфигурация субагентов

| Субагент | Модель | Write | Описание |
|----------|--------|-------|----------|
| database-architect | **opus** | ✅ | SQL, миграции, RLS |
| core-engineer | **opus** | ✅ | Pydantic, движки |
| platform-adapter | sonnet | ✅ | Telegram/VK/Discord |
| qa-reviewer | sonnet | ❌ | Только проверка |

## Запуск разработки

```bash
# Тесты
pytest tests/unit/ -v

# Симуляция матча
python scripts/simulate_match.py --verbose

# Telegram бот (после заполнения .env)
python -m src.platforms.telegram.bot
```
