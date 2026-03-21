---
name: create-migration
description: Создание миграции БД через Alembic
---

# Создание миграции

## 1. Создать файл миграции
```bash
alembic revision -m "описание_изменения"
# Создаст: src/infrastructure/db/migrations/versions/xxx_описание.py
```

## 2. Структура миграции
```python
"""описание изменения

Revision ID: xxx
Revises: yyy
Create Date: 2026-01-XX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'xxx'
down_revision = 'yyy'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Расширения
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # Создание таблицы
    op.create_table(
        'new_table',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('data', JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    
    # Индексы
    op.create_index('idx_new_table_user_id', 'new_table', ['user_id'])
    
    # RLS
    op.execute('ALTER TABLE new_table ENABLE ROW LEVEL SECURITY')
    op.execute('''
        CREATE POLICY new_table_select_own ON new_table
        FOR SELECT
        USING (user_id = current_setting('app.current_user_id')::uuid)
    ''')


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS new_table_select_own ON new_table')
    op.drop_index('idx_new_table_user_id')
    op.drop_table('new_table')
```

## 3. Паттерны

### JSONB с валидацией
```python
op.execute('''
    ALTER TABLE teams
    ADD CONSTRAINT teams_players_valid
    CHECK (jsonb_typeof(players) = 'array')
''')
```

### Триггер updated_at
```python
op.execute('''
    CREATE TRIGGER new_table_updated_at
    BEFORE UPDATE ON new_table
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column()
''')
```

### Сервисная роль
```python
op.execute('GRANT ALL ON new_table TO final4_service')
```

## 4. Проверка
```bash
# Применить
alembic upgrade head

# Откатить
alembic downgrade -1

# Снова применить (идемпотентность)
alembic upgrade head

# Проверить RLS
psql -c "\d new_table"
psql -c "SELECT * FROM pg_policies WHERE tablename = 'new_table'"
```

## 5. Чеклист
- [ ] IF NOT EXISTS для CREATE
- [ ] Индексы для внешних ключей
- [ ] RLS включен
- [ ] Политики настроены
- [ ] downgrade() работает
- [ ] Повторное применение не падает
