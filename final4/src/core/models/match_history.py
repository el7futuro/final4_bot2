# src/core/models/match_history.py
"""История матча и статистика игроков по ходам"""

from uuid import UUID, uuid4
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from enum import Enum

from .match import MatchPhase
from .bet import BetType


class TurnAction(BaseModel):
    """Действие в одном ходе"""
    turn_number: int
    phase: MatchPhase
    player_id: UUID
    player_name: str
    position: str
    
    # Ставки
    bet1_type: BetType
    bet1_value: str  # "чёт", "нечёт", "больше", "меньше", "1", "2", etc.
    bet1_won: bool = False
    
    bet2_type: BetType
    bet2_value: str
    bet2_won: bool = False
    
    # Результат
    dice_value: int = 0
    
    # Полученные действия (до карточек)
    saves_earned: int = 0
    passes_earned: int = 0
    goals_earned: int = 0
    
    # Карточка
    card_drawn: Optional[str] = None
    card_effect: Optional[str] = None
    
    # Изменения от карточки
    saves_from_card: int = 0
    passes_from_card: int = 0
    goals_from_card: int = 0


class PlayerMatchStats(BaseModel):
    """Статистика игрока за весь матч"""
    player_id: UUID
    player_name: str
    position: str
    
    # Когда играл
    turn_played: Optional[int] = None
    phase_played: Optional[MatchPhase] = None
    
    # Текущие накопленные действия
    saves: int = 0
    passes: int = 0
    goals: int = 0
    
    # История изменений
    history: List[str] = Field(default_factory=list)
    
    def add_saves(self, count: int, reason: str) -> None:
        self.saves += count
        self.history.append(f"+{count} отб ({reason})")
    
    def add_passes(self, count: int, reason: str) -> None:
        self.passes += count
        self.history.append(f"+{count} перед ({reason})")
    
    def add_goals(self, count: int, reason: str) -> None:
        self.goals += count
        self.history.append(f"+{count} гол ({reason})")
    
    def remove_saves(self, count: int, reason: str) -> None:
        self.saves = max(0, self.saves - count)
        self.history.append(f"-{count} отб ({reason})")
    
    def remove_passes(self, count: int, reason: str) -> None:
        self.passes = max(0, self.passes - count)
        self.history.append(f"-{count} перед ({reason})")
    
    def remove_goals(self, count: int, reason: str) -> None:
        self.goals = max(0, self.goals - count)
        self.history.append(f"-{count} гол ({reason})")
    
    def clear_all(self, reason: str) -> None:
        self.saves = 0
        self.passes = 0
        self.goals = 0
        self.history.append(f"Все действия обнулены ({reason})")


class MatchHistory(BaseModel):
    """История всего матча"""
    match_id: UUID
    
    # Статистика игроков по ID
    manager1_players: Dict[str, PlayerMatchStats] = Field(default_factory=dict)
    manager2_players: Dict[str, PlayerMatchStats] = Field(default_factory=dict)
    
    # История ходов
    turns: List[TurnAction] = Field(default_factory=list)
    
    # Использованные карточки
    cards_used: List[str] = Field(default_factory=list)
    
    # Колода карточек (оставшиеся)
    deck: Dict[str, int] = Field(default_factory=lambda: {
        "Хет-трик": 1,
        "Дубль": 1,
        "Гол": 2,
        "Автогол": 1,
        "ВАР": 2,
        "Офсайд": 2,
        "Пенальти": 2,
        "Удаление": 2,
        "Предупреждение": 3,
        "Фол": 6,
        "Потеря": 6,
        "Перехват": 6,
        "Отбор": 6,
    })
    
    def init_players(self, manager1_id: UUID, manager1_players: list, 
                     manager2_id: UUID, manager2_players: list) -> None:
        """Инициализировать игроков обеих команд"""
        for p in manager1_players:
            self.manager1_players[str(p.id)] = PlayerMatchStats(
                player_id=p.id,
                player_name=p.name,
                position=p.position.value
            )
        for p in manager2_players:
            self.manager2_players[str(p.id)] = PlayerMatchStats(
                player_id=p.id,
                player_name=p.name,
                position=p.position.value
            )
    
    def get_player_stats(self, manager_id: UUID, player_id: UUID, 
                         match_manager1_id: UUID) -> Optional[PlayerMatchStats]:
        """Получить статистику игрока"""
        key = str(player_id)
        if manager_id == match_manager1_id:
            return self.manager1_players.get(key)
        else:
            return self.manager2_players.get(key)
    
    def draw_card(self) -> Optional[str]:
        """Вытянуть карточку из колоды"""
        import random
        available = [card for card, count in self.deck.items() if count > 0]
        if not available:
            return None
        card = random.choice(available)
        self.deck[card] -= 1
        self.cards_used.append(card)
        return card
    
    def get_total_stats(self, manager_id: UUID, match_manager1_id: UUID) -> Dict[str, int]:
        """Получить суммарную статистику команды"""
        players = self.manager1_players if manager_id == match_manager1_id else self.manager2_players
        total = {"saves": 0, "passes": 0, "goals": 0}
        for p in players.values():
            total["saves"] += p.saves
            total["passes"] += p.passes
            total["goals"] += p.goals
        return total
    
    def get_players_with_passes(self, manager_id: UUID, match_manager1_id: UUID) -> List[PlayerMatchStats]:
        """Получить игроков с передачами (для пенальти)"""
        players = self.manager1_players if manager_id == match_manager1_id else self.manager2_players
        return [p for p in players.values() if p.passes > 0]
    
    def get_all_players_ordered_for_penalties(self, manager_id: UUID, 
                                               match_manager1_id: UUID) -> List[PlayerMatchStats]:
        """
        Получить игроков в порядке для серии пенальти:
        1. Extra Time (в обратном порядке)
        2. Основное время (с 11-го до вратаря)
        """
        players = self.manager1_players if manager_id == match_manager1_id else self.manager2_players
        
        # Сортируем по фазе и номеру хода
        extra_time = []
        main_time = []
        not_played = []
        
        for p in players.values():
            if p.phase_played == MatchPhase.EXTRA_TIME:
                extra_time.append((p.turn_played or 0, p))
            elif p.phase_played == MatchPhase.MAIN_TIME:
                main_time.append((p.turn_played or 0, p))
            else:
                not_played.append(p)
        
        # Extra Time: последний ход первым
        extra_time.sort(key=lambda x: -x[0])
        # Main Time: последний ход первым
        main_time.sort(key=lambda x: -x[0])
        
        result = [p for _, p in extra_time] + [p for _, p in main_time] + not_played
        return result
    
    def print_current_stats(self, match_manager1_id: UUID, manager1_name: str, manager2_name: str) -> str:
        """Вывести текущую статистику"""
        lines = []
        lines.append("=" * 60)
        lines.append("📊 ТЕКУЩАЯ СТАТИСТИКА")
        lines.append("=" * 60)
        
        # Manager 1
        total1 = self.get_total_stats(match_manager1_id, match_manager1_id)
        lines.append(f"\n{manager1_name}:")
        lines.append(f"  ИТОГО: {total1['saves']} отб, {total1['passes']} перед, {total1['goals']} гол")
        lines.append("  Игроки:")
        for p in self.manager1_players.values():
            if p.turn_played is not None:
                phase = "ET" if p.phase_played == MatchPhase.EXTRA_TIME else "MT"
                lines.append(f"    {p.player_name}: {p.saves} отб, {p.passes} перед, {p.goals} гол (ход {p.turn_played} {phase})")
        
        # Manager 2 (получаем ID из контекста - используем не match_manager1_id)
        total2 = {"saves": 0, "passes": 0, "goals": 0}
        for p in self.manager2_players.values():
            total2["saves"] += p.saves
            total2["passes"] += p.passes
            total2["goals"] += p.goals
        
        lines.append(f"\n{manager2_name}:")
        lines.append(f"  ИТОГО: {total2['saves']} отб, {total2['passes']} перед, {total2['goals']} гол")
        lines.append("  Игроки:")
        for p in self.manager2_players.values():
            if p.turn_played is not None:
                phase = "ET" if p.phase_played == MatchPhase.EXTRA_TIME else "MT"
                lines.append(f"    {p.player_name}: {p.saves} отб, {p.passes} перед, {p.goals} гол (ход {p.turn_played} {phase})")
        
        return "\n".join(lines)
