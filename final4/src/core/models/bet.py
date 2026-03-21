# src/core/models/bet.py
"""Модель ставки"""

from enum import Enum
from uuid import UUID, uuid4
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class BetType(str, Enum):
    """Типы ставок"""
    EVEN_ODD = "even_odd"           # Чёт/нечет -> отбития
    HIGH_LOW = "high_low"           # Больше/меньше -> передачи
    EXACT_NUMBER = "exact_number"   # Точное число -> гол


class EvenOddChoice(str, Enum):
    EVEN = "even"   # Чётное (2, 4, 6)
    ODD = "odd"     # Нечётное (1, 3, 5)


class HighLowChoice(str, Enum):
    LOW = "low"     # 1-3 (Меньше)
    HIGH = "high"   # 4-6 (Больше)


class BetOutcome(str, Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"


class Bet(BaseModel):
    """Ставка менеджера на футболиста"""
    id: UUID = Field(default_factory=uuid4)
    match_id: UUID
    manager_id: UUID
    player_id: UUID
    turn_number: int = Field(ge=1)
    bet_type: BetType
    
    # Значение ставки зависит от типа
    even_odd_choice: Optional[EvenOddChoice] = None
    high_low_choice: Optional[HighLowChoice] = None
    exact_number: Optional[int] = Field(default=None, ge=1, le=6)
    
    dice_roll: Optional[int] = Field(default=None, ge=1, le=6)
    outcome: BetOutcome = Field(default=BetOutcome.PENDING)

    @model_validator(mode='after')
    def validate_bet_value(self) -> 'Bet':
        if self.bet_type == BetType.EVEN_ODD and self.even_odd_choice is None:
            raise ValueError("even_odd_choice обязателен для EVEN_ODD ставки")
        if self.bet_type == BetType.HIGH_LOW and self.high_low_choice is None:
            raise ValueError("high_low_choice обязателен для HIGH_LOW ставки")
        if self.bet_type == BetType.EXACT_NUMBER and self.exact_number is None:
            raise ValueError("exact_number обязателен для EXACT_NUMBER ставки")
        return self

    def resolve(self, dice_roll: int) -> BetOutcome:
        """Определить результат ставки по броску кубика"""
        self.dice_roll = dice_roll
        
        if self.bet_type == BetType.EVEN_ODD:
            is_even = dice_roll % 2 == 0
            won = (self.even_odd_choice == EvenOddChoice.EVEN and is_even) or \
                  (self.even_odd_choice == EvenOddChoice.ODD and not is_even)
        
        elif self.bet_type == BetType.HIGH_LOW:
            is_high = dice_roll >= 4
            won = (self.high_low_choice == HighLowChoice.HIGH and is_high) or \
                  (self.high_low_choice == HighLowChoice.LOW and not is_high)
        
        elif self.bet_type == BetType.EXACT_NUMBER:
            won = self.exact_number == dice_roll
        
        else:
            won = False
        
        self.outcome = BetOutcome.WON if won else BetOutcome.LOST
        return self.outcome

    def get_display_value(self) -> str:
        """Получить отображаемое значение ставки"""
        if self.bet_type == BetType.EVEN_ODD:
            return "Чёт" if self.even_odd_choice == EvenOddChoice.EVEN else "Нечёт"
        elif self.bet_type == BetType.HIGH_LOW:
            return "1-3" if self.high_low_choice == HighLowChoice.LOW else "4-6"
        elif self.bet_type == BetType.EXACT_NUMBER:
            return str(self.exact_number)
        return ""
