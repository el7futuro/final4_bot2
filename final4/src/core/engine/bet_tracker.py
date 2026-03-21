# src/core/engine/bet_tracker.py
"""Отслеживание и валидация ставок"""

from uuid import UUID
from typing import List, Dict, Set
from collections import defaultdict

from ..models.match import Match
from ..models.player import Player, Position
from ..models.bet import Bet, BetType


class BetTracker:
    """Отслеживание и валидация ставок"""
    
    def validate_bet(
        self,
        match: Match,
        manager_id: UUID,
        player: Player,
        bet: Bet
    ) -> None:
        """
        Валидировать ставку согласно правилам.
        
        Raises:
            ValueError: Если ставка невалидна
        """
        team = match.get_team(manager_id)
        if not team:
            raise ValueError("Команда не найдена")
        
        turn_number = match.current_turn.turn_number if match.current_turn else 1
        
        # 1. Игрок должен быть на поле и доступен
        if not player.is_on_field:
            raise ValueError("Игрок не на поле")
        
        if not player.is_available:
            raise ValueError("Игрок недоступен (удалён)")
        
        # 2. НОВОЕ: Проверка по номеру хода
        if turn_number == 1:
            # Первый ход — только вратарь
            if player.position != Position.GOALKEEPER:
                raise ValueError("На первом ходу доступен только вратарь")
        else:
            # Ходы 2+ — все кроме вратаря
            if player.position == Position.GOALKEEPER:
                raise ValueError("Вратарь доступен только на первом ходу")
        
        # 3. НОВОЕ: Проверка, использован ли игрок в этом матче
        if match.is_player_used(manager_id, player.id):
            raise ValueError("Игрок уже делал ставку в этом матче")
        
        # 4. Ставка на чёт/нечёт — правила
        if bet.bet_type == BetType.EVEN_ODD:
            # Форварды не могут ставить на чёт/нечёт
            if player.position == Position.FORWARD:
                raise ValueError("Форварды не могут делать ставку на чёт/нечёт")
            
            # Лимит 6 ставок на чёт/нечёт за матч
            even_odd_count = self._count_even_odd_bets(match, manager_id)
            if even_odd_count >= 6:
                raise ValueError("Максимум 6 ставок на чёт/нечёт в матче")
        
        # 5. Вратарь — только чёт/нечёт и только 1 раз за матч
        if player.position == Position.GOALKEEPER:
            if bet.bet_type != BetType.EVEN_ODD:
                raise ValueError("Вратарь может делать только ставку на чёт/нечёт")
            
            # НОВОЕ: Вратарь может делать ставку только 1 раз за весь матч
            gk_bets = [b for b in match.bets 
                       if b.manager_id == manager_id and b.player_id == player.id]
            if gk_bets:
                raise ValueError("Вратарь уже сделал ставку в этом матче")
        
        # 6. Ставки на гол — лимиты по позициям
        if bet.bet_type == BetType.EXACT_NUMBER:
            self._validate_goal_bet(match, manager_id, player, team)
        
        # 7. ИСПРАВЛЕНО: Максимум ставок на игрока за ход (вратарь=1, остальные=2)
        max_bets_per_turn = 1 if player.position == Position.GOALKEEPER else 2
        player_bets_this_turn = self._count_player_bets_this_turn(match, player.id)
        if player_bets_this_turn >= max_bets_per_turn:
            raise ValueError(f"Максимум {max_bets_per_turn} ставок на этого игрока за ход")
    
    def _count_even_odd_bets(self, match: Match, manager_id: UUID) -> int:
        """Подсчитать количество ставок на чёт/нечёт"""
        count = 0
        for bet in match.bets:
            if bet.manager_id == manager_id and bet.bet_type == BetType.EVEN_ODD:
                count += 1
        return count
    
    def _count_player_bets_this_turn(self, match: Match, player_id: UUID) -> int:
        """Подсчитать ставки на игрока в текущем ходе"""
        if not match.current_turn:
            return 0
        turn_bet_ids = set(match.current_turn.bets_placed)
        return sum(1 for b in match.bets if b.id in turn_bet_ids and b.player_id == player_id)
    
    def _validate_goal_bet(
        self,
        match: Match,
        manager_id: UUID,
        player: Player,
        team
    ) -> None:
        """
        Валидировать ставку на гол.
        
        ИСПРАВЛЕНО:
        - DF: максимум 1 ИГРОК с голевой ставкой
        - MF: максимум 3 СТАВКИ на гол суммарно
        - FW: максимум 4 СТАВКИ на гол суммарно
        """
        # Вратарь не может иметь ставку на гол
        if player.position == Position.GOALKEEPER:
            raise ValueError("Вратарь не может делать ставку на гол")
        
        # Подсчёт голевых ставок
        goal_bet_counts: Dict[Position, int] = defaultdict(int)
        defenders_with_goal_bets: Set[UUID] = set()
        
        for bet in match.bets:
            if bet.manager_id == manager_id and bet.bet_type == BetType.EXACT_NUMBER:
                bet_player = team.get_player_by_id(bet.player_id)
                if bet_player:
                    goal_bet_counts[bet_player.position] += 1
                    if bet_player.position == Position.DEFENDER:
                        defenders_with_goal_bets.add(bet.player_id)
        
        # Проверяем лимиты
        if player.position == Position.DEFENDER:
            # Только 1 защитник может иметь ставку на гол
            if player.id not in defenders_with_goal_bets:
                if len(defenders_with_goal_bets) >= 1:
                    raise ValueError("Только 1 защитник может иметь ставку на гол")
        
        elif player.position == Position.MIDFIELDER:
            # Максимум 3 СТАВКИ на гол от полузащитников суммарно
            if goal_bet_counts[Position.MIDFIELDER] >= 3:
                raise ValueError("Максимум 3 ставки на гол от полузащитников")
        
        elif player.position == Position.FORWARD:
            # Максимум 4 СТАВКИ на гол от форвардов суммарно
            if goal_bet_counts[Position.FORWARD] >= 4:
                raise ValueError("Максимум 4 ставки на гол от форвардов")
    
    def get_available_bet_types(
        self,
        match: Match,
        manager_id: UUID,
        player: Player
    ) -> List[BetType]:
        """Получить доступные типы ставок для игрока"""
        available = []
        
        # Вратарь — только чёт/нечёт (и только 1 раз за матч)
        if player.position == Position.GOALKEEPER:
            # Проверяем, не ставил ли уже вратарь
            gk_bets = [b for b in match.bets 
                       if b.manager_id == manager_id and b.player_id == player.id]
            if gk_bets:
                return []  # Вратарь уже ставил
            
            even_odd_count = self._count_even_odd_bets(match, manager_id)
            if even_odd_count < 6:
                available.append(BetType.EVEN_ODD)
            return available
        
        # Чёт/нечёт — для всех кроме форвардов
        if player.position != Position.FORWARD:
            even_odd_count = self._count_even_odd_bets(match, manager_id)
            if even_odd_count < 6:
                available.append(BetType.EVEN_ODD)
        
        # Больше/меньше — всегда доступно для полевых
        available.append(BetType.HIGH_LOW)
        
        # Точное число (гол) — с учётом лимитов
        team = match.get_team(manager_id)
        if team:
            try:
                self._validate_goal_bet(match, manager_id, player, team)
                available.append(BetType.EXACT_NUMBER)
            except ValueError:
                pass
        
        return available
    
    def can_player_bet(
        self,
        match: Match,
        manager_id: UUID,
        player: Player
    ) -> tuple[bool, str]:
        """
        Проверить, может ли игрок делать ставку в текущем ходу.
        
        Returns:
            (can_bet, reason)
        """
        if not player.is_on_field:
            return False, "Игрок не на поле"
        
        if not player.is_available:
            return False, "Игрок удалён"
        
        turn_number = match.current_turn.turn_number if match.current_turn else 1
        
        # Правило по номеру хода
        if turn_number == 1:
            if player.position != Position.GOALKEEPER:
                return False, "На первом ходу доступен только вратарь"
        else:
            if player.position == Position.GOALKEEPER:
                return False, "Вратарь доступен только на первом ходу"
        
        # Проверка использованности
        if match.is_player_used(manager_id, player.id):
            return False, "Игрок уже использован в этом матче"
        
        # Вратарь — только 1 ставка за матч
        if player.position == Position.GOALKEEPER:
            gk_bets = [b for b in match.bets 
                       if b.manager_id == manager_id and b.player_id == player.id]
            if gk_bets:
                return False, "Вратарь уже сделал ставку"
        
        return True, "OK"
