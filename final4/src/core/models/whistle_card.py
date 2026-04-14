# src/core/models/whistle_card.py
"""Модель карточек Свисток"""

from enum import Enum
from uuid import UUID, uuid4
from typing import Optional
from pydantic import BaseModel, Field


class CardType(str, Enum):
    """Типы карточек Свисток"""
    HAT_TRICK = "hat_trick"       # Хэт-трик: +3 гола
    DOUBLE = "double"             # Дубль: +2 гола
    GOAL = "goal"                 # Гол: +1 гол
    OWN_GOAL = "own_goal"         # Автогол: соперник +1 гол
    VAR = "var"                   # ВАР: отмена карточки соперника
    OFFSIDE = "offside"           # Офсайд: отмена гола соперника
    PENALTY = "penalty"           # Пенальти: доп. бросок
    RED_CARD = "red_card"         # Удаление: игрок теряет все действия
    YELLOW_CARD = "yellow_card"   # Предупреждение: -1 действие
    FOUL = "foul"                 # Фол: -1 отбитие
    LOSS = "loss"                 # Потеря: -1 передача
    INTERCEPTION = "interception" # Перехват: +1 передача
    TACKLE = "tackle"             # Отбор: +1 отбитие


# Количество карточек каждого типа в колоде (всего 50)
CARD_DISTRIBUTION = {
    CardType.HAT_TRICK: 1,      # Хэт-трик: +3 гола
    CardType.DOUBLE: 1,         # Дубль: +2 гола
    CardType.GOAL: 2,           # Гол: +1 гол
    CardType.OWN_GOAL: 2,       # Автогол: +1 гол сопернику
    CardType.VAR: 2,            # ВАР: отменяет карточку соперника
    CardType.OFFSIDE: 2,        # Офсайд: отменяет гол соперника
    CardType.PENALTY: 3,        # Пенальти: интерактивный розыгрыш
    CardType.RED_CARD: 2,       # Удаление: все действия = 0
    CardType.YELLOW_CARD: 3,    # Предупреждение: -1 действие
    CardType.FOUL: 8,           # Фол: -1 отбитие
    CardType.LOSS: 8,           # Потеря: -1 передача
    CardType.INTERCEPTION: 8,   # Перехват: +1 передача
    CardType.TACKLE: 8,         # Отбор: +1 отбитие
}
# Всего: 1+1+2+2+2+2+3+2+3+8+8+8+8 = 50 карточек


class CardTarget(str, Enum):
    """Цель применения карточки"""
    SELF_PLAYER = "self_player"
    OPPONENT_PLAYER = "opponent_player"
    SELF_TEAM = "self_team"
    OPPONENT_TEAM = "opponent_team"


# Карточки и их цели
# ИСПРАВЛЕНО: По правилам игры
CARD_TARGETS = {
    # Позитивные для СВОЕГО игрока текущего хода
    CardType.HAT_TRICK: CardTarget.SELF_PLAYER,      # +3 гола своему
    CardType.DOUBLE: CardTarget.SELF_PLAYER,         # +2 гола своему
    CardType.GOAL: CardTarget.SELF_PLAYER,           # +1 гол своему
    CardType.INTERCEPTION: CardTarget.SELF_PLAYER,   # +1 передача своему
    CardType.TACKLE: CardTarget.SELF_PLAYER,         # +1 отбитие своему
    
    # Негативные для СВОЕГО игрока текущего хода
    CardType.FOUL: CardTarget.SELF_PLAYER,           # -1 отбитие своему
    CardType.LOSS: CardTarget.SELF_PLAYER,           # -1 передача своему
    
    # Действуют на СОПЕРНИКА текущего хода
    CardType.OWN_GOAL: CardTarget.OPPONENT_PLAYER,   # +1 гол игроку соперника
    CardType.OFFSIDE: CardTarget.OPPONENT_PLAYER,    # отменяет гол соперника
    CardType.VAR: CardTarget.OPPONENT_TEAM,          # отменяет карточку соперника
    CardType.RED_CARD: CardTarget.OPPONENT_PLAYER,   # удаление игрока соперника
    CardType.YELLOW_CARD: CardTarget.OPPONENT_PLAYER, # -1 действие у соперника
    
    # Особые
    CardType.PENALTY: CardTarget.SELF_PLAYER,        # розыгрыш пенальти
}


class WhistleCard(BaseModel):
    """Карточка Свисток"""
    id: UUID = Field(default_factory=uuid4)
    card_type: CardType
    is_used: bool = Field(default=False)
    
    # Применение карточки
    applied_to_player_id: Optional[UUID] = None
    applied_by_manager_id: Optional[UUID] = None
    turn_applied: Optional[int] = None
    cancelled_card_id: Optional[UUID] = None
    penalty_scored: Optional[bool] = None  # Результат пенальти (если карточка Пенальти)
    var_cancelled: bool = Field(default=False)  # Была отменена через VAR

    def get_target_type(self) -> CardTarget:
        """Определить тип цели для карточки"""
        return CARD_TARGETS.get(self.card_type, CardTarget.SELF_PLAYER)

    def get_display_name(self) -> str:
        """Получить отображаемое имя карточки"""
        names = {
            CardType.HAT_TRICK: "Хэт-трик",
            CardType.DOUBLE: "Дубль",
            CardType.GOAL: "Гол",
            CardType.OWN_GOAL: "Автогол",
            CardType.VAR: "ВАР",
            CardType.OFFSIDE: "Офсайд",
            CardType.PENALTY: "Пенальти",
            CardType.RED_CARD: "Удаление",
            CardType.YELLOW_CARD: "Предупреждение",
            CardType.FOUL: "Фол",
            CardType.LOSS: "Потеря",
            CardType.INTERCEPTION: "Перехват",
            CardType.TACKLE: "Отбор",
        }
        return names.get(self.card_type, self.card_type.value)

    def requires_target(self) -> bool:
        """
        Требуется ли РУЧНОЙ выбор цели.
        
        Большинство карточек применяются автоматически:
        - Позитивные (GOAL, HAT_TRICK, DOUBLE, INTERCEPTION, TACKLE) -> свой игрок текущего хода
        - Негативные (FOUL, LOSS, YELLOW_CARD, RED_CARD, OFFSIDE) -> игрок соперника текущего хода
        - OWN_GOAL, VAR, PENALTY -> не требуют выбора
        
        Возвращает True только для карточек, которые НЕЛЬЗЯ применить автоматически.
        """
        # Все основные карточки применяются автоматически
        return False


class CardEffect(BaseModel):
    """Эффект применения карточки"""
    card_id: UUID
    card_type: CardType
    target_player_id: Optional[UUID] = None
    target_manager_id: Optional[UUID] = None
    
    goals_added: int = Field(default=0)
    goals_removed: int = Field(default=0)
    saves_added: int = Field(default=0)
    saves_removed: int = Field(default=0)
    passes_added: int = Field(default=0)
    passes_removed: int = Field(default=0)
    player_removed: bool = Field(default=False)
    card_cancelled_id: Optional[UUID] = None
    requires_penalty_roll: bool = Field(default=False)
