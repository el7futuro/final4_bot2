# src/infrastructure/db/models.py
"""SQLAlchemy модели"""

from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean, Text,
    DateTime, ForeignKey, Date
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class UserModel(Base):
    """Модель пользователя в БД"""
    __tablename__ = 'users'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(Text, nullable=False)
    
    # ID на платформах
    telegram_id = Column(BigInteger, unique=True, nullable=True, index=True)
    vk_id = Column(BigInteger, unique=True, nullable=True, index=True)
    discord_id = Column(BigInteger, unique=True, nullable=True, index=True)
    
    # Подписка
    plan = Column(Text, nullable=False, default='free')
    plan_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Статистика
    matches_played = Column(Integer, nullable=False, default=0)
    matches_won = Column(Integer, nullable=False, default=0)
    matches_lost = Column(Integer, nullable=False, default=0)
    matches_draw = Column(Integer, nullable=False, default=0)
    tournaments_won = Column(Integer, nullable=False, default=0)
    goals_scored = Column(Integer, nullable=False, default=0)
    goals_conceded = Column(Integer, nullable=False, default=0)
    win_streak = Column(Integer, nullable=False, default=0)
    best_win_streak = Column(Integer, nullable=False, default=0)
    
    # Рейтинг
    rating = Column(Integer, nullable=False, default=1000)
    
    # Лимиты
    matches_today = Column(Integer, nullable=False, default=0)
    last_match_date = Column(Date, nullable=True)
    
    # Метаданные
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_banned = Column(Boolean, nullable=False, default=False)
    ban_reason = Column(Text, nullable=True)
    
    # Связи
    teams = relationship('TeamModel', back_populates='user', cascade='all, delete-orphan')


class TeamModel(Base):
    """Модель команды в БД"""
    __tablename__ = 'teams'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(Text, nullable=False)
    
    # Состав команды (JSONB)
    players = Column(JSONB, nullable=False, default=list)
    formation = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Связи
    user = relationship('UserModel', back_populates='teams')


class MatchModel(Base):
    """Модель матча в БД"""
    __tablename__ = 'matches'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    match_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default='waiting_for_opponent', index=True)
    phase = Column(Text, nullable=False, default='main_time')
    
    # Участники
    manager1_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    manager2_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, index=True)
    
    # Снимок команд на момент матча
    team1_snapshot = Column(JSONB, nullable=True)
    team2_snapshot = Column(JSONB, nullable=True)
    
    # Ход игры
    current_turn = Column(JSONB, nullable=True)
    total_turns_main = Column(Integer, nullable=False, default=0)
    total_turns_extra = Column(Integer, nullable=False, default=0)
    
    # Использованные игроки (JSONB массивы строковых UUID)
    used_players_main_m1 = Column(JSONB, nullable=False, default=list)
    used_players_main_m2 = Column(JSONB, nullable=False, default=list)
    used_players_extra_m1 = Column(JSONB, nullable=False, default=list)
    used_players_extra_m2 = Column(JSONB, nullable=False, default=list)
    
    # Карточки
    whistle_deck = Column(JSONB, nullable=False, default=list)
    whistle_cards_drawn = Column(JSONB, nullable=False, default=list)
    
    # Ставки (JSONB для простоты)
    bets = Column(JSONB, nullable=False, default=list)
    
    # Счёт
    score_manager1 = Column(Integer, nullable=False, default=0)
    score_manager2 = Column(Integer, nullable=False, default=0)
    
    # Результат
    winner_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    loser_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    decided_by = Column(Text, nullable=True)
    decided_by_lottery = Column(Boolean, nullable=False, default=False)
    
    # Серия пенальти
    penalty_results = Column(JSONB, nullable=False, default=list)
    penalty_score_m1 = Column(Integer, nullable=False, default=0)
    penalty_score_m2 = Column(Integer, nullable=False, default=0)
    
    # Платформа
    platform = Column(Text, nullable=False, default='telegram')
    
    # Метаданные
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    
    # Связи
    manager1 = relationship('UserModel', foreign_keys=[manager1_id])
    manager2 = relationship('UserModel', foreign_keys=[manager2_id])
