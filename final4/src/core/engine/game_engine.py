# src/core/engine/game_engine.py
"""Главный игровой движок"""

from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, List, Tuple, Dict
import random

from ..models.match import (
    Match, MatchStatus, MatchType, MatchPhase,
    TurnState, MatchResult, MatchScore
)
from ..models.team import Team, Formation
from ..models.player import Player, Position
from ..models.bet import Bet, BetType, BetOutcome
from ..models.whistle_card import WhistleCard
from ..models.match_history import MatchHistory, PlayerMatchStats

from .bet_tracker import BetTracker
from .action_calculator import ActionCalculator
from .score_calculator import ScoreCalculator
from .whistle_deck import WhistleDeck


# ID бота для матчей vs_bot
BOT_USER_ID = UUID('00000000-0000-0000-0000-000000000001')


class GameEngine:
    """Главный игровой движок Final 4"""
    
    def __init__(self):
        self.bet_tracker = BetTracker()
        self.action_calculator = ActionCalculator()
        self.score_calculator = ScoreCalculator()
        # История матчей по ID
        self._match_histories: Dict[UUID, MatchHistory] = {}
    
    def create_match(
        self,
        manager_id: UUID,
        match_type: MatchType,
        platform: str = "telegram"
    ) -> Match:
        """Создать новый матч"""
        match = Match(
            id=uuid4(),
            match_type=match_type,
            manager1_id=manager_id,
            created_at=datetime.utcnow(),
            platform=platform,
            whistle_deck=WhistleDeck.create_deck()
        )
        
        if match_type == MatchType.VS_BOT:
            match.manager2_id = BOT_USER_ID
            match.status = MatchStatus.SETTING_LINEUP
        
        return match
    
    def join_match(self, match: Match, manager_id: UUID) -> Match:
        """Присоединиться к матчу"""
        if match.status != MatchStatus.WAITING_FOR_OPPONENT:
            raise ValueError("Матч не ожидает соперника")
        if match.manager2_id is not None:
            raise ValueError("Матч уже имеет соперника")
        if match.manager1_id == manager_id:
            raise ValueError("Нельзя играть против себя")
        
        match.manager2_id = manager_id
        match.status = MatchStatus.SETTING_LINEUP
        return match
    
    def set_team_lineup(
        self,
        match: Match,
        manager_id: UUID,
        team: Team,
        formation: Formation,
        player_ids: List[UUID]
    ) -> Match:
        """Установить состав команды"""
        if match.status != MatchStatus.SETTING_LINEUP:
            raise ValueError("Нельзя менять состав в текущем статусе")
        
        if not match.is_participant(manager_id):
            raise ValueError("Вы не участник этого матча")
        
        team.set_formation(formation)
        if not team.set_lineup(player_ids):
            raise ValueError("Невалидный состав для формации")
        
        if manager_id == match.manager1_id:
            match.team1 = team
        else:
            match.team2 = team
        
        # Проверяем, оба ли готовы
        if match.team1 and match.team2:
            match = self._start_match(match)
        
        return match
    
    def _start_match(self, match: Match) -> Match:
        """Начать матч"""
        match.status = MatchStatus.IN_PROGRESS
        match.started_at = datetime.utcnow()
        match.current_turn = TurnState(
            turn_number=1,
            # ИСПРАВЛЕНО: Убираем current_manager_id — оба ставят одновременно
            current_manager_id=None  # Deprecated, но оставляем для обратной совместимости
        )
        
        # Инициализируем историю матча
        self._init_match_history(match)
        
        return match
    
    def _init_match_history(self, match: Match) -> None:
        """Инициализировать историю матча"""
        history = MatchHistory(match_id=match.id)
        
        if match.team1 and match.team2:
            history.init_players(
                match.manager1_id, match.team1.players,
                match.manager2_id, match.team2.players
            )
        
        self._match_histories[match.id] = history
    
    def get_match_history(self, match: Match) -> Optional[MatchHistory]:
        """Получить историю матча"""
        return self._match_histories.get(match.id)
    
    def get_player_stats(
        self, 
        match: Match, 
        manager_id: UUID, 
        player_id: UUID
    ) -> Optional[PlayerMatchStats]:
        """Получить статистику игрока"""
        history = self.get_match_history(match)
        if not history:
            return None
        return history.get_player_stats(manager_id, player_id, match.manager1_id)
    
    def print_current_stats(self, match: Match) -> str:
        """Вывести текущую статистику матча"""
        history = self.get_match_history(match)
        if not history:
            return "История матча не найдена"
        
        team1_name = match.team1.name if match.team1 else "Команда 1"
        team2_name = match.team2.name if match.team2 else "Команда 2"
        
        return history.print_current_stats(match.manager1_id, team1_name, team2_name)
    
    def place_bet(
        self,
        match: Match,
        manager_id: UUID,
        player_id: UUID,
        bet: Bet
    ) -> Tuple[Match, Bet]:
        """
        Разместить ставку.
        
        ИСПРАВЛЕНО: Теперь оба менеджера делают ставки одновременно.
        Кубик бросается только когда ОБА завершили ставки.
        """
        if not match.is_participant(manager_id):
            raise ValueError("Вы не участник этого матча")
        
        if not match.current_turn:
            raise ValueError("Ход не начат")
        
        if match.current_turn.dice_rolled:
            raise ValueError("Кубик уже брошен, ставки закрыты")
        
        # Проверяем, не завершил ли уже этот менеджер ставки
        if manager_id == match.manager1_id and match.current_turn.manager1_ready:
            raise ValueError("Вы уже завершили ставки в этом ходу")
        if manager_id == match.manager2_id and match.current_turn.manager2_ready:
            raise ValueError("Вы уже завершили ставки в этом ходу")
        
        team = match.get_team(manager_id)
        if not team:
            raise ValueError("Команда не найдена")
        
        player = team.get_player_by_id(player_id)
        if not player:
            raise ValueError("Игрок не найден")
        
        # Проверяем, что ставки делаются на ОДНОГО игрока за ход
        if manager_id == match.manager1_id:
            if match.current_turn.manager1_player_id and match.current_turn.manager1_player_id != player_id:
                raise ValueError("В этом ходу нужно делать ставки на одного игрока")
        else:
            if match.current_turn.manager2_player_id and match.current_turn.manager2_player_id != player_id:
                raise ValueError("В этом ходу нужно делать ставки на одного игрока")
        
        # Валидация правил ставок
        self.bet_tracker.validate_bet(match, manager_id, player, bet)
        
        # Заполняем поля ставки
        bet.id = uuid4()
        bet.match_id = match.id
        bet.manager_id = manager_id
        bet.player_id = player_id
        bet.turn_number = match.current_turn.turn_number
        
        # Добавляем ставку
        match.bets.append(bet)
        
        # Регистрируем в текущем ходе
        if manager_id == match.manager1_id:
            match.current_turn.manager1_player_id = player_id
            match.current_turn.manager1_bets.append(bet.id)
        else:
            match.current_turn.manager2_player_id = player_id
            match.current_turn.manager2_bets.append(bet.id)
        
        # Для обратной совместимости
        match.current_turn.bets_placed.append(bet.id)
        
        return match, bet
    
    def confirm_bets(self, match: Match, manager_id: UUID) -> Match:
        """
        Подтвердить завершение ставок менеджером.
        
        НОВЫЙ МЕТОД: Менеджер вызывает после того, как сделал все ставки.
        """
        if not match.is_participant(manager_id):
            raise ValueError("Вы не участник этого матча")
        
        if not match.current_turn:
            raise ValueError("Ход не начат")
        
        if match.current_turn.dice_rolled:
            raise ValueError("Кубик уже брошен")
        
        turn_number = match.current_turn.turn_number
        required_bets = match.current_turn.get_required_bets_count()
        
        # Проверяем количество ставок
        if manager_id == match.manager1_id:
            current_bets = len(match.current_turn.manager1_bets)
            if current_bets < required_bets:
                raise ValueError(f"Нужно сделать {required_bets} ставок (сделано {current_bets})")
            match.current_turn.manager1_ready = True
        else:
            current_bets = len(match.current_turn.manager2_bets)
            if current_bets < required_bets:
                raise ValueError(f"Нужно сделать {required_bets} ставок (сделано {current_bets})")
            match.current_turn.manager2_ready = True
        
        return match
    
    def can_roll_dice(self, match: Match) -> Tuple[bool, str]:
        """Проверить, можно ли бросить кубик (оба готовы?)"""
        if not match.current_turn:
            return False, "Ход не начат"
        
        if match.current_turn.dice_rolled:
            return False, "Кубик уже брошен"
        
        if not match.current_turn.both_ready():
            ready_status = []
            if match.current_turn.manager1_ready:
                ready_status.append("Менеджер 1 готов")
            else:
                ready_status.append("Менеджер 1 ещё делает ставки")
            if match.current_turn.manager2_ready:
                ready_status.append("Менеджер 2 готов")
            else:
                ready_status.append("Менеджер 2 ещё делает ставки")
            return False, "; ".join(ready_status)
        
        return True, "OK"
    
    def roll_dice(self, match: Match) -> Tuple[Match, int, Dict[UUID, List[Bet]]]:
        """
        Бросить кубик и определить результаты ставок ОБОИХ игроков.
        
        ИСПРАВЛЕНО: 
        - Один бросок для обоих менеджеров
        - Автоматическое вытягивание карточки при выигрыше
        - Запись статистики в MatchHistory
        
        Returns:
            (match, dice_value, won_bets_by_manager)
            won_bets_by_manager: {manager_id: [winning_bets]}
        """
        can_roll, reason = self.can_roll_dice(match)
        if not can_roll:
            raise ValueError(reason)
        
        # Бросок — ОДИН для обоих!
        dice_value = random.randint(1, 6)
        match.current_turn.dice_rolled = True
        match.current_turn.dice_value = dice_value
        
        # Получаем историю матча
        history = self.get_match_history(match)
        
        # Определяем результаты ставок для ОБОИХ менеджеров
        won_bets_by_manager: Dict[UUID, List[Bet]] = {
            match.manager1_id: [],
            match.manager2_id: []
        }
        
        # Обрабатываем все ставки этого хода
        all_turn_bet_ids = set(match.current_turn.bets_placed)
        
        for bet in match.bets:
            if bet.id not in all_turn_bet_ids:
                continue
            
            outcome = bet.resolve(dice_value)
            
            if outcome == BetOutcome.WON:
                won_bets_by_manager[bet.manager_id].append(bet)
                
                # Начисляем действия
                team = match.get_team(bet.manager_id)
                if team:
                    player = team.get_player_by_id(bet.player_id)
                    if player:
                        # Применяем результат ставки
                        saves, passes, goals = self.action_calculator.apply_bet_result(player, bet)
                        
                        # Записываем в историю
                        if history:
                            player_stats = history.get_player_stats(
                                bet.manager_id, bet.player_id, match.manager1_id
                            )
                            if player_stats:
                                # Отмечаем когда играл
                                if player_stats.turn_played is None:
                                    player_stats.turn_played = match.current_turn.turn_number
                                    player_stats.phase_played = match.phase
                                
                                # Записываем действия
                                if saves > 0:
                                    player_stats.add_saves(saves, f"ставка {bet.bet_type.value}")
                                if passes > 0:
                                    player_stats.add_passes(passes, f"ставка {bet.bet_type.value}")
                                if goals > 0:
                                    player_stats.add_goals(goals, f"ставка {bet.bet_type.value}")
        
        # Записываем игроков без выигрышей в историю (они тоже играли)
        if history:
            for manager_id in [match.manager1_id, match.manager2_id]:
                if manager_id == match.manager1_id:
                    player_id = match.current_turn.manager1_player_id
                else:
                    player_id = match.current_turn.manager2_player_id
                
                if player_id:
                    player_stats = history.get_player_stats(
                        manager_id, player_id, match.manager1_id
                    )
                    if player_stats and player_stats.turn_played is None:
                        player_stats.turn_played = match.current_turn.turn_number
                        player_stats.phase_played = match.phase
        
        # АВТОМАТИЧЕСКОЕ ВЫТЯГИВАНИЕ КАРТОЧЕК
        # Менеджер 1
        if won_bets_by_manager.get(match.manager1_id):
            match, card1 = self._auto_draw_whistle_card(match, match.manager1_id)
            if card1:
                match.current_turn.manager1_card_id = card1.id
        
        # Менеджер 2
        if match.manager2_id and won_bets_by_manager.get(match.manager2_id):
            match, card2 = self._auto_draw_whistle_card(match, match.manager2_id)
            if card2:
                match.current_turn.manager2_card_id = card2.id
        
        return match, dice_value, won_bets_by_manager
    
    def _auto_draw_whistle_card(
        self,
        match: Match,
        manager_id: UUID
    ) -> Tuple[Match, Optional[WhistleCard]]:
        """
        Автоматически вытянуть карточку Свисток при выигрыше ставки.
        
        Вызывается из roll_dice(), не требует отдельного вызова.
        """
        if not match.whistle_deck:
            return match, None
        
        card = WhistleDeck.draw_card(match.whistle_deck)
        if card:
            card.applied_by_manager_id = manager_id
            card.turn_applied = match.current_turn.turn_number if match.current_turn else 1
            match.whistle_cards_drawn.append(card)
        
        return match, card
    
    def draw_whistle_card(
        self,
        match: Match,
        manager_id: UUID
    ) -> Tuple[Match, Optional[WhistleCard]]:
        """
        Взять карточку Свисток (если есть выигравшие ставки).
        
        DEPRECATED: Карточки теперь вытягиваются автоматически в roll_dice().
        Этот метод оставлен для обратной совместимости.
        """
        if not match.is_participant(manager_id):
            raise ValueError("Вы не участник этого матча")
        
        if not match.current_turn:
            raise ValueError("Ход не начат")
        
        # Проверяем, не взята ли уже карточка
        if manager_id == match.manager1_id:
            if match.current_turn.manager1_card_id:
                # Карточка уже взята автоматически
                card = next((c for c in match.whistle_cards_drawn 
                            if c.id == match.current_turn.manager1_card_id), None)
                return match, card
        else:
            if match.current_turn.manager2_card_id:
                card = next((c for c in match.whistle_cards_drawn 
                            if c.id == match.current_turn.manager2_card_id), None)
                return match, card
        
        # Проверяем, есть ли выигравшие ставки
        turn_bets = match.get_turn_bets()
        won_any = any(b.outcome == BetOutcome.WON and b.manager_id == manager_id for b in turn_bets)
        
        # Для обратной совместимости
        match.current_turn.card_drawn = True
        
        if not won_any:
            return match, None
        
        if not match.whistle_deck:
            return match, None
        
        card = WhistleDeck.draw_card(match.whistle_deck)
        if card:
            card.applied_by_manager_id = manager_id
            card.turn_applied = match.current_turn.turn_number
            match.current_turn.card_id = card.id
            match.whistle_cards_drawn.append(card)
            
            # Записываем в новые поля
            if manager_id == match.manager1_id:
                match.current_turn.manager1_card_id = card.id
            else:
                match.current_turn.manager2_card_id = card.id
        
        return match, card
    
    def apply_whistle_card(
        self,
        match: Match,
        manager_id: UUID,
        card_id: UUID,
        target_player_id: Optional[UUID] = None
    ) -> Match:
        """Применить карточку Свисток"""
        if not match.is_participant(manager_id):
            raise ValueError("Вы не участник этого матча")
        
        # Находим карточку
        card = next((c for c in match.whistle_cards_drawn if c.id == card_id), None)
        if not card:
            raise ValueError("Карточка не найдена")
        
        if card.is_used:
            raise ValueError("Карточка уже использована")
        
        # Проверяем, что карточка принадлежит этому менеджеру
        if card.applied_by_manager_id != manager_id:
            raise ValueError("Это не ваша карточка")
        
        # Проверяем, нужна ли цель
        if card.requires_target() and not target_player_id:
            raise ValueError("Необходимо выбрать цель для карточки")
        
        # Получаем эффект и применяем
        effect = WhistleDeck.get_card_effect(card, match, manager_id, target_player_id)
        history = self.get_match_history(match)
        match = WhistleDeck.apply_effect(match, effect, history)
        
        card.is_used = True
        card.applied_to_player_id = target_player_id
        
        # Обновляем флаги
        if match.current_turn:
            if manager_id == match.manager1_id:
                match.current_turn.manager1_card_applied = True
            else:
                match.current_turn.manager2_card_applied = True
            match.current_turn.card_applied = True  # Для обратной совместимости
        
        return match
    
    def end_turn(self, match: Match) -> Match:
        """
        Завершить ход и перейти к следующему.
        
        ИСПРАВЛЕНО: Вызывается после броска кубика, когда оба менеджера 
        применили свои карточки (или отказались).
        """
        if not match.current_turn:
            raise ValueError("Ход не начат")
        
        if not match.current_turn.dice_rolled:
            raise ValueError("Кубик ещё не брошен")
        
        # Помечаем игроков этого хода как использованных
        # Менеджер 1
        if match.current_turn.manager1_player_id:
            match.mark_player_used(match.manager1_id, match.current_turn.manager1_player_id)
        
        # Менеджер 2
        if match.manager2_id and match.current_turn.manager2_player_id:
            match.mark_player_used(match.manager2_id, match.current_turn.manager2_player_id)
        
        # Пересчитываем статистику команд
        if match.team1:
            match.team1.calculate_stats()
        if match.team2:
            match.team2.calculate_stats()
        
        # Увеличиваем счётчик ходов (ОДИН ход = оба менеджера сделали ставки)
        if match.phase == MatchPhase.MAIN_TIME:
            match.total_turns_main += 1
        else:
            match.total_turns_extra += 1
        
        # Проверяем, закончился ли матч
        # В основное время: 11 ходов (оба ставят одновременно)
        if match.phase == MatchPhase.MAIN_TIME and match.total_turns_main >= 11:
            return self._end_main_time(match)
        
        # Дополнительное время: 5 ходов
        if match.phase == MatchPhase.EXTRA_TIME and match.total_turns_extra >= 5:
            return self._end_extra_time(match)
        
        # Переходим к следующему ходу
        match.current_turn = TurnState(
            turn_number=match.current_turn.turn_number + 1
        )
        
        return match
    
    def _end_main_time(self, match: Match) -> Match:
        """Завершить основное время"""
        if match.team1 and match.team2:
            score = self.score_calculator.calculate_score(match.team1, match.team2)
            match.score = score
            
            if score.manager1_goals != score.manager2_goals:
                return self._finish_match(match, MatchPhase.MAIN_TIME)
        
        # Ничья — дополнительное время
        match.phase = MatchPhase.EXTRA_TIME
        match.status = MatchStatus.EXTRA_TIME
        match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=match.manager1_id
        )
        return match
    
    def _end_extra_time(self, match: Match) -> Match:
        """Завершить дополнительное время"""
        if match.team1 and match.team2:
            score = self.score_calculator.calculate_score(match.team1, match.team2)
            match.score = score
            
            if score.manager1_goals != score.manager2_goals:
                return self._finish_match(match, MatchPhase.EXTRA_TIME)
        
        # Всё ещё ничья — пенальти
        match.phase = MatchPhase.PENALTIES
        match.status = MatchStatus.PENALTIES
        return self._start_penalties(match)
    
    def _start_penalties(self, match: Match) -> Match:
        """Начать серию пенальти"""
        match.current_turn = TurnState(
            turn_number=1,
            current_manager_id=match.manager1_id
        )
        return match
    
    def execute_penalty_kick(
        self,
        match: Match,
        manager_id: UUID,
        player_id: UUID
    ) -> Tuple[Match, bool]:
        """Выполнить пенальти. Возвращает (match, забит ли гол)"""
        if match.phase != MatchPhase.PENALTIES:
            raise ValueError("Не фаза пенальти")
        
        team = match.get_team(manager_id)
        if not team:
            raise ValueError("Команда не найдена")
        
        player = team.get_player_by_id(player_id)
        if not player:
            raise ValueError("Игрок не найден")
        
        # Гол забивается если у игрока есть передача
        goal_scored = player.stats.passes > 0
        
        if goal_scored:
            if manager_id == match.manager1_id:
                match.score.manager1_goals += 1
            else:
                match.score.manager2_goals += 1
        
        return match, goal_scored
    
    def _finish_match(self, match: Match, decided_by: MatchPhase) -> Match:
        """Завершить матч с результатом"""
        match.status = MatchStatus.FINISHED
        match.finished_at = datetime.utcnow()
        
        if match.score.manager1_goals > match.score.manager2_goals:
            winner_id = match.manager1_id
            loser_id = match.manager2_id
        else:
            winner_id = match.manager2_id
            loser_id = match.manager1_id
        
        match.result = MatchResult(
            winner_id=winner_id,
            loser_id=loser_id,
            final_score=match.score,
            decided_by=decided_by
        )
        
        return match
    
    def finish_by_lottery(self, match: Match) -> Match:
        """Определить победителя жребием (после всех пенальти)"""
        winner_id = random.choice([match.manager1_id, match.manager2_id])
        loser_id = match.manager2_id if winner_id == match.manager1_id else match.manager1_id
        
        match.status = MatchStatus.FINISHED
        match.finished_at = datetime.utcnow()
        match.result = MatchResult(
            winner_id=winner_id,
            loser_id=loser_id,
            final_score=match.score,
            decided_by=MatchPhase.PENALTIES,
            decided_by_lottery=True
        )
        
        return match
    
    def cancel_match(self, match: Match, manager_id: UUID) -> Match:
        """Отменить матч"""
        if match.status not in [MatchStatus.WAITING_FOR_OPPONENT, MatchStatus.SETTING_LINEUP]:
            raise ValueError("Нельзя отменить матч в текущем статусе")
        
        if not match.is_participant(manager_id):
            raise ValueError("Вы не участник этого матча")
        
        match.status = MatchStatus.CANCELLED
        match.finished_at = datetime.utcnow()
        
        return match
    
    def get_available_bet_types(
        self,
        match: Match,
        manager_id: UUID,
        player_id: UUID
    ) -> List[BetType]:
        """Получить доступные типы ставок для игрока"""
        team = match.get_team(manager_id)
        if not team:
            return []
        
        player = team.get_player_by_id(player_id)
        if not player:
            return []
        
        return self.bet_tracker.get_available_bet_types(match, manager_id, player)
    
    def get_available_players(
        self,
        match: Match,
        manager_id: UUID
    ) -> List[Player]:
        """
        Получить список доступных игроков для ставки в текущем ходе.
        
        ИСПРАВЛЕНО: Теперь проверяет, что у игрока есть минимум 2 РАЗНЫХ типа ставок.
        """
        team = match.get_team(manager_id)
        if not team:
            return []
        
        # Получаем базовый список доступных игроков
        base_available = match.get_available_players_for_betting(manager_id)
        
        # Фильтруем: оставляем только тех, у кого есть минимум 2 типа ставок
        turn_number = match.current_turn.turn_number if match.current_turn else 1
        
        final_available = []
        for player in base_available:
            # Вратарь на 1-м ходу — особый случай (1 ставка)
            if turn_number == 1 and player.position == Position.GOALKEEPER:
                available_types = self.bet_tracker.get_available_bet_types(match, manager_id, player)
                if available_types:
                    final_available.append(player)
                continue
            
            # Полевые игроки — нужно минимум 2 типа
            if player.position != Position.GOALKEEPER:
                available_types = self.bet_tracker.get_available_bet_types(match, manager_id, player)
                if len(available_types) >= 2:
                    final_available.append(player)
        
        return final_available
    
    def can_player_bet(
        self,
        match: Match,
        manager_id: UUID,
        player_id: UUID
    ) -> tuple[bool, str]:
        """
        Проверить, может ли игрок делать ставку.
        
        Returns:
            (can_bet, reason)
        """
        team = match.get_team(manager_id)
        if not team:
            return False, "Команда не найдена"
        
        player = team.get_player_by_id(player_id)
        if not player:
            return False, "Игрок не найден"
        
        return self.bet_tracker.can_player_bet(match, manager_id, player)
    
    def check_deadlock_risk(
        self,
        match: Match,
        manager_id: UUID,
        proposed_player_id: UUID,
        proposed_bet_types: List[BetType]
    ) -> Tuple[bool, str]:
        """
        Проверить риск дедлока при выборе игрока.
        
        Применяется начиная с 5-го хода.
        """
        return self.bet_tracker.check_deadlock_risk(
            match, manager_id, proposed_player_id, proposed_bet_types
        )
    
    # ==================== СЕРИЯ ПЕНАЛЬТИ ====================
    
    def start_penalty_shootout(self, match: Match) -> Match:
        """
        Начать серию пенальти после ничьей в дополнительное время.
        
        Правила:
        - 5 ударов от каждого менеджера
        - Удар = ставка на больше/меньше
        - Угадал = гол
        - Не угадал = отбитие сопернику
        - Если после 5 ударов ничья — до первого промаха
        """
        if match.phase != MatchPhase.EXTRA_TIME:
            raise ValueError("Пенальти возможны только после дополнительного времени")
        
        match.phase = MatchPhase.PENALTIES
        match.status = MatchStatus.PENALTIES
        match.current_turn = TurnState(turn_number=1)
        
        return match
    
    def take_penalty(
        self,
        match: Match,
        manager_id: UUID,
        high_or_low: str  # "high" (4-6) или "low" (1-3)
    ) -> Tuple[Match, int, bool, Optional[UUID]]:
        """
        Выполнить удар с пенальти.
        
        Args:
            match: Матч
            manager_id: ID бьющего менеджера
            high_or_low: "high" (4-6) или "low" (1-3)
        
        Returns:
            (match, dice_value, scored, opponent_save_player_id)
            - scored: True если гол, False если промах
            - opponent_save_player_id: ID игрока соперника, который получает отбитие при промахе
        """
        if match.phase != MatchPhase.PENALTIES:
            raise ValueError("Матч не в фазе пенальти")
        
        if not match.is_participant(manager_id):
            raise ValueError("Вы не участник этого матча")
        
        # Бросок кубика
        dice_value = random.randint(1, 6)
        
        # Проверяем угадал ли
        if high_or_low == "high":
            scored = dice_value >= 4
        else:  # low
            scored = dice_value <= 3
        
        # Обновляем счёт пенальти
        if scored:
            if manager_id == match.manager1_id:
                match.score.manager1_goals += 1
            else:
                match.score.manager2_goals += 1
            opponent_save_player_id = None
        else:
            # Соперник получает отбитие — нужно выбрать игрока
            opponent_id = match.get_opponent_id(manager_id)
            opponent_team = match.get_opponent_team(manager_id)
            opponent_save_player_id = None
            
            # Автоматически даём отбитие вратарю или первому доступному
            if opponent_team:
                gk = opponent_team.get_goalkeeper()
                if gk:
                    gk.add_saves(1)
                    opponent_save_player_id = gk.id
        
        # Увеличиваем счётчик ударов
        if match.current_turn:
            match.current_turn.turn_number += 1
        
        return match, dice_value, scored, opponent_save_player_id
    
    def check_penalty_winner(self, match: Match) -> Optional[UUID]:
        """
        Проверить, определился ли победитель в серии пенальти.
        
        Returns:
            ID победителя или None если серия продолжается
        """
        if match.phase != MatchPhase.PENALTIES:
            return None
        
        turn = match.current_turn.turn_number if match.current_turn else 1
        
        goals1 = match.score.manager1_goals
        goals2 = match.score.manager2_goals
        
        # Основная серия (10 ударов = 5 от каждого)
        if turn <= 10:
            # Проверяем, можно ли определить победителя досрочно
            remaining_kicks_m1 = max(0, 5 - (turn // 2 + turn % 2))  # Оставшиеся удары м1
            remaining_kicks_m2 = max(0, 5 - turn // 2)  # Оставшиеся удары м2
            
            # М1 выиграл досрочно
            if goals1 > goals2 + remaining_kicks_m2:
                return match.manager1_id
            
            # М2 выиграл досрочно
            if goals2 > goals1 + remaining_kicks_m1:
                return match.manager2_id
            
            # После 10 ударов
            if turn > 10:
                if goals1 > goals2:
                    return match.manager1_id
                elif goals2 > goals1:
                    return match.manager2_id
                # Иначе — продолжаем до первого промаха
        
        else:
            # Серия до первого промаха (после основных 10 ударов)
            # Каждые 2 удара (по одному от каждого) проверяем
            if turn % 2 == 0:  # Оба пробили
                if goals1 > goals2:
                    return match.manager1_id
                elif goals2 > goals1:
                    return match.manager2_id
        
        return None
    
    def finish_penalty_shootout(self, match: Match, winner_id: UUID) -> Match:
        """Завершить серию пенальти"""
        match.status = MatchStatus.FINISHED
        match.finished_at = datetime.utcnow()
        
        loser_id = match.get_opponent_id(winner_id)
        
        match.result = MatchResult(
            winner_id=winner_id,
            loser_id=loser_id,
            final_score=match.score,
            decided_by=MatchPhase.PENALTIES
        )
        
        return match
    
    # ==================== РОЗЫГРЫШ ПЕНАЛЬТИ (карточка) ====================
    
    def resolve_penalty_card(
        self,
        match: Match,
        manager_id: UUID,
        high_or_low: str  # "high" или "low"
    ) -> Tuple[Match, int, bool]:
        """
        Разыграть карточку Пенальти.
        
        По правилам:
        - Менеджер ставит на больше (4-6) или меньше (1-3)
        - Если угадал → его игрок текущего хода получает ГОЛ
        - Если не угадал → игрок СОПЕРНИКА текущего хода получает ОТБИТИЕ
        
        Returns:
            (match, dice_value, scored)
        """
        if not match.current_turn:
            raise ValueError("Ход не начат")
        
        # Бросок кубика
        dice_value = random.randint(1, 6)
        
        # Проверяем
        if high_or_low == "high":
            scored = dice_value >= 4
        else:
            scored = dice_value <= 3
        
        # Находим игроков текущего хода
        if manager_id == match.manager1_id:
            own_player_id = match.current_turn.manager1_player_id
            opponent_player_id = match.current_turn.manager2_player_id
        else:
            own_player_id = match.current_turn.manager2_player_id
            opponent_player_id = match.current_turn.manager1_player_id
        
        if scored:
            # Свой игрок получает гол
            if own_player_id:
                team = match.get_team(manager_id)
                if team:
                    player = team.get_player_by_id(own_player_id)
                    if player:
                        player.add_goals(1)
        else:
            # Игрок соперника получает отбитие
            if opponent_player_id:
                opponent_id = match.get_opponent_id(manager_id)
                if opponent_id:
                    opponent_team = match.get_opponent_team(manager_id)
                    if opponent_team:
                        player = opponent_team.get_player_by_id(opponent_player_id)
                        if player:
                            player.add_saves(1)
        
        return match, dice_value, scored
