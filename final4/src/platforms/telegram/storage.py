# src/platforms/telegram/storage.py
"""Гибридное хранилище: in-memory кэш + PostgreSQL персистентность"""

import asyncio
import logging
from uuid import UUID, uuid4
from typing import Dict, Optional, List
from datetime import datetime, timezone

from src.core.models.match import Match, MatchStatus
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.engine.game_engine import GameEngine

logger = logging.getLogger(__name__)


class InMemoryUser:
    """Пользователь в памяти"""
    def __init__(self, telegram_id: int, username: str, user_id: UUID = None):
        self.id: UUID = user_id or uuid4()
        self.telegram_id: int = telegram_id
        self.username: str = username
        self.rating: int = 1000
        self.matches_played: int = 0
        self.matches_won: int = 0
        self.created_at: datetime = datetime.now(timezone.utc)
        self._db_synced: bool = False  # Уже есть в БД?


class HybridStorage:
    """In-memory кэш + PostgreSQL для персистентности.
    
    Все чтения — из памяти (быстро).
    Записи — в память + фоновая задача в PostgreSQL.
    """
    
    def __init__(self):
        self.users: Dict[int, InMemoryUser] = {}
        self.matches: Dict[UUID, Match] = {}
        self.user_teams: Dict[UUID, Team] = {}
        self.waiting_matches: List[UUID] = []
        self.engine = GameEngine()
        
        self._db = None
        self._db_enabled = False
    
    async def init_db(self):
        """Инициализировать подключение к PostgreSQL"""
        try:
            from src.infrastructure.db.database import Database
            self._db = Database()
            # Проверяем подключение
            async with self._db.session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
            self._db_enabled = True
            logger.info("[DB] PostgreSQL подключен")
            # Создаём бот-юзера если нет
            await self._ensure_bot_user()
            # Загружаем данные из БД
            await self._load_from_db()
        except Exception as e:
            logger.warning(f"[DB] PostgreSQL недоступен, работаем in-memory: {e}")
            self._db_enabled = False
    
    async def _ensure_bot_user(self):
        """Создать бот-юзера в БД если его нет"""
        try:
            from src.core.engine.game_engine import BOT_USER_ID
            async with self._db.session() as session:
                from src.infrastructure.db.models import UserModel
                from sqlalchemy import select
                result = await session.execute(
                    select(UserModel).where(UserModel.id == BOT_USER_ID)
                )
                if not result.scalar_one_or_none():
                    bot_user = UserModel(
                        id=BOT_USER_ID, username="Bot", plan="free",
                        rating=1000, matches_played=0, matches_won=0,
                        matches_lost=0, matches_draw=0, tournaments_won=0,
                        goals_scored=0, goals_conceded=0, win_streak=0,
                        best_win_streak=0, matches_today=0, is_banned=False
                    )
                    session.add(bot_user)
                    logger.info("[DB] Bot user created")
        except Exception as e:
            logger.error(f"[DB] Failed to ensure bot user: {e}")

    async def _load_from_db(self):
        """Загрузить пользователей и активные матчи из БД"""
        if not self._db_enabled:
            return
        try:
            async with self._db.session() as session:
                from src.infrastructure.db.models import UserModel, MatchModel
                from sqlalchemy import select
                
                # Загружаем пользователей
                result = await session.execute(select(UserModel))
                for model in result.scalars().all():
                    user = InMemoryUser(
                        telegram_id=model.telegram_id,
                        username=model.username,
                        user_id=model.id
                    )
                    user.rating = model.rating
                    user.matches_played = model.matches_played
                    user.matches_won = model.matches_won
                    user.created_at = model.created_at
                    user._db_synced = True
                    self.users[model.telegram_id] = user
                
                # Загружаем активные матчи
                active_statuses = [
                    'waiting_for_opponent', 'setting_lineup',
                    'in_progress', 'extra_time', 'penalties'
                ]
                result = await session.execute(
                    select(MatchModel).where(MatchModel.status.in_(active_statuses))
                )
                from src.infrastructure.repositories.match_repository import MatchRepository
                repo = MatchRepository(session)
                for model in result.scalars().all():
                    match = repo._to_domain(model)
                    self.matches[match.id] = match
                    if match.status == MatchStatus.WAITING_FOR_OPPONENT:
                        self.waiting_matches.append(match.id)

                # Загружаем последние завершённые матчи каждого пользователя,
                # чтобы кнопка "История" работала после перезапуска бота.
                # Берём последние 100 finished матчей по created_at.
                from sqlalchemy import desc
                result = await session.execute(
                    select(MatchModel)
                    .where(MatchModel.status == 'finished')
                    .order_by(desc(MatchModel.created_at))
                    .limit(100)
                )
                for model in result.scalars().all():
                    if model.id not in self.matches:
                        try:
                            match = repo._to_domain(model)
                            self.matches[match.id] = match
                        except Exception as e:
                            logger.warning(
                                f"[DB] Failed to load finished match {model.id}: {e}"
                            )
                
                # Загружаем команды
                from src.infrastructure.db.models import TeamModel
                result = await session.execute(select(TeamModel))
                from src.infrastructure.repositories.match_repository import MatchRepository as MR
                for model in result.scalars().all():
                    try:
                        team_data = {"id": str(model.id), "manager_id": str(model.user_id),
                                     "name": model.name, "players": model.players or []}
                        # Простой парсинг
                        players = []
                        for p_data in team_data.get("players", []):
                            if isinstance(p_data, dict):
                                pos = p_data.get("position", "midfielder")
                                if isinstance(pos, str):
                                    p_data["position"] = Position(pos)
                                players.append(Player(**p_data))
                        if players:
                            team = Team(
                                manager_id=model.user_id,
                                name=model.name,
                                players=players
                            )
                            self.user_teams[model.user_id] = team
                    except Exception as e:
                        logger.warning(f"[DB] Failed to load team {model.id}: {e}")
                
                logger.info(f"[DB] Загружено: {len(self.users)} пользователей, "
                           f"{len(self.matches)} активных матчей, "
                           f"{len(self.user_teams)} команд")
        except Exception as e:
            logger.error(f"[DB] Ошибка загрузки из БД: {e}")
    
    def _bg_save(self, coro):
        """Запустить фоновое сохранение в БД"""
        if not self._db_enabled:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            pass
    
    # =========== USERS ===========
    
    def get_or_create_user(self, telegram_id: int, username: str) -> InMemoryUser:
        """Получить или создать пользователя"""
        if telegram_id not in self.users:
            user = InMemoryUser(telegram_id, username)
            self.users[telegram_id] = user
            self._create_default_team(user.id, username)
            self._bg_save(self._db_create_user(user))
        return self.users[telegram_id]
    
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[InMemoryUser]:
        return self.users.get(telegram_id)
    
    def get_user_by_id(self, user_id: UUID) -> Optional[InMemoryUser]:
        for user in self.users.values():
            if user.id == user_id:
                return user
        return None
    
    # =========== TEAMS ===========
    
    def _create_default_team(self, user_id: UUID, username: str) -> Team:
        """Создать команду по умолчанию с 16 игроками"""
        players = []
        number = 1
        players.append(Player(name="Вратарь", position=Position.GOALKEEPER, number=number)); number += 1
        for i in range(5):
            players.append(Player(name=f"Защитник {i+1}", position=Position.DEFENDER, number=number)); number += 1
        for i in range(6):
            players.append(Player(name=f"Полузащитник {i+1}", position=Position.MIDFIELDER, number=number)); number += 1
        for i in range(4):
            players.append(Player(name=f"Нападающий {i+1}", position=Position.FORWARD, number=number)); number += 1
        
        team = Team(manager_id=user_id, name=f"Команда {username}", players=players)
        self.user_teams[user_id] = team
        self._bg_save(self._db_save_team(user_id, team))
        return team
    
    def get_user_team(self, user_id: UUID) -> Optional[Team]:
        return self.user_teams.get(user_id)
    
    # =========== MATCHES ===========
    
    def get_match(self, match_id: UUID) -> Optional[Match]:
        return self.matches.get(match_id)
    
    def get_user_active_match(self, user_id: UUID) -> Optional[Match]:
        for match in self.matches.values():
            if match.status in [MatchStatus.WAITING_FOR_OPPONENT, MatchStatus.SETTING_LINEUP, 
                               MatchStatus.IN_PROGRESS, MatchStatus.EXTRA_TIME, MatchStatus.PENALTIES]:
                if match.is_participant(user_id):
                    return match
        return None
    
    def get_user_last_match(self, user_id: UUID) -> Optional[Match]:
        last_match = None
        for match in self.matches.values():
            if match.is_participant(user_id):
                if last_match is None or (match.created_at and (last_match.created_at is None or match.created_at > last_match.created_at)):
                    last_match = match
        return last_match

    def get_user_finished_matches(self, user_id: UUID, limit: int = 5) -> List[Match]:
        """Получить последние завершённые матчи пользователя.

        Сортируются по finished_at (или created_at если finished_at не заполнен)
        в порядке убывания.
        """
        matches = []
        for match in self.matches.values():
            if (
                match.status == MatchStatus.FINISHED
                and match.is_participant(user_id)
            ):
                matches.append(match)

        def _key(m: Match):
            return m.finished_at or m.created_at or datetime.min.replace(tzinfo=timezone.utc)

        matches.sort(key=_key, reverse=True)
        return matches[:limit]
    
    def save_match(self, match: Match) -> None:
        """Сохранить матч в память + фоновое сохранение в БД"""
        self.matches[match.id] = match
        self._bg_save(self._db_save_match(match))
    
    def add_waiting_match(self, match_id: UUID) -> None:
        if match_id not in self.waiting_matches:
            self.waiting_matches.append(match_id)
    
    def remove_waiting_match(self, match_id: UUID) -> None:
        if match_id in self.waiting_matches:
            self.waiting_matches.remove(match_id)
    
    def find_waiting_match(self, exclude_user_id: UUID) -> Optional[Match]:
        for match_id in self.waiting_matches:
            match = self.matches.get(match_id)
            if match and match.manager1_id != exclude_user_id:
                return match
        return None
    
    # =========== DB BACKGROUND OPS ===========
    
    async def _db_create_user(self, user: InMemoryUser):
        """Создать пользователя в БД (фоновая задача)"""
        if not self._db_enabled:
            return
        try:
            async with self._db.session() as session:
                from src.infrastructure.db.models import UserModel
                from sqlalchemy import select
                # Проверяем что пользователя нет
                result = await session.execute(
                    select(UserModel).where(UserModel.telegram_id == user.telegram_id)
                )
                if result.scalar_one_or_none():
                    user._db_synced = True
                    return
                model = UserModel(
                    id=user.id,
                    username=user.username,
                    telegram_id=user.telegram_id,
                    plan="free",
                    rating=user.rating,
                    matches_played=user.matches_played,
                    matches_won=user.matches_won,
                    is_banned=False,
                )
                session.add(model)
            user._db_synced = True
            logger.debug(f"[DB] User created: {user.telegram_id}")
        except Exception as e:
            logger.error(f"[DB] Failed to create user: {e}")
    
    async def _db_save_team(self, user_id: UUID, team: Team):
        """Сохранить команду в БД"""
        if not self._db_enabled:
            return
        try:
            async with self._db.session() as session:
                from src.infrastructure.db.models import TeamModel
                from sqlalchemy import select
                
                result = await session.execute(
                    select(TeamModel).where(TeamModel.user_id == user_id)
                )
                existing = result.scalar_one_or_none()
                
                players_json = [p.model_dump(mode='json') for p in team.players]
                
                if existing:
                    existing.name = team.name
                    existing.players = players_json
                else:
                    model = TeamModel(
                        id=team.id,
                        user_id=user_id,
                        name=team.name,
                        players=players_json
                    )
                    session.add(model)
            logger.debug(f"[DB] Team saved for user {user_id}")
        except Exception as e:
            logger.error(f"[DB] Failed to save team: {e}")
    
    async def _db_save_match(self, match: Match):
        """Сохранить/обновить матч в БД"""
        if not self._db_enabled:
            return
        try:
            async with self._db.session() as session:
                from src.infrastructure.db.models import MatchModel
                from sqlalchemy import select
                
                result = await session.execute(
                    select(MatchModel).where(MatchModel.id == match.id)
                )
                existing = result.scalar_one_or_none()
                
                match_data = {
                    "match_type": match.match_type.value,
                    "status": match.status.value,
                    "phase": match.phase.value,
                    "manager1_id": match.manager1_id,
                    "manager2_id": match.manager2_id,
                    "team1_snapshot": match.team1.model_dump(mode='json') if match.team1 else None,
                    "team2_snapshot": match.team2.model_dump(mode='json') if match.team2 else None,
                    "current_turn": match.current_turn.model_dump(mode='json') if match.current_turn else None,
                    "total_turns_main": match.total_turns_main,
                    "total_turns_extra": match.total_turns_extra,
                    "used_players_main_m1": match.used_players_main_m1,
                    "used_players_main_m2": match.used_players_main_m2,
                    "used_players_extra_m1": match.used_players_extra_m1,
                    "used_players_extra_m2": match.used_players_extra_m2,
                    "whistle_deck": [c.model_dump(mode='json') for c in match.whistle_deck],
                    "whistle_cards_drawn": [c.model_dump(mode='json') for c in match.whistle_cards_drawn],
                    "bets": [b.model_dump(mode='json') for b in match.bets],
                    "score_manager1": match.score.manager1_goals,
                    "score_manager2": match.score.manager2_goals,
                    "winner_id": match.result.winner_id if match.result else None,
                    "loser_id": match.result.loser_id if match.result else None,
                    "decided_by": match.result.decided_by.value if match.result else None,
                    "decided_by_lottery": match.result.decided_by_lottery if match.result else False,
                    "penalty_results": [p.model_dump(mode='json') for p in match.penalty_results],
                    "penalty_score_m1": match.penalty_score_m1,
                    "penalty_score_m2": match.penalty_score_m2,
                    "started_at": match.started_at,
                    "finished_at": match.finished_at,
                }
                
                if existing:
                    for key, value in match_data.items():
                        setattr(existing, key, value)
                else:
                    model = MatchModel(id=match.id, **match_data, platform="telegram")
                    session.add(model)
            
            logger.debug(f"[DB] Match saved: {match.id} ({match.status.value})")
        except Exception as e:
            logger.error(f"[DB] Failed to save match {match.id}: {e}")
    
    async def _db_update_user(self, user: InMemoryUser):
        """Обновить пользователя в БД"""
        if not self._db_enabled:
            return
        try:
            async with self._db.session() as session:
                from src.infrastructure.db.models import UserModel
                from sqlalchemy import update
                await session.execute(
                    update(UserModel)
                    .where(UserModel.id == user.id)
                    .values(
                        rating=user.rating,
                        matches_played=user.matches_played,
                        matches_won=user.matches_won,
                        last_active_at=datetime.now(timezone.utc)
                    )
                )
            logger.debug(f"[DB] User updated: {user.telegram_id}")
        except Exception as e:
            logger.error(f"[DB] Failed to update user: {e}")
    
    def update_user_stats(self, user: InMemoryUser):
        """Обновить статистику пользователя в БД (вызывается при завершении матча)"""
        self._bg_save(self._db_update_user(user))
    
    async def close(self):
        """Закрыть подключение к БД"""
        if self._db:
            await self._db.close()


# Глобальный экземпляр
_storage: Optional[HybridStorage] = None


def get_storage() -> HybridStorage:
    """Получить глобальное хранилище"""
    global _storage
    if _storage is None:
        _storage = HybridStorage()
    return _storage
