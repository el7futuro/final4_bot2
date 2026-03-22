# src/platforms/telegram/storage.py
"""In-memory хранилище для MVP (без PostgreSQL/Redis)"""

from uuid import UUID, uuid4
from typing import Dict, Optional, List
from datetime import datetime

from src.core.models.match import Match, MatchStatus
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.engine.game_engine import GameEngine


class InMemoryUser:
    """Пользователь в памяти"""
    def __init__(self, telegram_id: int, username: str):
        self.id: UUID = uuid4()
        self.telegram_id: int = telegram_id
        self.username: str = username
        self.rating: int = 1000
        self.matches_played: int = 0
        self.matches_won: int = 0
        self.created_at: datetime = datetime.utcnow()


class InMemoryStorage:
    """In-memory хранилище для Telegram бота"""
    
    def __init__(self):
        # Пользователи: telegram_id -> user
        self.users: Dict[int, InMemoryUser] = {}
        
        # Матчи: match_id -> match
        self.matches: Dict[UUID, Match] = {}
        
        # Команды пользователей: user_id -> team
        self.user_teams: Dict[UUID, Team] = {}
        
        # Ожидающие матчи (для random matchmaking)
        self.waiting_matches: List[UUID] = []
        
        # GameEngine
        self.engine = GameEngine()
    
    # =========== USERS ===========
    
    def get_or_create_user(self, telegram_id: int, username: str) -> InMemoryUser:
        """Получить или создать пользователя"""
        if telegram_id not in self.users:
            user = InMemoryUser(telegram_id, username)
            self.users[telegram_id] = user
            # Создаём команду по умолчанию
            self._create_default_team(user.id, username)
        return self.users[telegram_id]
    
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[InMemoryUser]:
        """Получить пользователя по Telegram ID"""
        return self.users.get(telegram_id)
    
    def get_user_by_id(self, user_id: UUID) -> Optional[InMemoryUser]:
        """Получить пользователя по ID"""
        for user in self.users.values():
            if user.id == user_id:
                return user
        return None
    
    # =========== TEAMS ===========
    
    def _create_default_team(self, user_id: UUID, username: str) -> Team:
        """Создать команду по умолчанию с 16 игроками"""
        players = []
        number = 1
        
        # 1 вратарь
        players.append(Player(name="Вратарь", position=Position.GOALKEEPER, number=number))
        number += 1
        
        # 5 защитников
        for i in range(5):
            players.append(Player(name=f"Защитник {i+1}", position=Position.DEFENDER, number=number))
            number += 1
        
        # 6 полузащитников
        for i in range(6):
            players.append(Player(name=f"Полузащитник {i+1}", position=Position.MIDFIELDER, number=number))
            number += 1
        
        # 4 нападающих
        for i in range(4):
            players.append(Player(name=f"Нападающий {i+1}", position=Position.FORWARD, number=number))
            number += 1
        
        team = Team(manager_id=user_id, name=f"Команда {username}", players=players)
        self.user_teams[user_id] = team
        return team
    
    def get_user_team(self, user_id: UUID) -> Optional[Team]:
        """Получить команду пользователя"""
        return self.user_teams.get(user_id)
    
    # =========== MATCHES ===========
    
    def get_match(self, match_id: UUID) -> Optional[Match]:
        """Получить матч по ID"""
        return self.matches.get(match_id)
    
    def get_user_active_match(self, user_id: UUID) -> Optional[Match]:
        """Получить активный матч пользователя"""
        for match in self.matches.values():
            if match.status in [MatchStatus.WAITING_FOR_OPPONENT, MatchStatus.SETTING_LINEUP, 
                               MatchStatus.IN_PROGRESS, MatchStatus.EXTRA_TIME, MatchStatus.PENALTIES]:
                if match.is_participant(user_id):
                    return match
        return None
    
    def save_match(self, match: Match) -> None:
        """Сохранить матч"""
        self.matches[match.id] = match
    
    def add_waiting_match(self, match_id: UUID) -> None:
        """Добавить матч в очередь ожидания"""
        if match_id not in self.waiting_matches:
            self.waiting_matches.append(match_id)
    
    def remove_waiting_match(self, match_id: UUID) -> None:
        """Убрать матч из очереди ожидания"""
        if match_id in self.waiting_matches:
            self.waiting_matches.remove(match_id)
    
    def find_waiting_match(self, exclude_user_id: UUID) -> Optional[Match]:
        """Найти ожидающий матч (кроме своего)"""
        for match_id in self.waiting_matches:
            match = self.matches.get(match_id)
            if match and match.manager1_id != exclude_user_id:
                return match
        return None


# Глобальный экземпляр
_storage: Optional[InMemoryStorage] = None


def get_storage() -> InMemoryStorage:
    """Получить глобальное хранилище"""
    global _storage
    if _storage is None:
        _storage = InMemoryStorage()
    return _storage
