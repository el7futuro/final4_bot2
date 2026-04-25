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
            
            # Лимит 6 ставок на чёт/нечёт ТОЛЬКО в основное время
            if match.phase == MatchPhase.MAIN_TIME:
                even_odd_count = self._count_even_odd_bets(match, manager_id)
                if even_odd_count >= 6:
                    raise ValueError("Максимум 6 ставок на чёт/нечёт в основное время")
        
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
        
        # 8. Проверка типов ставок (зависит от фазы)
        if player.position != Position.GOALKEEPER and player_bets_this_turn == 1:
            # Это вторая ставка
            existing_bet_type = self._get_player_bet_type_this_turn(match, manager_id, player.id)
            
            if match.phase == MatchPhase.EXTRA_TIME:
                # ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ: одна ставка ОБЯЗАТЕЛЬНО на гол
                first_is_goal = existing_bet_type == BetType.EXACT_NUMBER
                second_is_goal = bet.bet_type == BetType.EXACT_NUMBER
                
                if not first_is_goal and not second_is_goal:
                    raise ValueError("В дополнительное время одна ставка ОБЯЗАТЕЛЬНО на гол (точное число)")
                
                if first_is_goal and second_is_goal:
                    raise ValueError("В дополнительное время только ОДНА ставка на гол, вторая — чёт/нечёт или больше/меньше")
            else:
                # ОСНОВНОЕ ВРЕМЯ: 
                # - Две ставки на гол разрешены, если квота позволяет (>= 2)
                # - Остальные типы — РАЗНЫЕ
                if existing_bet_type and existing_bet_type == bet.bet_type:
                    if bet.bet_type == BetType.EXACT_NUMBER:
                        # Проверяем, есть ли квота на вторую голевую ставку
                        # Защитники: 1 квота → не могут 2 ставки на гол
                        # Полузащитники: 3 квоты → могут, если осталось >= 2
                        # Форварды: 4 квоты → могут, если осталось >= 2
                        remaining = self._get_remaining_goal_quota(match, manager_id, player, team)
                        if remaining < 1:
                            raise ValueError(f"Недостаточно квоты для второй ставки на гол")
                    else:
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
        - DF: максимум 1 СТАВКА на гол на всех защитников
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
        
        remaining = self._get_remaining_goal_quota(match, manager_id, player, team)
        if remaining <= 0:
            if player.position == Position.DEFENDER:
                raise ValueError("Лимит ставок на гол для защитников исчерпан (1)")
            elif player.position == Position.MIDFIELDER:
                raise ValueError("Лимит ставок на гол для полузащитников исчерпан (3)")
            elif player.position == Position.FORWARD:
                raise ValueError("Лимит ставок на гол для форвардов исчерпан (4)")
    
    def _get_remaining_goal_quota(
        self,
        match: Match,
        manager_id: UUID,
        player: Player,
        team
    ) -> int:
        """
        Получить оставшуюся квоту на голевые ставки для позиции игрока.
        
        Квоты:
        - Защитники: 1 ставка на всех
        - Полузащитники: 3 ставки на всех
        - Форварды: 4 ставки на всех
        """
        if player.position == Position.GOALKEEPER:
            return 0
        
        # Лимиты по позициям
        limits = {
            Position.DEFENDER: 1,
            Position.MIDFIELDER: 3,
            Position.FORWARD: 4
        }
        
        limit = limits.get(player.position, 0)
        
        # Считаем уже сделанные ставки на гол для этой позиции
        used = 0
        for bet in match.bets:
            if bet.manager_id == manager_id and bet.bet_type == BetType.EXACT_NUMBER:
                bet_player = team.get_player_by_id(bet.player_id)
                if bet_player and bet_player.position == player.position:
                    used += 1
        
        return limit - used
    
    
    # Допустимые формации (DF, MF, FW) — 10 полевых игроков
    VALID_FORMATIONS = [
        (4, 4, 2),
        (4, 3, 3),
        (3, 5, 2),
        (3, 4, 3),
        (5, 3, 2),
        (5, 2, 3),
        (3, 3, 4),
    ]

    def _simulate_bets_safe_for_future(
        self,
        match: Match,
        manager_id: UUID,
        player: Player,
        proposed_bet_types: List[BetType]
    ) -> bool:
        """
        Симулирует размещение указанных ставок на кандидате И проверяет
        что оставшиеся ходы можно сыграть полностью:
        - Финальный набор использованных полевых должен попадать в одну из
          допустимых формаций (4-4-2, 4-3-3, 3-5-2, 3-4-3, 5-3-2, 5-2-3, 3-3-4).
        - Каждый из оставшихся ходов (turns_remaining) — это 1 игрок с парой
          из 2 разных типов ставок, которые ВМЕСТЕ должны вписаться в общий
          бюджет ч/н (≤6) и квоты голов по позициям (DF≤1, MF≤3, FW≤4).

        КЛЮЧЕВОЕ: проверка единая — формация И бюджеты И квоты ОДНОВРЕМЕННО,
        а не по отдельности. Возможные пары на полевого:
        - DF/MF: (HL,EO), (HL,EXACT), (EO,EXACT) — только 1 EXACT за пару (квота 1/3)
        - FW:    (HL,EXACT) — единственный вариант (FW не может EO)
        """
        if match.phase != MatchPhase.MAIN_TIME:
            return True

        team = match.get_team(manager_id)
        if not team:
            return True

        turn_number = match.current_turn.turn_number if match.current_turn else 1
        turns_remaining = 11 - turn_number  # ходов ПОСЛЕ текущего
        if turns_remaining <= 0:
            return True

        used_ids = set(match.get_used_players(manager_id)) | {player.id}

        # Текущее состояние из match.bets (включает уже размещённые ставки этого хода)
        eo_used = self._count_even_odd_bets(match, manager_id)
        df_goals = 0
        mf_goals = 0
        fw_goals = 0
        used_df = used_mf = used_fw = 0
        for p in team.players:
            if p.id in match.get_used_players(manager_id):
                if p.position == Position.DEFENDER:
                    used_df += 1
                elif p.position == Position.MIDFIELDER:
                    used_mf += 1
                elif p.position == Position.FORWARD:
                    used_fw += 1
        for bet in match.bets:
            if bet.manager_id == manager_id and bet.bet_type == BetType.EXACT_NUMBER:
                bp = team.get_player_by_id(bet.player_id)
                if bp:
                    if bp.position == Position.DEFENDER:
                        df_goals += 1
                    elif bp.position == Position.MIDFIELDER:
                        mf_goals += 1
                    elif bp.position == Position.FORWARD:
                        fw_goals += 1

        # Применяем proposed_bet_types к кандидату (его ставки текущего хода)
        for bt in proposed_bet_types:
            if bt == BetType.EVEN_ODD:
                eo_used += 1
            elif bt == BetType.EXACT_NUMBER:
                if player.position == Position.DEFENDER:
                    df_goals += 1
                elif player.position == Position.MIDFIELDER:
                    mf_goals += 1
                elif player.position == Position.FORWARD:
                    fw_goals += 1

        # Кандидат добавляется к used (его позиция) — для финальной формации
        if player.position == Position.DEFENDER:
            used_df += 1
        elif player.position == Position.MIDFIELDER:
            used_mf += 1
        elif player.position == Position.FORWARD:
            used_fw += 1

        eo_budget = max(0, 6 - eo_used)
        df_q = max(0, 1 - df_goals)
        mf_q = max(0, 3 - mf_goals)
        fw_q = max(0, 4 - fw_goals)

        # Оставшиеся НЕиспользованные полевые по позициям (без кандидата)
        r_df = r_mf = r_fw = 0
        for p in team.players:
            if p.id in used_ids or not p.is_available:
                continue
            if p.position == Position.DEFENDER:
                r_df += 1
            elif p.position == Position.MIDFIELDER:
                r_mf += 1
            elif p.position == Position.FORWARD:
                r_fw += 1

        # Проверяем: ∃ формация (d,m,f) такая что
        # - need_df + need_mf + need_fw == turns_remaining
        # - need_df ≥ 0, need_mf ≥ 0, need_fw ≥ 0
        # - need_df ≤ r_df, need_mf ≤ r_mf, need_fw ≤ r_fw
        # - need_fw ≤ fw_q (FW обязан брать EXACT)
        # - ∃ x_df ∈ [0, min(need_df, df_q)], x_mf ∈ [0, min(need_mf, mf_q)]:
        #     (need_df - x_df) + (need_mf - x_mf) ≤ eo_budget
        for d, m, f in self.VALID_FORMATIONS:
            need_df = d - used_df
            need_mf = m - used_mf
            need_fw = f - used_fw
            if need_df < 0 or need_mf < 0 or need_fw < 0:
                continue
            if need_df + need_mf + need_fw != turns_remaining:
                continue
            if need_df > r_df or need_mf > r_mf or need_fw > r_fw:
                continue
            if need_fw > fw_q:
                continue
            # Минимум EO: максимизируем EXACT для DF и MF
            max_x_df = min(need_df, df_q)
            max_x_mf = min(need_mf, mf_q)
            min_eo = (need_df - max_x_df) + (need_mf - max_x_mf)
            if min_eo <= eo_budget:
                return True

        return False


    def _is_pair_rules_valid(
        self,
        match: Match,
        manager_id: UUID,
        player: Player,
        t1: BetType,
        t2: BetType
    ) -> bool:
        """
        Проверить что пара ставок (t1, t2) на одного игрока в текущем ходе
        соответствует базовым правилам (без проверки future-safety):
        - Две ставки должны быть РАЗНЫХ типов, кроме (EXACT, EXACT)
          когда у позиции хватает квоты голов.
        - В ОСНОВНОЕ ВРЕМЯ: форварды не могут ставить EVEN_ODD; бюджет ч/н
          (с учётом текущего расхода) должен покрывать кол-во EVEN_ODD в паре;
          квота голов по позиции должна покрывать кол-во EXACT_NUMBER в паре.
        - В ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ: ровно один EXACT_NUMBER; вторая — HIGH_LOW
          или EVEN_ODD (EVEN_ODD только не для форвардов).
        Бюджет ч/н в ET не ограничен (по правилам игры).
        """
        if player.position == Position.GOALKEEPER:
            return False

        team = match.get_team(manager_id)
        if not team:
            return False

        # ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ: ровно одна ставка на гол
        if match.phase == MatchPhase.EXTRA_TIME:
            n_goals = (1 if t1 == BetType.EXACT_NUMBER else 0) + \
                      (1 if t2 == BetType.EXACT_NUMBER else 0)
            if n_goals != 1:
                return False
            # Вторая (не-голевая) ставка
            other = t1 if t2 == BetType.EXACT_NUMBER else t2
            if other == BetType.EVEN_ODD and player.position == Position.FORWARD:
                return False
            if other not in (BetType.HIGH_LOW, BetType.EVEN_ODD):
                return False
            return True

        # ОСНОВНОЕ ВРЕМЯ
        # Запрет одинаковых типов (кроме EXACT+EXACT при наличии квоты)
        if t1 == t2 and t1 != BetType.EXACT_NUMBER:
            return False

        # Форварды не могут EVEN_ODD
        if player.position == Position.FORWARD and \
                (t1 == BetType.EVEN_ODD or t2 == BetType.EVEN_ODD):
            return False

        # Бюджет ч/н
        n_eo = (1 if t1 == BetType.EVEN_ODD else 0) + \
               (1 if t2 == BetType.EVEN_ODD else 0)
        eo_used = self._count_even_odd_bets(match, manager_id)
        if eo_used + n_eo > 6:
            return False

        # Квота голов по позиции
        n_goals = (1 if t1 == BetType.EXACT_NUMBER else 0) + \
                  (1 if t2 == BetType.EXACT_NUMBER else 0)
        if n_goals > 0:
            remaining = self._get_remaining_goal_quota(match, manager_id, player, team)
            if n_goals > remaining:
                return False

        return True

    def has_valid_safe_combo(
        self,
        match: Match,
        manager_id: UUID,
        player: Player
    ) -> bool:
        """
        Существует ли хотя бы одна валидная (по правилам) и безопасная (по 
        будущим ходам) комбинация из 2 ставок для этого игрока в этом ходу?

        Используется для:
        - проверки "выбираем ли игрока" (вместо отдельных проверок ч/н и голов)
        - turn 1 (только вратарь, 1 ставка) — отдельная логика
        """
        # Вратарь
        if player.position == Position.GOALKEEPER:
            turn_number = match.current_turn.turn_number if match.current_turn else 1
            if match.phase != MatchPhase.MAIN_TIME or turn_number != 1:
                return False
            # GK на 1-м ходу — только EVEN_ODD
            if self._count_even_odd_bets(match, manager_id) >= 6:
                return False
            return True

        # Полевые: перебираем все упорядоченные пары (для покрытия EXACT,EXACT)
        all_types = [BetType.EVEN_ODD, BetType.HIGH_LOW, BetType.EXACT_NUMBER]
        for t1 in all_types:
            for t2 in all_types:
                if not self._is_pair_rules_valid(match, manager_id, player, t1, t2):
                    continue
                if not self._simulate_bets_safe_for_future(
                    match, manager_id, player, [t1, t2]
                ):
                    continue
                return True
        return False

    def _even_odd_safe_for_future(
        self,
        match: Match,
        manager_id: UUID,
        player: Player
    ) -> bool:
        """
        Если этот игрок поставит ч/н, останется ли достаточно играбельных 
        игроков (с >= 2 типами ставок) на все будущие ходы?
        
        Симулируем: бюджет ч/н уменьшается на 1. Пересчитываем сколько 
        оставшихся игроков имеют >= 2 типа.
        """
        if match.phase != MatchPhase.MAIN_TIME:
            return True
        
        team = match.get_team(manager_id)
        if not team:
            return True
        
        turn_number = match.current_turn.turn_number if match.current_turn else 1
        turns_remaining = 11 - turn_number  # ходов ПОСЛЕ текущего
        if turns_remaining <= 0:
            return True
        
        used_ids = match.get_used_players(manager_id)
        
        # Бюджет ч/н ПОСЛЕ этой ставки
        eo_after = self._count_even_odd_bets(match, manager_id) + 1
        eo_budget = 6 - eo_after
        
        # Голы по позициям (текущие)
        df_goals = 0
        mf_goals = 0
        for bet in match.bets:
            if bet.manager_id == manager_id and bet.bet_type == BetType.EXACT_NUMBER:
                bp = team.get_player_by_id(bet.player_id)
                if bp:
                    if bp.position == Position.DEFENDER: df_goals += 1
                    elif bp.position == Position.MIDFIELDER: mf_goals += 1
        
        # Считаем сколько оставшихся (без текущего) будут играбельными
        playable = 0
        for p in team.players:
            if p.id in used_ids or not p.is_available or p.id == player.id:
                continue
            if p.position == Position.GOALKEEPER:
                continue
            
            # Считаем типы для этого игрока при новом бюджете ч/н
            types = 0
            # HIGH_LOW — всегда
            types += 1
            # EXACT_NUMBER — если квота есть
            if p.position == Position.FORWARD:
                fw_goals = sum(1 for b in match.bets if b.manager_id == manager_id and b.bet_type == BetType.EXACT_NUMBER and team.get_player_by_id(b.player_id) and team.get_player_by_id(b.player_id).position == Position.FORWARD)
                if fw_goals < 4: types += 1
            elif p.position == Position.DEFENDER:
                if df_goals < 1: types += 1
            elif p.position == Position.MIDFIELDER:
                if mf_goals < 3: types += 1
            # EVEN_ODD — если не FW и бюджет > 0
            if p.position != Position.FORWARD and eo_budget > 0:
                types += 1
            
            if types >= 2:
                playable += 1
        
        return playable >= turns_remaining

    def _goal_safe_for_future(
        self,
        match: Match,
        manager_id: UUID,
        player: Player
    ) -> bool:
        """
        Если этот игрок поставит на гол, останется ли достаточно играбельных
        игроков (с >= 2 типами ставок) на все будущие ходы?
        
        Симулируем: гол-квота позиции увеличивается на 1. Пересчитываем.
        """
        if match.phase != MatchPhase.MAIN_TIME:
            return True
        
        team = match.get_team(manager_id)
        if not team:
            return True
        
        turn_number = match.current_turn.turn_number if match.current_turn else 1
        turns_remaining = 11 - turn_number
        if turns_remaining <= 0:
            return True
        
        used_ids = match.get_used_players(manager_id)
        
        eo_budget = 6 - self._count_even_odd_bets(match, manager_id)
        
        # Голы по позициям ПОСЛЕ этой ставки
        df_goals = 0
        mf_goals = 0
        fw_goals = 0
        for bet in match.bets:
            if bet.manager_id == manager_id and bet.bet_type == BetType.EXACT_NUMBER:
                bp = team.get_player_by_id(bet.player_id)
                if bp:
                    if bp.position == Position.DEFENDER: df_goals += 1
                    elif bp.position == Position.MIDFIELDER: mf_goals += 1
                    elif bp.position == Position.FORWARD: fw_goals += 1
        
        # +1 гол для позиции текущего игрока
        if player.position == Position.DEFENDER: df_goals += 1
        elif player.position == Position.MIDFIELDER: mf_goals += 1
        elif player.position == Position.FORWARD: fw_goals += 1
        
        # Считаем играбельных
        playable = 0
        for p in team.players:
            if p.id in used_ids or not p.is_available or p.id == player.id:
                continue
            if p.position == Position.GOALKEEPER:
                continue
            
            types = 0
            types += 1  # HIGH_LOW всегда
            # EXACT_NUMBER
            if p.position == Position.FORWARD and fw_goals < 4: types += 1
            elif p.position == Position.DEFENDER and df_goals < 1: types += 1
            elif p.position == Position.MIDFIELDER and mf_goals < 3: types += 1
            # EVEN_ODD
            if p.position != Position.FORWARD and eo_budget > 0:
                types += 1
            
            if types >= 2:
                playable += 1
        
        return playable >= turns_remaining

    def get_available_bet_types(
        self,
        match: Match,
        manager_id: UUID,
        player: Player
    ) -> List[BetType]:
        """
        Получить доступные типы ставок для игрока.
        
        ОСНОВНОЕ ВРЕМЯ:
        - 2 разных типа из доступных
        
        ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ:
        - Обязательно: 1 ставка на гол + 1 позиционная (чёт/нечёт или больше/меньше)
        - Форварды: гол + больше/меньше
        - Остальные: гол + (чёт/нечёт ИЛИ больше/меньше)
        """
        available = []
        
        # Вратарь — только чёт/нечёт (и только 1 раз за матч)
        if player.position == Position.GOALKEEPER:
            gk_bets = [b for b in match.bets 
                       if b.manager_id == manager_id and b.player_id == player.id]
            if gk_bets:
                return []
            
            even_odd_count = self._count_even_odd_bets(match, manager_id)
            if even_odd_count < 6:
                available.append(BetType.EVEN_ODD)
            return available
        
        # ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ — особые правила
        if match.phase == MatchPhase.EXTRA_TIME:
            # Проверяем, есть ли уже ставка в этом ходу
            existing_bet_type = self._get_player_bet_type_this_turn(match, manager_id, player.id)
            
            if existing_bet_type is None:
                # ПЕРВАЯ ставка — доступны все варианты
                available.append(BetType.EXACT_NUMBER)
                
                # Чёт/нечёт — для всех кроме форвардов, БЕЗ лимита в ET
                if player.position != Position.FORWARD:
                    available.append(BetType.EVEN_ODD)
                
                # Больше/меньше — всегда
                available.append(BetType.HIGH_LOW)
            else:
                # ВТОРАЯ ставка — зависит от первой
                if existing_bet_type == BetType.EXACT_NUMBER:
                    # Первая была на гол → вторая ОБЯЗАТЕЛЬНО позиционная
                    if player.position != Position.FORWARD:
                        available.append(BetType.EVEN_ODD)
                    available.append(BetType.HIGH_LOW)
                else:
                    # Первая была НЕ на гол → вторая ОБЯЗАТЕЛЬНО на гол
                    available.append(BetType.EXACT_NUMBER)
            
            return available
        
        # ОСНОВНОЕ ВРЕМЯ — combo-aware логика.
        # Тип T доступен если:
        # - для ПЕРВОЙ ставки: существует валидный T2 такой что пара (T, T2)
        #   проходит правила И `_simulate_bets_safe_for_future([T, T2])`.
        # - для ВТОРОЙ ставки (T1 уже в match.bets): добавление T поверх
        #   валидно по правилам И `_simulate_bets_safe_for_future([T])`.
        existing_bet_type = self._get_player_bet_type_this_turn(match, manager_id, player.id)
        all_types = [BetType.EVEN_ODD, BetType.HIGH_LOW, BetType.EXACT_NUMBER]

        # Форварды не могут EVEN_ODD
        candidate_types = [t for t in all_types
                           if not (player.position == Position.FORWARD and t == BetType.EVEN_ODD)]

        if existing_bet_type is None:
            # Первая ставка: ищем для каждого T хотя бы один T2 чтобы (T,T2) проходила
            for t1 in candidate_types:
                for t2 in all_types:
                    if not self._is_pair_rules_valid(match, manager_id, player, t1, t2):
                        continue
                    if not self._simulate_bets_safe_for_future(
                        match, manager_id, player, [t1, t2]
                    ):
                        continue
                    available.append(t1)
                    break
        else:
            # Вторая ставка: проверяем добавление одиночной T2 поверх T1.
            # Используем validate_bet (одиночная валидация против текущего
            # состояния, T1 уже в match.bets и учтён в счётчиках).
            from uuid import uuid4 as _uuid4
            for t2 in candidate_types:
                # Минимальный bet для проверки (поля с конкретными значениями
                # не валидируются здесь — проверяются только типы и квоты).
                hypo_kwargs = {
                    "id": _uuid4(),
                    "match_id": match.id,
                    "manager_id": manager_id,
                    "player_id": player.id,
                    "turn_number": (match.current_turn.turn_number if match.current_turn else 1),
                    "bet_type": t2,
                }
                from ..models.bet import EvenOddChoice, HighLowChoice
                if t2 == BetType.EVEN_ODD:
                    hypo_kwargs["even_odd_choice"] = EvenOddChoice.EVEN
                elif t2 == BetType.HIGH_LOW:
                    hypo_kwargs["high_low_choice"] = HighLowChoice.HIGH
                elif t2 == BetType.EXACT_NUMBER:
                    hypo_kwargs["exact_number"] = 1
                hypo = Bet(**hypo_kwargs)
                try:
                    self.validate_bet(match, manager_id, player, hypo)
                except ValueError:
                    continue
                if not self._simulate_bets_safe_for_future(
                    match, manager_id, player, [t2]
                ):
                    continue
                available.append(t2)

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
