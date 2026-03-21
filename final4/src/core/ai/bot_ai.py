# src/core/ai/bot_ai.py
"""AI для бота Final 4"""

from uuid import UUID
from typing import List, Tuple, Optional
import random

from ..models.match import Match
from ..models.team import Team, Formation, FORMATION_STRUCTURE
from ..models.player import Player, Position
from ..models.bet import Bet, BetType, EvenOddChoice, HighLowChoice
from ..engine import BOT_USER_ID


class AIStrategy:
    """Базовая стратегия бота"""
    
    def choose_formation(self, team: Team) -> Formation:
        raise NotImplementedError
    
    def choose_lineup(self, team: Team, formation: Formation) -> List[UUID]:
        raise NotImplementedError
    
    def choose_bets(self, match: Match, player: Player, available_types: List[BetType]) -> List[Bet]:
        raise NotImplementedError


class RandomStrategy(AIStrategy):
    """Случайная стратегия — для простого бота"""
    
    def choose_formation(self, team: Team) -> Formation:
        return random.choice(list(Formation))
    
    def choose_lineup(self, team: Team, formation: Formation) -> List[UUID]:
        structure = FORMATION_STRUCTURE[formation]
        lineup = []
        
        for position_str, count in structure.items():
            position = Position(position_str)
            players = [p for p in team.players if p.position == position and p.is_available]
            selected = random.sample(players, min(count, len(players)))
            lineup.extend([p.id for p in selected])
        
        return lineup
    
    def choose_bets(self, match: Match, player: Player, available_types: List[BetType]) -> List[Bet]:
        if not available_types:
            return []
        
        bets = []
        
        # Первая ставка
        bet_type = random.choice(available_types)
        bets.append(self._create_bet(match, player, bet_type))
        
        # Вторая ставка (50% шанс)
        if random.random() > 0.5 and len(available_types) > 0:
            remaining_types = [t for t in available_types if t != BetType.EVEN_ODD]
            if remaining_types:
                bet_type = random.choice(remaining_types)
                bets.append(self._create_bet(match, player, bet_type))
        
        return bets
    
    def _create_bet(self, match: Match, player: Player, bet_type: BetType) -> Bet:
        bet = Bet(
            match_id=match.id,
            manager_id=BOT_USER_ID,
            player_id=player.id,
            turn_number=match.current_turn.turn_number if match.current_turn else 1,
            bet_type=bet_type
        )
        
        if bet_type == BetType.EVEN_ODD:
            bet.even_odd_choice = random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
        elif bet_type == BetType.HIGH_LOW:
            bet.high_low_choice = random.choice([HighLowChoice.LOW, HighLowChoice.HIGH])
        elif bet_type == BetType.EXACT_NUMBER:
            bet.exact_number = random.randint(1, 6)
        
        return bet


class SmartStrategy(AIStrategy):
    """Умная стратегия — анализирует вероятности"""
    
    def choose_formation(self, team: Team) -> Formation:
        # Выбираем формацию с наибольшим числом атакующих если много форвардов
        forwards = [p for p in team.players if p.position == Position.FORWARD]
        if len(forwards) >= 4:
            return Formation.F_3_3_4
        return Formation.F_4_3_3
    
    def choose_lineup(self, team: Team, formation: Formation) -> List[UUID]:
        structure = FORMATION_STRUCTURE[formation]
        lineup = []
        
        for position_str, count in structure.items():
            position = Position(position_str)
            players = [p for p in team.players if p.position == position and p.is_available]
            # Берём первых count игроков (можно добавить логику выбора лучших)
            selected = players[:count]
            lineup.extend([p.id for p in selected])
        
        return lineup
    
    def choose_bets(self, match: Match, player: Player, available_types: List[BetType]) -> List[Bet]:
        if not available_types:
            return []
        
        bets = []
        
        # Умная стратегия: приоритет HIGH_LOW (50% шанс) над EXACT_NUMBER (17%)
        if BetType.HIGH_LOW in available_types:
            bets.append(self._create_bet(match, player, BetType.HIGH_LOW))
        elif BetType.EVEN_ODD in available_types:
            bets.append(self._create_bet(match, player, BetType.EVEN_ODD))
        
        # Для форвардов добавляем ставку на гол
        if player.position == Position.FORWARD and BetType.EXACT_NUMBER in available_types:
            bets.append(self._create_bet(match, player, BetType.EXACT_NUMBER))
        
        return bets
    
    def _create_bet(self, match: Match, player: Player, bet_type: BetType) -> Bet:
        bet = Bet(
            match_id=match.id,
            manager_id=BOT_USER_ID,
            player_id=player.id,
            turn_number=match.current_turn.turn_number if match.current_turn else 1,
            bet_type=bet_type
        )
        
        if bet_type == BetType.EVEN_ODD:
            # Выбираем чёт — статистически люди чаще выбирают нечёт
            bet.even_odd_choice = EvenOddChoice.EVEN
        elif bet_type == BetType.HIGH_LOW:
            # Случайный выбор
            bet.high_low_choice = random.choice([HighLowChoice.LOW, HighLowChoice.HIGH])
        elif bet_type == BetType.EXACT_NUMBER:
            # Чаще выпадают средние числа
            bet.exact_number = random.choice([3, 4, 3, 4, 2, 5])
        
        return bet


class Final4BotAI:
    """Главный класс бота AI"""
    
    def __init__(self, strategy: Optional[AIStrategy] = None):
        self.strategy = strategy or SmartStrategy()
    
    def prepare_team(self, team: Team) -> Tuple[Formation, List[UUID]]:
        """Подготовить команду к матчу"""
        formation = self.strategy.choose_formation(team)
        lineup = self.strategy.choose_lineup(team, formation)
        return formation, lineup
    
    def make_turn(
        self,
        match: Match,
        available_bet_types_func
    ) -> List[Bet]:
        """
        Сделать ход (выбрать ставки).
        
        Args:
            match: Текущий матч
            available_bet_types_func: Функция для получения доступных типов ставок
        """
        team = match.get_team(BOT_USER_ID)
        if not team:
            return []
        
        current_player = self._get_current_player(match, team)
        if not current_player:
            return []
        
        available_types = available_bet_types_func(match, BOT_USER_ID, current_player.id)
        return self.strategy.choose_bets(match, current_player, available_types)
    
    def _get_current_player(self, match: Match, team: Team) -> Optional[Player]:
        """Определить текущего игрока для ставки"""
        field_players = team.get_field_players()
        if not field_players:
            return None
        
        turn = match.current_turn.turn_number if match.current_turn else 1
        
        # Порядок: вратарь, защитники, полузащитники, форварды
        order = []
        gk = team.get_goalkeeper()
        if gk:
            order.append(gk)
        order.extend([p for p in field_players if p.position == Position.DEFENDER])
        order.extend([p for p in field_players if p.position == Position.MIDFIELDER])
        order.extend([p for p in field_players if p.position == Position.FORWARD])
        
        if not order:
            return None
        
        # Индекс в цикле (каждый ход — следующий игрок)
        idx = (turn - 1) % len(order)
        return order[idx]
    
    def choose_card_target(
        self,
        match: Match,
        targets: List[Player],
        is_positive: bool
    ) -> Optional[UUID]:
        """Выбрать цель для карточки Свисток"""
        if not targets:
            return None
        
        if is_positive:
            # Для позитивных карточек — выбираем форварда
            forwards = [p for p in targets if p.position == Position.FORWARD]
            if forwards:
                return random.choice(forwards).id
            return random.choice(targets).id
        else:
            # Для негативных — игрок с наибольшим количеством действий
            best = max(targets, key=lambda p: p.get_total_actions())
            return best.id
