# src/admin/models.py
"""SQLAlchemy модели для Flask-Admin (синхронные, та же БД)"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, Text, DateTime, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(Text, nullable=False)
    telegram_id = Column(BigInteger, unique=True, nullable=True)
    vk_id = Column(BigInteger, unique=True, nullable=True)
    discord_id = Column(BigInteger, unique=True, nullable=True)
    plan = Column(Text, nullable=False, default='free')
    plan_expires_at = Column(DateTime(timezone=True), nullable=True)
    matches_played = Column(Integer, nullable=False, default=0)
    matches_won = Column(Integer, nullable=False, default=0)
    matches_lost = Column(Integer, nullable=False, default=0)
    matches_draw = Column(Integer, nullable=False, default=0)
    tournaments_won = Column(Integer, nullable=False, default=0)
    goals_scored = Column(Integer, nullable=False, default=0)
    goals_conceded = Column(Integer, nullable=False, default=0)
    win_streak = Column(Integer, nullable=False, default=0)
    best_win_streak = Column(Integer, nullable=False, default=0)
    rating = Column(Integer, nullable=False, default=1000)
    matches_today = Column(Integer, nullable=False, default=0)
    last_match_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_banned = Column(Boolean, nullable=False, default=False)
    ban_reason = Column(Text, nullable=True)
    
    def __repr__(self):
        return f'{self.username} ({self.telegram_id})'


class Team(db.Model):
    __tablename__ = 'teams'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = Column(Text, nullable=False)
    players = Column(JSONB, nullable=False, default=list)
    formation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    user = db.relationship('User', backref='teams')
    
    def __repr__(self):
        return self.name


class Match(db.Model):
    __tablename__ = 'matches'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default='waiting_for_opponent')
    phase = Column(Text, nullable=False, default='main_time')
    manager1_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    manager2_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    team1_snapshot = Column(JSONB, nullable=True)
    team2_snapshot = Column(JSONB, nullable=True)
    current_turn = Column(JSONB, nullable=True)
    total_turns_main = Column(Integer, nullable=False, default=0)
    total_turns_extra = Column(Integer, nullable=False, default=0)
    used_players_main_m1 = Column(JSONB, nullable=False, default=list)
    used_players_main_m2 = Column(JSONB, nullable=False, default=list)
    used_players_extra_m1 = Column(JSONB, nullable=False, default=list)
    used_players_extra_m2 = Column(JSONB, nullable=False, default=list)
    whistle_deck = Column(JSONB, nullable=False, default=list)
    whistle_cards_drawn = Column(JSONB, nullable=False, default=list)
    bets = Column(JSONB, nullable=False, default=list)
    score_manager1 = Column(Integer, nullable=False, default=0)
    score_manager2 = Column(Integer, nullable=False, default=0)
    winner_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    loser_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    decided_by = Column(Text, nullable=True)
    decided_by_lottery = Column(Boolean, nullable=False, default=False)
    penalty_results = Column(JSONB, nullable=False, default=list)
    penalty_score_m1 = Column(Integer, nullable=False, default=0)
    penalty_score_m2 = Column(Integer, nullable=False, default=0)
    platform = Column(Text, nullable=False, default='telegram')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    
    manager1 = db.relationship('User', foreign_keys=[manager1_id], backref='matches_as_m1')
    manager2 = db.relationship('User', foreign_keys=[manager2_id], backref='matches_as_m2')
    
    def __repr__(self):
        return f'Match {str(self.id)[:8]} ({self.status})'


class Tournament(db.Model):
    """Турниры (CRUD для будущего)"""
    __tablename__ = 'tournaments'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default='draft')  # draft, registration, in_progress, finished
    max_participants = Column(Integer, nullable=False, default=16)
    entry_fee = Column(Integer, nullable=False, default=0)  # в внутренней валюте
    prize_pool = Column(Integer, nullable=False, default=0)
    format = Column(Text, nullable=False, default='single_elimination')
    participants = Column(JSONB, nullable=False, default=list)  # [user_id, ...]
    bracket = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    starts_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f'{self.name} ({self.status})'


class Transaction(db.Model):
    """Монетизация / транзакции"""
    __tablename__ = 'transactions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    type = Column(Text, nullable=False)  # purchase, reward, entry_fee, prize, refund
    amount = Column(Integer, nullable=False, default=0)
    currency = Column(Text, nullable=False, default='coins')
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    user = db.relationship('User', backref='transactions')
    
    def __repr__(self):
        return f'{self.type}: {self.amount} ({self.user_id})'
