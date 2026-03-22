# src/core/engine/bet_tracker.py
"""Отслеживание и валидация ставок"""

from uuid import UUID
from typing import List, Dict, Set, Tuple
from collections import defaultdict

from ..models.match import Match, MatchPhase
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
        
        # 1. Игрок должен быть в заявке и доступен
        # ИСПРАВЛЕНО: Убрали проверку is_on_field — все 16 игроков заявки доступны!
        if not player.is_available:
            raise ValueError("Игрок недоступен (удалён)")
        
        # 2. Проверка по номеру хода (зависит от фазы матча)
        if match.phase == MatchPhase.MAIN_TIME:
            # ОСНОВНОЕ ВРЕМЯ
            if turn_number == 1:
                # Первый ход — только вратарь
                if player.position != Position.GOALKEEPER:
                    raise ValueError("На первом ходу доступен только вратарь")
            else:
                # Ходы 2+ — все кроме вратаря
                if player.position == Position.GOALKEEPER:
                    raise ValueError("Вратарь доступен только на первом ходу")
        else:
            # ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ — только полевые (вратарь уже использован)
            if player.position == Position.GOALKEEPER:
                raise ValueError("Вратарь недоступен в дополнительное время")
        
        # 3. Проверка, использован ли игрок в этом матче
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
            
            gk_bets = [b for b in match.bets 
                       if b.manager_id == manager_id and b.player_id == player.id]
            if gk_bets:
                raise ValueError("Вратарь уже сделал ставку в этом матче")
        
        # 6. Ставки на гол — лимиты по позициям
        if bet.bet_type == BetType.EXACT_NUMBER:
            self._validate_goal_bet(match, manager_id, player, team)
        
        # 7. Максимум ставок на игрока за ход (вратарь=1, остальные=2)
        max_bets_per_turn = 1 if player.position == Position.GOALKEEPER else 2
        player_bets_this_turn = self._count_player_bets_this_turn(match, manager_id, player.id)
        if player_bets_this_turn >= max_bets_per_turn:
            raise ValueError(f"Максимум {max_bets_per_turn} ставок на этого игрока за ход")
        
        # 8. НОВОЕ: 2 ставки должны быть РАЗНЫХ типов (для полевых игроков)
        if player.position != Position.GOALKEEPER and player_bets_this_turn == 1:
            # Это вторая ставка — проверяем, что тип отличается от первой
            existing_bet_type = self._get_player_bet_type_this_turn(match, manager_id, player.id)
            if existing_bet_type and existing_bet_type == bet.bet_type:
                raise ValueError(f"Две ставки должны быть РАЗНЫХ типов (уже есть {existing_bet_type.value})")
    
    def _count_even_odd_bets(self, match: Match, manager_id: UUID) -> int:
        """Подсчитать количество ставок на чёт/нечёт"""
        count = 0
        for bet in match.bets:
            if bet.manager_id == manager_id and bet.bet_type == BetType.EVEN_ODD:
                count += 1
        return count
    
    def _count_player_bets_this_turn(self, match: Match, manager_id: UUID, player_id: UUID) -> int:
        """Подсчитать ставки на игрока в текущем ходе для конкретного менеджера"""
        if not match.current_turn:
            return 0
        
        # Получаем ID ставок этого менеджера в текущем ходе
        if manager_id == match.manager1_id:
            turn_bet_ids = set(match.current_turn.manager1_bets)
        elif manager_id == match.manager2_id:
            turn_bet_ids = set(match.current_turn.manager2_bets)
        else:
            # Легаси: используем bets_placed
            turn_bet_ids = set(match.current_turn.bets_placed)
        
        return sum(1 for b in match.bets if b.id in turn_bet_ids and b.player_id == player_id)
    
    def _get_player_bet_type_this_turn(self, match: Match, manager_id: UUID, player_id: UUID) -> BetType | None:
        """Получить тип первой ставки игрока в текущем ходе"""
        if not match.current_turn:
            return None
        
        # Получаем ID ставок этого менеджера в текущем ходе
        if manager_id == match.manager1_id:
            turn_bet_ids = set(match.current_turn.manager1_bets)
        elif manager_id == match.manager2_id:
            turn_bet_ids = set(match.current_turn.manager2_bets)
        else:
            turn_bet_ids = set(match.current_turn.bets_placed)
        
        for bet in match.bets:
            if bet.id in turn_bet_ids and bet.player_id == player_id:
                return bet.bet_type
        
        return None
    
    def _validate_goal_bet(
        self,
        match: Match,
        manager_id: UUID,
        player: Player,
        team
    ) -> None:
        """
        Валидировать ставку на гол.
        
        ОСНОВНОЕ ВРЕМЯ:
        - DF: максимум 1 ИГРОК с голевой ставкой
        - MF: максимум 3 СТАВКИ на гол суммарно
        - FW: максимум 4 СТАВКИ на гол суммарно
        
        ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ:
        - Ставка на гол возможна для КАЖДОГО игрока!
        """
        # Вратарь не может иметь ставку на гол
        if player.position == Position.GOALKEEPER:
            raise ValueError("Вратарь не может делать ставку на гол")
        
        # В ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ лимиты не действуют — ставка на гол для каждого!
        if match.phase != MatchPhase.MAIN_TIME:
            return  # Без ограничений
        
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
        if not player.is_available:
            return False, "Игрок удалён"
        
        turn_number = match.current_turn.turn_number if match.current_turn else 1
        
        # Правило по номеру хода ЗАВИСИТ от фазы
        if match.phase == MatchPhase.MAIN_TIME:
            # ОСНОВНОЕ ВРЕМЯ
            if turn_number == 1:
                if player.position != Position.GOALKEEPER:
                    return False, "На первом ходу доступен только вратарь"
            else:
                if player.position == Position.GOALKEEPER:
                    return False, "Вратарь доступен только на первом ходу"
        else:
            # ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ — только полевые
            if player.position == Position.GOALKEEPER:
                return False, "Вратарь недоступен в дополнительное время"
        
        # Проверка использованности
        if match.is_player_used(manager_id, player.id):
            return False, "Игрок уже использован в этом матче"
        
        # Вратарь — только 1 ставка за матч
        if player.position == Position.GOALKEEPER:
            gk_bets = [b for b in match.bets 
                       if b.manager_id == manager_id and b.player_id == player.id]
            if gk_bets:
                return False, "Вратарь уже сделал ставку"
        
        # Для полевых игроков — проверяем наличие минимум 2 РАЗНЫХ типов ставок
        if player.position != Position.GOALKEEPER:
            available_types = self.get_available_bet_types(match, manager_id, player)
            if len(available_types) < 2:
                return False, f"Недостаточно типов ставок (нужно 2, есть {len(available_types)})"
        
        return True, "OK"
    
    def check_deadlock_risk(
        self,
        match: Match,
        manager_id: UUID,
        proposed_player_id: UUID,
        proposed_bet_types: List[BetType]
    ) -> Tuple[bool, str]:
        """
        Проверить, не приведёт ли текущий выбор к дедлоку.
        
        Применяется начиная с 5-го хода.
        
        Args:
            match: Текущий матч
            manager_id: ID менеджера
            proposed_player_id: ID выбранного игрока
            proposed_bet_types: Типы ставок, которые игрок планирует сделать
        
        Returns:
            (is_safe, reason): True если безопасно, иначе False + причина
        """
        turn_number = match.current_turn.turn_number if match.current_turn else 1
        
        # До 5-го хода проверка не нужна
        if turn_number < 5:
            return True, "Проверка активна с 5-го хода"
        
        team = match.get_team(manager_id)
        if not team:
            return True, "Команда не найдена"
        
        # Симулируем состояние после этого хода
        simulated_even_odd_count = self._count_even_odd_bets(match, manager_id)
        for bet_type in proposed_bet_types:
            if bet_type == BetType.EVEN_ODD:
                simulated_even_odd_count += 1
        
        # Сколько ходов осталось (всего 11 ходов в основное время)
        remaining_turns = 11 - turn_number
        
        # Сколько игроков ещё нужно использовать
        used_players = match.get_used_players(manager_id)
        remaining_player_count = remaining_turns  # Каждый ход = 1 игрок
        
        # Проверяем, хватит ли чёт/нечёт ставок для оставшихся игроков
        remaining_even_odd = 6 - simulated_even_odd_count
        
        # Считаем, сколько игроков НЕ МОГУТ использовать чёт/нечёт (форварды)
        available_players = []
        for player in team.players:
            if player.id == proposed_player_id:
                continue  # Этого уже выбрали
            if player.id in used_players:
                continue
            if not player.is_available:
                continue
            if player.position == Position.GOALKEEPER:
                continue  # Вратарь уже ходил на 1-м ходу
            available_players.append(player)
        
        # Проверяем каждого оставшегося игрока
        players_needing_even_odd = 0
        players_with_only_even_odd_option = 0
        
        for player in available_players[:remaining_player_count]:
            types = self._get_potential_bet_types(match, manager_id, player, simulated_even_odd_count)
            
            # Если у игрока только 1 тип — это потенциальная проблема
            if len(types) < 2:
                return False, f"Игрок {player.name} останется без 2 типов ставок"
            
            # Если игрок ТРЕБУЕТ чёт/нечёт (не форвард и нет гола)
            if BetType.EVEN_ODD in types and player.position != Position.FORWARD:
                # Проверяем, может ли он обойтись без чёт/нечёт
                non_even_odd_types = [t for t in types if t != BetType.EVEN_ODD]
                if len(non_even_odd_types) < 2:
                    players_needing_even_odd += 1
        
        # Проверяем, хватит ли чёт/нечёт для всех, кому они нужны
        if players_needing_even_odd > remaining_even_odd:
            return False, f"Не хватит ставок чёт/нечёт: нужно {players_needing_even_odd}, осталось {remaining_even_odd}"
        
        return True, "OK"
    
    def _get_potential_bet_types(
        self,
        match: Match,
        manager_id: UUID,
        player: Player,
        simulated_even_odd_count: int
    ) -> List[BetType]:
        """
        Получить потенциальные типы ставок с учётом симулированного состояния.
        """
        available = []
        team = match.get_team(manager_id)
        
        # Чёт/нечёт — для всех кроме форвардов
        if player.position != Position.FORWARD:
            if simulated_even_odd_count < 6:
                available.append(BetType.EVEN_ODD)
        
        # Больше/меньше — всегда доступно для полевых
        if player.position != Position.GOALKEEPER:
            available.append(BetType.HIGH_LOW)
        
        # Точное число (гол) — с учётом лимитов
        if team and player.position != Position.GOALKEEPER:
            try:
                self._validate_goal_bet(match, manager_id, player, team)
                available.append(BetType.EXACT_NUMBER)
            except ValueError:
                pass
        
        return available
