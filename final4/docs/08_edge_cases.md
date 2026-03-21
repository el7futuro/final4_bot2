# Edge Cases и обработка ошибок

## Обзор

Документ описывает все граничные случаи и их обработку в системе.

---

## 1. Ошибки валидации (бизнес-логика)

### 1.1 Матчи

| Ситуация | Ошибка | Код HTTP | Обработка |
|----------|--------|----------|-----------|
| Попытка присоединиться к своему матчу | `ValueError: "Нельзя играть против себя"` | 400 | Показать сообщение, вернуть в меню |
| Матч уже имеет соперника | `ValueError: "Матч уже имеет соперника"` | 400 | Предложить другой матч |
| Матч отменён | `ValueError: "Матч отменён"` | 400 | Вернуть в меню |
| Превышен лимит матчей в день | `ValueError: "Daily limit reached"` | 429 | Показать время до сброса |
| Пользователь забанен | `ValueError: "User banned"` | 403 | Показать причину бана |

### 1.2 Ставки

| Ситуация | Ошибка | Код HTTP | Обработка |
|----------|--------|----------|-----------|
| Не ваш ход | `ValueError: "Сейчас не ваш ход"` | 400 | Показать чей ход |
| Игрок не на поле | `ValueError: "Игрок не на поле"` | 400 | Показать состав |
| Форвард + чёт/нечёт | `ValueError: "Форварды не могут иметь ставку на чёт/нечёт"` | 400 | Показать доступные типы |
| Превышен лимит ставок на чёт/нечёт | `ValueError: "Максимум 6 ставок на чёт/нечёт"` | 400 | Показать текущий счёт |
| Лимит голевых ставок защитников | `ValueError: "Только 1 защитник может иметь ставку на гол"` | 400 | Показать кто уже имеет |
| Вратарь + ставка на гол | `ValueError: "Вратарь не может иметь ставку на гол"` | 400 | Предложить чёт/нечёт |
| Кубик уже брошен | `ValueError: "Кубик уже брошен в этот ход"` | 400 | Показать результат |

### 1.3 Состав

| Ситуация | Ошибка | Код HTTP | Обработка |
|----------|--------|----------|-----------|
| Невалидное количество игроков | `ValueError: "Необходимо выбрать 11 игроков"` | 400 | Показать текущий выбор |
| Несоответствие формации | `ValueError: "Невалидный состав для формации"` | 400 | Показать требования |
| Игрок недоступен (удалён) | `ValueError: "Игрок недоступен"` | 400 | Показать доступных |

---

## 2. Ошибки инфраструктуры

### 2.1 База данных

| Ситуация | Обработка |
|----------|-----------|
| Соединение потеряно | Retry 3 раза с exponential backoff |
| Deadlock | Retry транзакции |
| Unique constraint violation | Логика merge/update |
| Timeout | Отмена операции, уведомление пользователя |

```python
# Пример retry декоратора
from functools import wraps
import asyncio

def db_retry(max_retries=3, base_delay=0.1):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (ConnectionError, TimeoutError) as e:
                    last_exception = e
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator
```

### 2.2 Redis

| Ситуация | Обработка |
|----------|-----------|
| Соединение потеряно | Graceful degradation (работа без кэша) |
| Данные истекли | Регенерация из БД |
| Rate limit достигнут | Возврат 429 с Retry-After |

### 2.3 Внешние сервисы (платформы)

| Ситуация | Обработка |
|----------|-----------|
| Telegram API timeout | Retry + очередь сообщений |
| VK API rate limit | Очередь с throttling |
| Discord API error | Логирование + уведомление админа |

---

## 3. Состояния матча и переходы

### 3.1 Диаграмма состояний

```
WAITING_FOR_OPPONENT
    │
    ├─[opponent joins]──► SETTING_LINEUP
    │                         │
    ├─[timeout 30m]──────► CANCELLED
    │                         │
    └─[creator cancels]──► CANCELLED
                             │
                             ├─[both ready]──► IN_PROGRESS
                             │                     │
                             └─[timeout 10m]──► CANCELLED
                                                  │
                                ┌─────────────────┴─────────────────┐
                                │                                   │
                                ▼                                   │
                           IN_PROGRESS                              │
                                │                                   │
                    ┌───────────┴───────────┐                      │
                    │                       │                      │
                    ▼                       ▼                      │
              [winner decided]      [draw at end]                  │
                    │                       │                      │
                    ▼                       ▼                      │
               FINISHED              EXTRA_TIME                    │
                                          │                        │
                            ┌─────────────┴─────────────┐         │
                            │                           │         │
                            ▼                           ▼         │
                      [winner]                    [still draw]    │
                            │                           │         │
                            ▼                           ▼         │
                       FINISHED                    PENALTIES      │
                                                       │          │
                                          ┌────────────┴──────────┤
                                          │                       │
                                          ▼                       │
                                    [winner/lottery]              │
                                          │                       │
                                          ▼                       │
                                     FINISHED                     │
                                                                  │
                                [player disconnects]──────────────┘
                                          │
                                          ▼
                                     CANCELLED (forfeit)
```

### 3.2 Таймауты

| Фаза | Таймаут | Действие |
|------|---------|----------|
| WAITING_FOR_OPPONENT | 30 минут | Автоотмена |
| SETTING_LINEUP | 10 минут | Автоотмена или forfeit |
| Ход игрока | 3 минуты | Автоматический random ход |
| Inactive match | 24 часа | Автоотмена |

---

## 4. Конкурентность

### 4.1 Race conditions

| Ситуация | Решение |
|----------|---------|
| Два игрока присоединяются одновременно | Optimistic locking с version |
| Двойной клик на кнопку ставки | Идемпотентность через bet_id |
| Параллельные броски кубика | Mutex на уровне матча в Redis |

```python
# Пример distributed lock
class MatchLock:
    def __init__(self, redis: RedisClient, match_id: UUID, timeout: int = 30):
        self.redis = redis
        self.key = f"lock:match:{match_id}"
        self.timeout = timeout
        self.token = str(uuid4())
    
    async def __aenter__(self):
        acquired = await self.redis.redis.set(
            self.key,
            self.token,
            nx=True,
            ex=self.timeout
        )
        if not acquired:
            raise ConcurrencyError("Match is locked by another operation")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Release only if we own the lock
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        await self.redis.redis.eval(script, 1, self.key, self.token)
```

### 4.2 Консистентность данных

```python
# Пример транзакции с проверкой версии
async def update_match_with_version(
    session: AsyncSession,
    match_id: UUID,
    expected_version: int,
    updates: dict
) -> Match:
    result = await session.execute(
        update(MatchModel)
        .where(
            and_(
                MatchModel.id == match_id,
                MatchModel.version == expected_version
            )
        )
        .values(**updates, version=expected_version + 1)
        .returning(MatchModel)
    )
    
    updated = result.scalar_one_or_none()
    if not updated:
        raise ConcurrencyError("Match was modified by another process")
    
    return _to_domain(updated)
```

---

## 5. Восстановление после сбоев

### 5.1 Сценарии восстановления

| Сбой | Восстановление |
|------|----------------|
| Сервер упал во время хода | Checkpoint в Redis, восстановление из snapshot |
| БД недоступна | Очередь записи, replay при восстановлении |
| Потеря сообщения платформы | Retry queue с deduplication |

### 5.2 Checkpoint система

```python
# Сохранение состояния в Redis при каждом действии
class MatchCheckpoint:
    PREFIX = "checkpoint:match:"
    
    async def save(self, match: Match) -> None:
        await self.redis.set_json(
            f"{self.PREFIX}{match.id}",
            {
                "match_state": match.model_dump(),
                "timestamp": datetime.utcnow().isoformat(),
                "last_action": match.current_turn.turn_number if match.current_turn else 0
            },
            expire=86400  # 24 hours
        )
    
    async def restore(self, match_id: UUID) -> Optional[Match]:
        data = await self.redis.get_json(f"{self.PREFIX}{match_id}")
        if data:
            return Match(**data["match_state"])
        return None
```

---

## 6. Валидация входных данных

### 6.1 Pydantic валидация

```python
from pydantic import BaseModel, Field, validator

class PlaceBetRequest(BaseModel):
    player_id: UUID
    bet_type: BetType
    value: str
    
    @validator('value')
    def validate_value_for_type(cls, v, values):
        bet_type = values.get('bet_type')
        
        if bet_type == BetType.EVEN_ODD:
            if v not in ['even', 'odd']:
                raise ValueError("value must be 'even' or 'odd' for even_odd bet")
        
        elif bet_type == BetType.HIGH_LOW:
            if v not in ['low', 'high']:
                raise ValueError("value must be 'low' or 'high' for high_low bet")
        
        elif bet_type == BetType.EXACT_NUMBER:
            try:
                num = int(v)
                if not 1 <= num <= 6:
                    raise ValueError("exact_number must be 1-6")
            except ValueError:
                raise ValueError("value must be a number 1-6 for exact_number bet")
        
        return v
```

### 6.2 Санитизация

```python
import re
from html import escape

def sanitize_username(name: str) -> str:
    """Очистка username от опасных символов"""
    # Remove HTML
    name = escape(name)
    # Remove control characters
    name = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', name)
    # Limit length
    name = name[:50]
    # Remove leading/trailing whitespace
    name = name.strip()
    return name or "Anonymous"
```

---

## 7. Логирование ошибок

### 7.1 Структура логов

```python
import structlog
from uuid import UUID
from datetime import datetime

logger = structlog.get_logger()

class GameLogger:
    @staticmethod
    def log_error(
        error: Exception,
        match_id: UUID = None,
        user_id: UUID = None,
        action: str = None,
        context: dict = None
    ):
        logger.error(
            "game_error",
            error_type=type(error).__name__,
            error_message=str(error),
            match_id=str(match_id) if match_id else None,
            user_id=str(user_id) if user_id else None,
            action=action,
            context=context or {},
            timestamp=datetime.utcnow().isoformat()
        )
    
    @staticmethod
    def log_match_event(
        event_type: str,
        match_id: UUID,
        user_id: UUID,
        data: dict
    ):
        logger.info(
            "match_event",
            event_type=event_type,
            match_id=str(match_id),
            user_id=str(user_id),
            data=data,
            timestamp=datetime.utcnow().isoformat()
        )
```

### 7.2 Мониторинг

| Метрика | Описание | Alert threshold |
|---------|----------|-----------------|
| `match_errors_total` | Общее количество ошибок | > 10/min |
| `match_duration_seconds` | Длительность матча | > 2 hours |
| `bet_validation_failures` | Ошибки валидации ставок | > 100/hour |
| `db_connection_errors` | Ошибки БД | > 5/min |
| `redis_errors` | Ошибки Redis | > 10/min |

---

## 8. Graceful Degradation

### 8.1 Режимы работы

| Режим | Описание | Доступные функции |
|-------|----------|-------------------|
| **Full** | Все системы работают | Все |
| **No Cache** | Redis недоступен | Игра (медленнее), нет rate limiting |
| **Read Only** | БД только на чтение | Просмотр статистики, нет новых матчей |
| **Maintenance** | Плановое обслуживание | Только уведомления |

### 8.2 Feature flags

```python
class FeatureFlags:
    def __init__(self, redis: RedisClient):
        self.redis = redis
    
    async def is_enabled(self, feature: str) -> bool:
        value = await self.redis.get(f"feature:{feature}")
        return value == "1"
    
    # Примеры флагов
    MATCHMAKING_ENABLED = "matchmaking"
    TOURNAMENTS_ENABLED = "tournaments"
    BOT_MATCHES_ENABLED = "bot_matches"
    PREMIUM_FEATURES = "premium"
```
