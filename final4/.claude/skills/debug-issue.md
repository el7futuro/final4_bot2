---
name: debug-issue
description: Отладка проблемы в коде
---

# Отладка проблемы

## 1. Воспроизведение
```bash
# Запустить тесты
pytest tests/ -v -x --tb=long

# Конкретный тест
pytest tests/unit/core/test_game_engine.py::TestGameEngine::test_roll_dice -v
```

## 2. Логирование
```python
import structlog
logger = structlog.get_logger()

logger.debug("debug_info", match_id=str(match.id), turn=match.current_turn)
```

## 3. Проверка данных
```bash
# Redis
redis-cli KEYS "session:*"
redis-cli GET "session:uuid"

# PostgreSQL
psql -c "SELECT * FROM matches WHERE id = 'uuid'"
```

## 4. Частые проблемы

### Изоляция Core нарушена
```bash
grep -r "import aiogram" src/core/
# Если найдено — перенести логику в адаптер
```

### Pydantic валидация
```python
# Проверить @model_validator
try:
    bet = Bet(bet_type=BetType.EVEN_ODD)
except ValidationError as e:
    print(e.errors())
```

### Асинхронность
```python
# Забыли await
result = repo.get_by_id(id)  # ❌ Coroutine object
result = await repo.get_by_id(id)  # ✅
```

### RLS не работает
```sql
-- Проверить политики
SELECT * FROM pg_policies WHERE tablename = 'matches';

-- Установить контекст
SET app.current_user_id = 'uuid';
```

## 5. Пошаговая отладка
```python
import pdb; pdb.set_trace()
# или
breakpoint()
```

## 6. Проверка после фикса
```bash
# Все тесты
pytest tests/ -v

# Покрытие
pytest --cov=src/core --cov-report=html
open htmlcov/index.html
```
