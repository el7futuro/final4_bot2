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
        
        # 1. Игрок должен быть на поле
        if not player.is_on_field:
            raise ValueError("Игрок не на поле")
        
        if not player.is_available:
            raise ValueError("Игрок недоступен (удалён)")
        
        # 2. Ставка на чёт/нечёт только для НЕ форвардов
        if bet.bet_type == BetType.EVEN_ODD:
            if player.position == Position.FORWARD:
                raise ValueError("Форварды не могут иметь ставку на чёт/нечёт")
            
            # Проверяем лимит 6 игроков с чёт/нечёт
            even_odd_count = self._count_even_odd_bets(match, manager_id)
            if even_odd_count >= 6:
                raise ValueError("Максимум 6 ставок на чёт/нечёт в матче")
        
        # 3. Вратарь — только чёт/нечёт
        if player.position == Position.GOALKEEPER:
            if bet.bet_type != BetType.EVEN_ODD:
                raise ValueError("Вратарь может иметь только ставку на чёт/нечёт")
        
        # 4. Ставки на гол — лимиты по позициям
        if bet.bet_type == BetType.EXACT_NUMBER:
            self._validate_goal_bet(match, manager_id, player, team)
        
        # 5. Максимум 2 ставки на игрока за ход
        player_bets_this_turn = self._count_player_bets_this_turn(match, player.id)
        if player_bets_this_turn >= 2:
            raise ValueError("Максимум 2 ставки на игрока за ход")
    
    def _count_even_odd_bets(self, match: Match, manager_id: UUID) -> int:
        """Подсчитать количество уникальных игроков с чёт/нечёт ставками"""
        players_with_even_odd: Set[UUID] = set()
        for bet in match.bets:
            if bet.manager_id == manager_id and bet.bet_type == BetType.EVEN_ODD:
                players_with_even_odd.add(bet.player_id)
        return len(players_with_even_odd)
    
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
        """Валидировать ставку на гол"""
        # Вратарь не может иметь ставку на гол
        if player.position == Position.GOALKEEPER:
            raise ValueError("Вратарь не может иметь ставку на гол")
        
        # Подсчёт голевых ставок по позициям
        goal_bets_by_position: Dict[Position, Set[UUID]] = defaultdict(set)
        
        for bet in match.bets:
            if bet.manager_id == manager_id and bet.bet_type == BetType.EXACT_NUMBER:
                bet_player = team.get_player_by_id(bet.player_id)
                if bet_player:
                    goal_bets_by_position[bet_player.position].add(bet.player_id)
        
        # Правила:
        # - Защитники: только 1 защитник может иметь ставку на гол
        # - Полузащитники: макс 3 игрока с голевой ставкой
        # - Форварды: макс 4 игрока с голевой ставкой
        
        if player.position == Position.DEFENDER:
            if player.id not in goal_bets_by_position[Position.DEFENDER]:
                if len(goal_bets_by_position[Position.DEFENDER]) >= 1:
                    raise ValueError("Только 1 защитник может иметь ставку на гол")
        
        elif player.position == Position.MIDFIELDER:
            if player.id not in goal_bets_by_position[Position.MIDFIELDER]:
                if len(goal_bets_by_position[Position.MIDFIELDER]) >= 3:
                    raise ValueError("Максимум 3 полузащитника могут иметь ставку на гол")
        
        elif player.position == Position.FORWARD:
            if player.id not in goal_bets_by_position[Position.FORWARD]:
                if len(goal_bets_by_position[Position.FORWARD]) >= 4:
                    raise ValueError("Максимум 4 форварда могут иметь ставку на гол")
    
    def get_available_bet_types(
        self,
        match: Match,
        manager_id: UUID,
        player: Player
    ) -> List[BetType]:
        """Получить доступные типы ставок для игрока"""
        available = []
        
        # Вратарь — только чёт/нечёт
        if player.position == Position.GOALKEEPER:
            even_odd_count = self._count_even_odd_bets(match, manager_id)
            if even_odd_count < 6:
                available.append(BetType.EVEN_ODD)
            return available
        
        # Чёт/нечёт — для всех кроме форвардов
        if player.position != Position.FORWARD:
            even_odd_count = self._count_even_odd_bets(match, manager_id)
            if even_odd_count < 6:
                available.append(BetType.EVEN_ODD)
        
        # Больше/меньше — всегда доступно
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
