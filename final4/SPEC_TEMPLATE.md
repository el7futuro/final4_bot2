# Спецификация фичи: [НАЗВАНИЕ]

## Описание
[Краткое описание: что делает, для кого, зачем]

## User Stories
- Как **[роль]**, я хочу **[действие]**, чтобы **[результат]**
- Как игрок, я хочу ..., чтобы ...

## Модель данных

### Новые таблицы
```sql
CREATE TABLE new_feature (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- поля
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_new_feature_user ON new_feature(user_id);
ALTER TABLE new_feature ENABLE ROW LEVEL SECURITY;
```

### Изменения существующих таблиц
```sql
ALTER TABLE matches ADD COLUMN new_field TYPE;
```

## Pydantic модели
```python
class NewFeature(BaseModel):
    id: UUID
    user_id: UUID
    # поля

    @model_validator(mode='after')
    def validate(self) -> 'NewFeature':
        # валидация
        return self
```

## API / Команды

### Telegram
- `/command` — описание
- Callback: `feature_action_{id}` — описание

### VK
- Payload: `{"action": "feature", "feature_action": "..."}`

### Discord
- Slash: `/command` — описание
- Button: `feature_action`

### REST API
```
POST /api/v1/feature
GET /api/v1/feature/{id}
```

## Экраны / Сообщения

### Главный экран фичи
```
[Emoji] Заголовок

Описание состояния

[Кнопка 1] [Кнопка 2]
```

### Сообщения об ошибках
- Ошибка X: "Текст сообщения"

## Бизнес-логика

### Правила
1. Правило 1
2. Правило 2

### Валидация
- Поле X: диапазон/формат
- Связь с другими сущностями

### Формулы
```
результат = (A - B) / C
```

## Edge Cases

| Ситуация | Ожидаемое поведение |
|----------|---------------------|
| Нет данных | Показать placeholder |
| Таймаут | Retry 3 раза |
| Конкурентный доступ | Optimistic locking |

## Зависимости

### От каких модулей зависит
- `core/models/...`
- `core/engine/...`

### Какие фичи блокирует
- Фича Y не может быть реализована без этой

## Приоритет
- [ ] P0 — критично для MVP
- [ ] P1 — важно
- [ ] P2 — желательно

## Оценка трудозатрат
- Core: X часов
- Infrastructure: X часов
- Adapters: X часов
- Tests: X часов
- **Итого**: X часов
