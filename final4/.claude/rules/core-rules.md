---
glob: src/core/**/*.py
---

# Правила для Core

## 1. Запрещённые импорты
```python
# ❌ ЗАПРЕЩЕНО
import aiogram
from aiogram import ...
import vkbottle
from vkbottle import ...
import discord
from discord import ...
import sqlalchemy
from sqlalchemy import ...
```

## 2. Разрешённые импорты
```python
# ✅ РАЗРЕШЕНО
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple, Any
from enum import Enum
from dataclasses import dataclass
import random
import json

from pydantic import BaseModel, Field, model_validator, field_validator
```

## 3. Обязательные аннотации типов
Все методы и функции должны иметь аннотации:
```python
# ✅ Правильно
def calculate_score(self, team1: Team, team2: Team) -> MatchScore:
    ...

# ❌ Неправильно
def calculate_score(self, team1, team2):
    ...
```

## 4. Валидация Pydantic
Все модели должны использовать валидаторы:
```python
class Bet(BaseModel):
    bet_type: BetType
    exact_number: Optional[int] = None

    @model_validator(mode='after')
    def validate_bet_value(self) -> 'Bet':
        if self.bet_type == BetType.EXACT_NUMBER and self.exact_number is None:
            raise ValueError("exact_number обязателен")
        return self
```

## 5. Документация
Все публичные методы должны иметь docstring:
```python
def roll_dice(self, match: Match, manager_id: UUID) -> Tuple[Match, int, List[Bet]]:
    """
    Бросить кубик и определить результаты ставок.
    
    Args:
        match: Текущий матч
        manager_id: ID менеджера, бросающего кубик
    
    Returns:
        Tuple[Match, int, List[Bet]]: (обновлённый матч, значение кубика, выигравшие ставки)
    
    Raises:
        ValueError: Если сейчас не ход этого менеджера
    """
```

## 6. Именование
- Классы: PascalCase (GameEngine, BetTracker)
- Методы/функции: snake_case (calculate_score, roll_dice)
- Константы: UPPER_SNAKE_CASE (BOT_USER_ID, CARD_DISTRIBUTION)
- Enum значения: UPPER_SNAKE_CASE (MatchStatus.IN_PROGRESS)
