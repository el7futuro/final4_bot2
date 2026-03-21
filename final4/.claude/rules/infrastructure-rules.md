---
glob: src/infrastructure/**/*.py
---

# Правила для Infrastructure

## 1. Репозитории
Все репозитории реализуют интерфейсы из `core.interfaces`:
```python
from src.core.interfaces.repositories import IUserRepository

class UserRepository(IUserRepository):
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        ...
```

## 2. Асинхронность
Все методы репозиториев — асинхронные:
```python
# ✅ Правильно
async def get_by_id(self, user_id: UUID) -> Optional[User]:
    result = await self.session.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    return self._to_domain(result.scalar_one_or_none())

# ❌ Неправильно
def get_by_id(self, user_id: UUID) -> Optional[User]:
    ...
```

## 3. Сессии БД
Использовать контекстный менеджер:
```python
class Database:
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
```

## 4. Маппинг Domain ↔ ORM
Отдельные методы для конвертации:
```python
def _to_domain(self, model: UserModel) -> User:
    """Конвертация ORM → Domain"""
    return User(
        id=model.id,
        username=model.username,
        ...
    )

def _to_model(self, user: User) -> UserModel:
    """Конвертация Domain → ORM"""
    return UserModel(
        id=user.id,
        username=user.username,
        ...
    )
```

## 5. Redis
TTL обязателен для всех ключей:
```python
# ✅ Правильно
await self.redis.set_json(key, data, expire=3600)

# ❌ Неправильно
await self.redis.set(key, data)  # Нет TTL
```

## 6. Миграции
Идемпотентные скрипты:
```sql
-- ✅ Правильно
CREATE TABLE IF NOT EXISTS users (...);
CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id);

-- ❌ Неправильно
CREATE TABLE users (...);  -- Упадёт при повторном запуске
```

## 7. RLS
Включать для всех таблиц:
```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY users_select_own ON users
    FOR SELECT
    USING (id = current_setting('app.current_user_id')::uuid);
```
