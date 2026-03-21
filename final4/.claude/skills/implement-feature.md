---
name: implement-feature
description: Реализация новой фичи от спецификации до тестов
---

# Шаги реализации фичи

## 1. Анализ спецификации
```bash
# Прочитать спецификацию в docs/specs/
cat docs/specs/SPEC_TEMPLATE.md
cat docs/specs/01_core_module.md
```

## 2. Core модели (core-engineer)
```bash
# Создать Pydantic-модели
touch src/core/models/new_feature.py
# Валидаторы, типы, методы
```

## 3. Core движок (core-engineer)
```bash
# Добавить логику в существующий движок или создать новый
edit src/core/engine/game_engine.py
# Или создать новый
touch src/core/engine/new_engine.py
```

## 4. Интерфейс репозитория (core-engineer)
```python
# src/core/interfaces/repositories.py
class INewRepository(ABC):
    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[Model]:
        pass
```

## 5. SQL миграция (database-architect)
```bash
alembic revision -m "add_new_feature_table"
# Добавить CREATE TABLE, индексы, RLS
```

## 6. Репозиторий (database-architect)
```bash
touch src/infrastructure/repositories/new_repository.py
# Реализовать интерфейс
```

## 7. Unit-тесты (core-engineer)
```bash
touch tests/unit/core/test_new_feature.py
pytest tests/unit/core/test_new_feature.py -v
```

## 8. Integration-тесты
```bash
touch tests/integration/test_new_repository.py
pytest tests/integration/ -v
```

## 9. Адаптеры (platform-adapter)
```bash
# Telegram
touch src/platforms/telegram/handlers/new_feature.py
# VK
touch src/platforms/vk/handlers/new_feature.py
# Discord
touch src/platforms/discord/cogs/new_feature.py
```

## 10. Review (qa-reviewer)
```bash
# Проверка изоляции
grep -r "import aiogram" src/core/
# Покрытие
pytest --cov=src/core --cov-report=term-missing
```

## Чеклист готовности
- [ ] Pydantic-модели с валидацией
- [ ] Движок с бизнес-логикой
- [ ] Интерфейс репозитория
- [ ] SQL миграция с RLS
- [ ] Реализация репозитория
- [ ] Unit-тесты (>80%)
- [ ] Integration-тесты
- [ ] Адаптеры для платформ
- [ ] QA review пройден
