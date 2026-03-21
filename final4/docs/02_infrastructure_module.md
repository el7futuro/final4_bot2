# Модуль: Infrastructure (Инфраструктурный слой)

## Обзор

Инфраструктурный слой содержит реализации репозиториев, работу с БД (PostgreSQL), кэш (Redis) и шину событий.

---

## 1. База данных PostgreSQL

### 1.1 SQL Schema

```sql
-- migrations/001_initial_schema.sql

-- Расширения
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- ТАБЛИЦА: users (Пользователи)
-- ============================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username TEXT NOT NULL,
    
    -- Идентификаторы платформ
    telegram_id BIGINT UNIQUE,
    vk_id BIGINT UNIQUE,
    discord_id BIGINT UNIQUE,
    
    -- Подписка
    plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'premium', 'pro')),
    plan_expires_at TIMESTAMPTZ,
    
    -- Статистика
    matches_played INTEGER NOT NULL DEFAULT 0,
    matches_won INTEGER NOT NULL DEFAULT 0,
    matches_lost INTEGER NOT NULL DEFAULT 0,
    matches_draw INTEGER NOT NULL DEFAULT 0,
    tournaments_won INTEGER NOT NULL DEFAULT 0,
    goals_scored INTEGER NOT NULL DEFAULT 0,
    goals_conceded INTEGER NOT NULL DEFAULT 0,
    win_streak INTEGER NOT NULL DEFAULT 0,
    best_win_streak INTEGER NOT NULL DEFAULT 0,
    
    -- Рейтинг
    rating INTEGER NOT NULL DEFAULT 1000,
    
    -- Дневные лимиты
    matches_today INTEGER NOT NULL DEFAULT 0,
    last_match_date DATE,
    
    -- Метаданные
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_banned BOOLEAN NOT NULL DEFAULT FALSE,
    ban_reason TEXT,
    
    -- Constraints
    CONSTRAINT users_at_least_one_platform CHECK (
        telegram_id IS NOT NULL OR 
        vk_id IS NOT NULL OR 
        discord_id IS NOT NULL
    )
);

-- Индексы для users
CREATE INDEX idx_users_telegram_id ON users(telegram_id) WHERE telegram_id IS NOT NULL;
CREATE INDEX idx_users_vk_id ON users(vk_id) WHERE vk_id IS NOT NULL;
CREATE INDEX idx_users_discord_id ON users(discord_id) WHERE discord_id IS NOT NULL;
CREATE INDEX idx_users_rating ON users(rating DESC);
CREATE INDEX idx_users_last_active ON users(last_active_at DESC);


-- ============================================
-- ТАБЛИЦА: teams (Команды пользователей)
-- ============================================
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    
    -- Состав (JSONB для flexibility)
    players JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Текущая формация (может быть NULL если не выбрана)
    formation TEXT CHECK (formation IN (
        '1-5-3-2', '1-5-2-3', '1-4-4-2', '1-4-3-3',
        '1-3-5-2', '1-3-4-3', '1-3-3-4'
    )),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Индексы для teams
CREATE INDEX idx_teams_user_id ON teams(user_id);


-- ============================================
-- ТАБЛИЦА: matches (Матчи)
-- ============================================
CREATE TABLE matches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Тип и статус
    match_type TEXT NOT NULL CHECK (match_type IN ('random', 'vs_bot', 'tournament')),
    status TEXT NOT NULL DEFAULT 'waiting_for_opponent' CHECK (status IN (
        'waiting_for_opponent', 'setting_lineup', 'in_progress',
        'extra_time', 'penalties', 'finished', 'cancelled'
    )),
    phase TEXT NOT NULL DEFAULT 'main_time' CHECK (phase IN (
        'main_time', 'extra_time', 'penalties'
    )),
    
    -- Участники
    manager1_id UUID NOT NULL REFERENCES users(id),
    manager2_id UUID REFERENCES users(id),
    
    -- Команды (snapshot на момент матча)
    team1_snapshot JSONB,
    team2_snapshot JSONB,
    
    -- Ход игры
    current_turn JSONB,
    total_turns_main INTEGER NOT NULL DEFAULT 0,
    total_turns_extra INTEGER NOT NULL DEFAULT 0,
    
    -- Колода карточек
    whistle_deck JSONB NOT NULL DEFAULT '[]'::jsonb,
    whistle_cards_drawn JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Счёт
    score_manager1 INTEGER NOT NULL DEFAULT 0,
    score_manager2 INTEGER NOT NULL DEFAULT 0,
    
    -- Результат
    winner_id UUID REFERENCES users(id),
    loser_id UUID REFERENCES users(id),
    decided_by TEXT CHECK (decided_by IN ('main_time', 'extra_time', 'penalties')),
    decided_by_lottery BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Платформа
    platform TEXT NOT NULL CHECK (platform IN ('telegram', 'vk', 'discord', 'api')),
    
    -- Метаданные
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

-- Индексы для matches
CREATE INDEX idx_matches_manager1 ON matches(manager1_id);
CREATE INDEX idx_matches_manager2 ON matches(manager2_id) WHERE manager2_id IS NOT NULL;
CREATE INDEX idx_matches_status ON matches(status);
CREATE INDEX idx_matches_platform_status ON matches(platform, status);
CREATE INDEX idx_matches_created_at ON matches(created_at DESC);
CREATE INDEX idx_matches_winner ON matches(winner_id) WHERE winner_id IS NOT NULL;


-- ============================================
-- ТАБЛИЦА: bets (Ставки)
-- ============================================
CREATE TABLE bets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    match_id UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    manager_id UUID NOT NULL REFERENCES users(id),
    player_id UUID NOT NULL,  -- ID игрока из team snapshot
    
    turn_number INTEGER NOT NULL,
    
    -- Тип и значение ставки
    bet_type TEXT NOT NULL CHECK (bet_type IN ('even_odd', 'high_low', 'exact_number')),
    even_odd_choice TEXT CHECK (even_odd_choice IN ('even', 'odd')),
    high_low_choice TEXT CHECK (high_low_choice IN ('low', 'high')),
    exact_number INTEGER CHECK (exact_number BETWEEN 1 AND 6),
    
    -- Результат
    dice_roll INTEGER CHECK (dice_roll BETWEEN 1 AND 6),
    outcome TEXT NOT NULL DEFAULT 'pending' CHECK (outcome IN ('pending', 'won', 'lost')),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT bets_value_matches_type CHECK (
        (bet_type = 'even_odd' AND even_odd_choice IS NOT NULL) OR
        (bet_type = 'high_low' AND high_low_choice IS NOT NULL) OR
        (bet_type = 'exact_number' AND exact_number IS NOT NULL)
    )
);

-- Индексы для bets
CREATE INDEX idx_bets_match_id ON bets(match_id);
CREATE INDEX idx_bets_manager_id ON bets(manager_id);
CREATE INDEX idx_bets_match_turn ON bets(match_id, turn_number);


-- ============================================
-- ТАБЛИЦА: tournaments (Турниры)
-- ============================================
CREATE TABLE tournaments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    
    -- Настройки
    max_participants INTEGER NOT NULL DEFAULT 8,
    entry_fee INTEGER NOT NULL DEFAULT 0,  -- В игровой валюте
    prize_pool INTEGER NOT NULL DEFAULT 0,
    
    -- Статус
    status TEXT NOT NULL DEFAULT 'registration' CHECK (status IN (
        'registration', 'in_progress', 'finished', 'cancelled'
    )),
    
    -- Участники
    participants JSONB NOT NULL DEFAULT '[]'::jsonb,  -- Array of user_ids
    bracket JSONB,  -- Сетка плей-офф
    
    -- Победитель
    winner_id UUID REFERENCES users(id),
    
    -- Метаданные
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES users(id)
);

-- Индексы для tournaments
CREATE INDEX idx_tournaments_status ON tournaments(status);
CREATE INDEX idx_tournaments_winner ON tournaments(winner_id) WHERE winner_id IS NOT NULL;


-- ============================================
-- ТАБЛИЦА: tournament_matches (Связь турнир-матч)
-- ============================================
CREATE TABLE tournament_matches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tournament_id UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    match_id UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,  -- 1 = финал, 2 = полуфинал, и т.д.
    bracket_position INTEGER NOT NULL,
    
    UNIQUE(tournament_id, match_id)
);

-- Индексы
CREATE INDEX idx_tournament_matches_tournament ON tournament_matches(tournament_id);


-- ============================================
-- ТАБЛИЦА: match_events (Лог событий матча)
-- ============================================
CREATE TABLE match_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    match_id UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    
    event_type TEXT NOT NULL,  -- 'bet_placed', 'dice_rolled', 'card_drawn', etc.
    event_data JSONB NOT NULL,
    
    turn_number INTEGER NOT NULL,
    manager_id UUID REFERENCES users(id),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Индексы
CREATE INDEX idx_match_events_match ON match_events(match_id);
CREATE INDEX idx_match_events_type ON match_events(event_type);


-- ============================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================

-- Включаем RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE bets ENABLE ROW LEVEL SECURITY;

-- Политики для users
CREATE POLICY users_select_own ON users
    FOR SELECT
    USING (id = current_setting('app.current_user_id')::uuid);

CREATE POLICY users_update_own ON users
    FOR UPDATE
    USING (id = current_setting('app.current_user_id')::uuid);

-- Политики для teams
CREATE POLICY teams_select_own ON teams
    FOR SELECT
    USING (user_id = current_setting('app.current_user_id')::uuid);

CREATE POLICY teams_insert_own ON teams
    FOR INSERT
    WITH CHECK (user_id = current_setting('app.current_user_id')::uuid);

CREATE POLICY teams_update_own ON teams
    FOR UPDATE
    USING (user_id = current_setting('app.current_user_id')::uuid);

-- Политики для matches (видны участникам)
CREATE POLICY matches_select_participant ON matches
    FOR SELECT
    USING (
        manager1_id = current_setting('app.current_user_id')::uuid OR
        manager2_id = current_setting('app.current_user_id')::uuid
    );

-- Политики для bets (видны владельцу)
CREATE POLICY bets_select_own ON bets
    FOR SELECT
    USING (manager_id = current_setting('app.current_user_id')::uuid);

-- Сервисная роль для обхода RLS
CREATE ROLE final4_service;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE teams FORCE ROW LEVEL SECURITY;
ALTER TABLE matches FORCE ROW LEVEL SECURITY;
ALTER TABLE bets FORCE ROW LEVEL SECURITY;

-- Сервисная роль может всё
GRANT ALL ON ALL TABLES IN SCHEMA public TO final4_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO final4_service;


-- ============================================
-- ФУНКЦИИ И ТРИГГЕРЫ
-- ============================================

-- Функция обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для teams
CREATE TRIGGER teams_updated_at
    BEFORE UPDATE ON teams
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Функция обновления статистики пользователя после матча
CREATE OR REPLACE FUNCTION update_user_stats_after_match()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'finished' AND OLD.status != 'finished' THEN
        -- Обновляем победителя
        IF NEW.winner_id IS NOT NULL THEN
            UPDATE users SET
                matches_played = matches_played + 1,
                matches_won = matches_won + 1,
                win_streak = win_streak + 1,
                best_win_streak = GREATEST(best_win_streak, win_streak + 1),
                last_active_at = NOW()
            WHERE id = NEW.winner_id;
            
            -- Обновляем проигравшего
            UPDATE users SET
                matches_played = matches_played + 1,
                matches_lost = matches_lost + 1,
                win_streak = 0,
                last_active_at = NOW()
            WHERE id = NEW.loser_id;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER matches_update_stats
    AFTER UPDATE ON matches
    FOR EACH ROW
    EXECUTE FUNCTION update_user_stats_after_match();

-- Функция сброса дневных лимитов (вызывать через cron)
CREATE OR REPLACE FUNCTION reset_daily_limits()
RETURNS void AS $$
BEGIN
    UPDATE users
    SET matches_today = 0
    WHERE last_match_date < CURRENT_DATE;
END;
$$ LANGUAGE plpgsql;
```

### 1.2 Структура JSONB полей

#### players (в таблице teams)

```json
[
    {
        "id": "uuid",
        "name": "Иван Петров",
        "position": "goalkeeper",
        "number": 1,
        "stats": {
            "saves": 0,
            "passes": 0,
            "goals": 0
        },
        "is_on_field": false,
        "is_available": true,
        "yellow_cards": 0
    }
]
```

#### current_turn (в таблице matches)

```json
{
    "turn_number": 5,
    "current_manager_id": "uuid",
    "player_being_bet_on": "uuid",
    "bets_placed": ["uuid1", "uuid2"],
    "dice_rolled": false,
    "dice_value": null,
    "card_drawn": false,
    "card_id": null,
    "card_applied": false,
    "waiting_for_penalty_roll": false
}
```

#### whistle_deck / whistle_cards_drawn

```json
[
    {
        "id": "uuid",
        "card_type": "goal",
        "is_used": false,
        "applied_to_player_id": null,
        "applied_by_manager_id": null,
        "turn_applied": null,
        "cancelled_card_id": null
    }
]
```

---

## 2. SQLAlchemy Models

```python
# src/infrastructure/db/models.py

from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean, Text,
    DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class UserModel(Base):
    __tablename__ = 'users'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(Text, nullable=False)
    
    # Platform IDs
    telegram_id = Column(BigInteger, unique=True, nullable=True)
    vk_id = Column(BigInteger, unique=True, nullable=True)
    discord_id = Column(BigInteger, unique=True, nullable=True)
    
    # Subscription
    plan = Column(Text, nullable=False, default='free')
    plan_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Stats
    matches_played = Column(Integer, nullable=False, default=0)
    matches_won = Column(Integer, nullable=False, default=0)
    matches_lost = Column(Integer, nullable=False, default=0)
    matches_draw = Column(Integer, nullable=False, default=0)
    tournaments_won = Column(Integer, nullable=False, default=0)
    goals_scored = Column(Integer, nullable=False, default=0)
    goals_conceded = Column(Integer, nullable=False, default=0)
    win_streak = Column(Integer, nullable=False, default=0)
    best_win_streak = Column(Integer, nullable=False, default=0)
    
    # Rating
    rating = Column(Integer, nullable=False, default=1000)
    
    # Daily limits
    matches_today = Column(Integer, nullable=False, default=0)
    last_match_date = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_banned = Column(Boolean, nullable=False, default=False)
    ban_reason = Column(Text, nullable=True)
    
    # Relationships
    teams = relationship('TeamModel', back_populates='user', cascade='all, delete-orphan')
    
    __table_args__ = (
        CheckConstraint(
            'telegram_id IS NOT NULL OR vk_id IS NOT NULL OR discord_id IS NOT NULL',
            name='users_at_least_one_platform'
        ),
        CheckConstraint("plan IN ('free', 'premium', 'pro')", name='users_plan_check'),
    )


class TeamModel(Base):
    __tablename__ = 'teams'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = Column(Text, nullable=False)
    
    players = Column(JSONB, nullable=False, default=list)
    formation = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship('UserModel', back_populates='teams')
    
    __table_args__ = (
        Index('idx_teams_user_id', 'user_id'),
        CheckConstraint(
            "formation IN ('1-5-3-2', '1-5-2-3', '1-4-4-2', '1-4-3-3', '1-3-5-2', '1-3-4-3', '1-3-3-4')",
            name='teams_formation_check'
        ),
    )


class MatchModel(Base):
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
    
    whistle_deck = Column(JSONB, nullable=False, default=list)
    whistle_cards_drawn = Column(JSONB, nullable=False, default=list)
    
    score_manager1 = Column(Integer, nullable=False, default=0)
    score_manager2 = Column(Integer, nullable=False, default=0)
    
    winner_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    loser_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    decided_by = Column(Text, nullable=True)
    decided_by_lottery = Column(Boolean, nullable=False, default=False)
    
    platform = Column(Text, nullable=False)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    manager1 = relationship('UserModel', foreign_keys=[manager1_id])
    manager2 = relationship('UserModel', foreign_keys=[manager2_id])
    winner = relationship('UserModel', foreign_keys=[winner_id])
    bets = relationship('BetModel', back_populates='match', cascade='all, delete-orphan')
    events = relationship('MatchEventModel', back_populates='match', cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_matches_manager1', 'manager1_id'),
        Index('idx_matches_status', 'status'),
        Index('idx_matches_platform_status', 'platform', 'status'),
        CheckConstraint("match_type IN ('random', 'vs_bot', 'tournament')", name='matches_type_check'),
        CheckConstraint(
            "status IN ('waiting_for_opponent', 'setting_lineup', 'in_progress', 'extra_time', 'penalties', 'finished', 'cancelled')",
            name='matches_status_check'
        ),
        CheckConstraint("phase IN ('main_time', 'extra_time', 'penalties')", name='matches_phase_check'),
        CheckConstraint("platform IN ('telegram', 'vk', 'discord', 'api')", name='matches_platform_check'),
    )


class BetModel(Base):
    __tablename__ = 'bets'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey('matches.id', ondelete='CASCADE'), nullable=False)
    manager_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    player_id = Column(UUID(as_uuid=True), nullable=False)
    
    turn_number = Column(Integer, nullable=False)
    
    bet_type = Column(Text, nullable=False)
    even_odd_choice = Column(Text, nullable=True)
    high_low_choice = Column(Text, nullable=True)
    exact_number = Column(Integer, nullable=True)
    
    dice_roll = Column(Integer, nullable=True)
    outcome = Column(Text, nullable=False, default='pending')
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationships
    match = relationship('MatchModel', back_populates='bets')
    manager = relationship('UserModel')
    
    __table_args__ = (
        Index('idx_bets_match_id', 'match_id'),
        Index('idx_bets_manager_id', 'manager_id'),
        Index('idx_bets_match_turn', 'match_id', 'turn_number'),
        CheckConstraint("bet_type IN ('even_odd', 'high_low', 'exact_number')", name='bets_type_check'),
        CheckConstraint("outcome IN ('pending', 'won', 'lost')", name='bets_outcome_check'),
        CheckConstraint('exact_number BETWEEN 1 AND 6', name='bets_exact_number_range'),
        CheckConstraint('dice_roll BETWEEN 1 AND 6', name='bets_dice_roll_range'),
    )


class MatchEventModel(Base):
    __tablename__ = 'match_events'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey('matches.id', ondelete='CASCADE'), nullable=False)
    
    event_type = Column(Text, nullable=False)
    event_data = Column(JSONB, nullable=False)
    
    turn_number = Column(Integer, nullable=False)
    manager_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationships
    match = relationship('MatchModel', back_populates='events')
    
    __table_args__ = (
        Index('idx_match_events_match', 'match_id'),
        Index('idx_match_events_type', 'event_type'),
    )


class TournamentModel(Base):
    __tablename__ = 'tournaments'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    
    max_participants = Column(Integer, nullable=False, default=8)
    entry_fee = Column(Integer, nullable=False, default=0)
    prize_pool = Column(Integer, nullable=False, default=0)
    
    status = Column(Text, nullable=False, default='registration')
    
    participants = Column(JSONB, nullable=False, default=list)
    bracket = Column(JSONB, nullable=True)
    
    winner_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    
    __table_args__ = (
        Index('idx_tournaments_status', 'status'),
        CheckConstraint(
            "status IN ('registration', 'in_progress', 'finished', 'cancelled')",
            name='tournaments_status_check'
        ),
    )
```

---

## 3. Repository Implementations

```python
# src/infrastructure/repositories/user_repository.py

from typing import Optional, List
from uuid import UUID
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.user import User, UserPlan, PlatformIds, UserStats, DailyLimits
from src.core.interfaces.repositories import IUserRepository
from ..db.models import UserModel

class UserRepository(IUserRepository):
    """Реализация репозитория пользователей"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.telegram_id == telegram_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def get_by_vk_id(self, vk_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.vk_id == vk_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def get_by_discord_id(self, discord_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.discord_id == discord_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def create(self, user: User) -> User:
        model = self._to_model(user)
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)
    
    async def update(self, user: User) -> User:
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user.id)
        )
        model = result.scalar_one()
        
        # Update fields
        model.username = user.username
        model.telegram_id = user.platform_ids.telegram_id
        model.vk_id = user.platform_ids.vk_id
        model.discord_id = user.platform_ids.discord_id
        model.plan = user.plan.value
        model.plan_expires_at = user.plan_expires_at
        model.matches_played = user.stats.matches_played
        model.matches_won = user.stats.matches_won
        model.matches_lost = user.stats.matches_lost
        model.matches_draw = user.stats.matches_draw
        model.tournaments_won = user.stats.tournaments_won
        model.goals_scored = user.stats.goals_scored
        model.goals_conceded = user.stats.goals_conceded
        model.win_streak = user.stats.win_streak
        model.best_win_streak = user.stats.best_win_streak
        model.rating = user.rating
        model.matches_today = user.daily_limits.matches_today
        model.last_match_date = user.daily_limits.last_match_date
        model.last_active_at = user.last_active_at
        model.is_banned = user.is_banned
        model.ban_reason = user.ban_reason
        
        await self.session.flush()
        return self._to_domain(model)
    
    async def get_leaderboard(self, limit: int = 100) -> List[User]:
        result = await self.session.execute(
            select(UserModel)
            .where(UserModel.is_banned == False)
            .order_by(desc(UserModel.rating))
            .limit(limit)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]
    
    def _to_domain(self, model: UserModel) -> User:
        return User(
            id=model.id,
            username=model.username,
            platform_ids=PlatformIds(
                telegram_id=model.telegram_id,
                vk_id=model.vk_id,
                discord_id=model.discord_id
            ),
            plan=UserPlan(model.plan),
            plan_expires_at=model.plan_expires_at,
            stats=UserStats(
                matches_played=model.matches_played,
                matches_won=model.matches_won,
                matches_lost=model.matches_lost,
                matches_draw=model.matches_draw,
                tournaments_won=model.tournaments_won,
                goals_scored=model.goals_scored,
                goals_conceded=model.goals_conceded,
                win_streak=model.win_streak,
                best_win_streak=model.best_win_streak
            ),
            daily_limits=DailyLimits(
                matches_today=model.matches_today,
                last_match_date=model.last_match_date
            ),
            rating=model.rating,
            created_at=model.created_at,
            last_active_at=model.last_active_at,
            is_banned=model.is_banned,
            ban_reason=model.ban_reason
        )
    
    def _to_model(self, user: User) -> UserModel:
        return UserModel(
            id=user.id,
            username=user.username,
            telegram_id=user.platform_ids.telegram_id,
            vk_id=user.platform_ids.vk_id,
            discord_id=user.platform_ids.discord_id,
            plan=user.plan.value,
            plan_expires_at=user.plan_expires_at,
            matches_played=user.stats.matches_played,
            matches_won=user.stats.matches_won,
            matches_lost=user.stats.matches_lost,
            matches_draw=user.stats.matches_draw,
            tournaments_won=user.stats.tournaments_won,
            goals_scored=user.stats.goals_scored,
            goals_conceded=user.stats.goals_conceded,
            win_streak=user.stats.win_streak,
            best_win_streak=user.stats.best_win_streak,
            rating=user.rating,
            matches_today=user.daily_limits.matches_today,
            last_match_date=user.daily_limits.last_match_date,
            created_at=user.created_at,
            last_active_at=user.last_active_at,
            is_banned=user.is_banned,
            ban_reason=user.ban_reason
        )
```

```python
# src/infrastructure/repositories/match_repository.py

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.match import Match, MatchStatus, MatchType, MatchPhase, TurnState, MatchScore, MatchResult
from src.core.models.team import Team
from src.core.models.whistle_card import WhistleCard
from src.core.interfaces.repositories import IMatchRepository
from ..db.models import MatchModel

class MatchRepository(IMatchRepository):
    """Реализация репозитория матчей"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, match_id: UUID) -> Optional[Match]:
        result = await self.session.execute(
            select(MatchModel).where(MatchModel.id == match_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def create(self, match: Match) -> Match:
        model = self._to_model(match)
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)
    
    async def update(self, match: Match) -> Match:
        result = await self.session.execute(
            select(MatchModel).where(MatchModel.id == match.id)
        )
        model = result.scalar_one()
        
        # Update all fields
        model.status = match.status.value
        model.phase = match.phase.value
        model.manager2_id = match.manager2_id
        model.team1_snapshot = match.team1.model_dump() if match.team1 else None
        model.team2_snapshot = match.team2.model_dump() if match.team2 else None
        model.current_turn = match.current_turn.model_dump() if match.current_turn else None
        model.total_turns_main = match.total_turns_main
        model.total_turns_extra = match.total_turns_extra
        model.whistle_deck = [c.model_dump() for c in match.whistle_deck]
        model.whistle_cards_drawn = [c.model_dump() for c in match.whistle_cards_drawn]
        model.score_manager1 = match.score.manager1_goals
        model.score_manager2 = match.score.manager2_goals
        model.winner_id = match.result.winner_id if match.result else None
        model.loser_id = match.result.loser_id if match.result else None
        model.decided_by = match.result.decided_by.value if match.result else None
        model.decided_by_lottery = match.result.decided_by_lottery if match.result else False
        model.started_at = match.started_at
        model.finished_at = match.finished_at
        
        await self.session.flush()
        return self._to_domain(model)
    
    async def get_waiting_matches(self, platform: str) -> List[Match]:
        result = await self.session.execute(
            select(MatchModel)
            .where(
                and_(
                    MatchModel.platform == platform,
                    MatchModel.status == 'waiting_for_opponent',
                    MatchModel.match_type == 'random'
                )
            )
            .order_by(MatchModel.created_at)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]
    
    async def get_user_matches(
        self,
        user_id: UUID,
        status: Optional[MatchStatus] = None,
        limit: int = 10
    ) -> List[Match]:
        query = select(MatchModel).where(
            or_(
                MatchModel.manager1_id == user_id,
                MatchModel.manager2_id == user_id
            )
        )
        
        if status:
            query = query.where(MatchModel.status == status.value)
        
        query = query.order_by(desc(MatchModel.created_at)).limit(limit)
        
        result = await self.session.execute(query)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]
    
    async def get_user_match_history(
        self,
        user_id: UUID,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Match]:
        query = select(MatchModel).where(
            and_(
                or_(
                    MatchModel.manager1_id == user_id,
                    MatchModel.manager2_id == user_id
                ),
                MatchModel.status == 'finished'
            )
        )
        
        if from_date:
            query = query.where(MatchModel.finished_at >= from_date)
        if to_date:
            query = query.where(MatchModel.finished_at <= to_date)
        
        query = query.order_by(desc(MatchModel.finished_at)).limit(limit)
        
        result = await self.session.execute(query)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]
    
    def _to_domain(self, model: MatchModel) -> Match:
        return Match(
            id=model.id,
            match_type=MatchType(model.match_type),
            status=MatchStatus(model.status),
            phase=MatchPhase(model.phase),
            manager1_id=model.manager1_id,
            manager2_id=model.manager2_id,
            team1=Team(**model.team1_snapshot) if model.team1_snapshot else None,
            team2=Team(**model.team2_snapshot) if model.team2_snapshot else None,
            current_turn=TurnState(**model.current_turn) if model.current_turn else None,
            total_turns_main=model.total_turns_main,
            total_turns_extra=model.total_turns_extra,
            bets=[],  # Loaded separately
            whistle_cards_drawn=[WhistleCard(**c) for c in model.whistle_cards_drawn],
            whistle_deck=[WhistleCard(**c) for c in model.whistle_deck],
            score=MatchScore(
                manager1_goals=model.score_manager1,
                manager2_goals=model.score_manager2
            ),
            result=MatchResult(
                winner_id=model.winner_id,
                loser_id=model.loser_id,
                final_score=MatchScore(
                    manager1_goals=model.score_manager1,
                    manager2_goals=model.score_manager2
                ),
                decided_by=MatchPhase(model.decided_by) if model.decided_by else MatchPhase.MAIN_TIME,
                decided_by_lottery=model.decided_by_lottery
            ) if model.winner_id else None,
            created_at=model.created_at,
            started_at=model.started_at,
            finished_at=model.finished_at,
            platform=model.platform
        )
    
    def _to_model(self, match: Match) -> MatchModel:
        return MatchModel(
            id=match.id,
            match_type=match.match_type.value,
            status=match.status.value,
            phase=match.phase.value,
            manager1_id=match.manager1_id,
            manager2_id=match.manager2_id,
            team1_snapshot=match.team1.model_dump() if match.team1 else None,
            team2_snapshot=match.team2.model_dump() if match.team2 else None,
            current_turn=match.current_turn.model_dump() if match.current_turn else None,
            total_turns_main=match.total_turns_main,
            total_turns_extra=match.total_turns_extra,
            whistle_deck=[c.model_dump() for c in match.whistle_deck],
            whistle_cards_drawn=[c.model_dump() for c in match.whistle_cards_drawn],
            score_manager1=match.score.manager1_goals,
            score_manager2=match.score.manager2_goals,
            winner_id=match.result.winner_id if match.result else None,
            loser_id=match.result.loser_id if match.result else None,
            decided_by=match.result.decided_by.value if match.result else None,
            decided_by_lottery=match.result.decided_by_lottery if match.result else False,
            platform=match.platform,
            created_at=match.created_at,
            started_at=match.started_at,
            finished_at=match.finished_at
        )
```

---

## 4. Redis Cache

```python
# src/infrastructure/cache/redis_client.py

from typing import Optional, Any
import json
import redis.asyncio as redis
from pydantic import BaseModel

class RedisClient:
    """Клиент Redis"""
    
    def __init__(self, url: str):
        self.redis = redis.from_url(url, decode_responses=True)
    
    async def get(self, key: str) -> Optional[str]:
        return await self.redis.get(key)
    
    async def set(self, key: str, value: str, expire: int = None) -> None:
        if expire:
            await self.redis.setex(key, expire, value)
        else:
            await self.redis.set(key, value)
    
    async def delete(self, key: str) -> None:
        await self.redis.delete(key)
    
    async def get_json(self, key: str) -> Optional[dict]:
        data = await self.get(key)
        return json.loads(data) if data else None
    
    async def set_json(self, key: str, value: dict, expire: int = None) -> None:
        await self.set(key, json.dumps(value), expire)
    
    async def close(self) -> None:
        await self.redis.close()
```

```python
# src/infrastructure/cache/session_cache.py

from typing import Optional
from uuid import UUID

from .redis_client import RedisClient

class SessionCache:
    """Кэш сессий пользователей"""
    
    PREFIX = "session:"
    TTL = 3600 * 24  # 24 часа
    
    def __init__(self, redis: RedisClient):
        self.redis = redis
    
    async def get_active_match(self, user_id: UUID) -> Optional[UUID]:
        """Получить ID активного матча пользователя"""
        data = await self.redis.get_json(f"{self.PREFIX}{user_id}")
        if data and data.get('active_match_id'):
            return UUID(data['active_match_id'])
        return None
    
    async def set_active_match(self, user_id: UUID, match_id: UUID) -> None:
        """Установить активный матч"""
        await self.redis.set_json(
            f"{self.PREFIX}{user_id}",
            {'active_match_id': str(match_id)},
            self.TTL
        )
    
    async def clear_active_match(self, user_id: UUID) -> None:
        """Очистить активный матч"""
        await self.redis.delete(f"{self.PREFIX}{user_id}")
    
    async def get_user_state(self, user_id: UUID) -> Optional[dict]:
        """Получить состояние пользователя (для FSM)"""
        return await self.redis.get_json(f"{self.PREFIX}{user_id}:state")
    
    async def set_user_state(self, user_id: UUID, state: dict) -> None:
        """Установить состояние пользователя"""
        await self.redis.set_json(f"{self.PREFIX}{user_id}:state", state, self.TTL)
```

```python
# src/infrastructure/cache/rate_limiter.py

from .redis_client import RedisClient

class RateLimiter:
    """Rate limiting для API"""
    
    PREFIX = "ratelimit:"
    
    def __init__(self, redis: RedisClient):
        self.redis = redis
    
    async def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        """Проверить, разрешён ли запрос"""
        full_key = f"{self.PREFIX}{key}"
        
        current = await self.redis.redis.incr(full_key)
        
        if current == 1:
            await self.redis.redis.expire(full_key, window_seconds)
        
        return current <= max_requests
    
    async def get_remaining(
        self,
        key: str,
        max_requests: int
    ) -> int:
        """Получить оставшееся количество запросов"""
        full_key = f"{self.PREFIX}{key}"
        current = await self.redis.get(full_key)
        
        if current is None:
            return max_requests
        
        return max(0, max_requests - int(current))
```

---

## 5. Event Bus

```python
# src/infrastructure/events/event_bus.py

from typing import Callable, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
import asyncio

@dataclass
class Event:
    """Базовое событие"""
    event_type: str
    timestamp: datetime
    data: Dict[str, Any]

class MatchCreatedEvent(Event):
    def __init__(self, match_id: UUID, manager_id: UUID, platform: str):
        super().__init__(
            event_type='match_created',
            timestamp=datetime.utcnow(),
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id),
                'platform': platform
            }
        )

class MatchJoinedEvent(Event):
    def __init__(self, match_id: UUID, manager_id: UUID):
        super().__init__(
            event_type='match_joined',
            timestamp=datetime.utcnow(),
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id)
            }
        )

class BetPlacedEvent(Event):
    def __init__(self, match_id: UUID, manager_id: UUID, bet_id: UUID):
        super().__init__(
            event_type='bet_placed',
            timestamp=datetime.utcnow(),
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id),
                'bet_id': str(bet_id)
            }
        )

class DiceRolledEvent(Event):
    def __init__(self, match_id: UUID, manager_id: UUID, dice_value: int):
        super().__init__(
            event_type='dice_rolled',
            timestamp=datetime.utcnow(),
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id),
                'dice_value': dice_value
            }
        )

class TurnCompletedEvent(Event):
    def __init__(self, match_id: UUID, manager_id: UUID, turn_number: int):
        super().__init__(
            event_type='turn_completed',
            timestamp=datetime.utcnow(),
            data={
                'match_id': str(match_id),
                'manager_id': str(manager_id),
                'turn_number': turn_number
            }
        )

class MatchFinishedEvent(Event):
    def __init__(self, match_id: UUID, winner_id: UUID, loser_id: UUID, score: str):
        super().__init__(
            event_type='match_finished',
            timestamp=datetime.utcnow(),
            data={
                'match_id': str(match_id),
                'winner_id': str(winner_id),
                'loser_id': str(loser_id),
                'score': score
            }
        )

class EventBus:
    """Внутренняя шина событий"""
    
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Подписаться на событие"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    async def publish(self, event: Event) -> None:
        """Опубликовать событие"""
        handlers = self._handlers.get(event.event_type, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                # Log error but don't stop other handlers
                print(f"Error in event handler: {e}")
    
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Отписаться от события"""
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)
```

---

## 6. Database Connection

```python
# src/infrastructure/db/database.py

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)

class Database:
    """Управление подключением к БД"""
    
    def __init__(self, url: str):
        self.engine = create_async_engine(
            url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Контекстный менеджер для сессии"""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    async def set_user_context(self, session: AsyncSession, user_id: str) -> None:
        """Установить контекст пользователя для RLS"""
        await session.execute(
            f"SET LOCAL app.current_user_id = '{user_id}'"
        )
    
    async def close(self) -> None:
        """Закрыть все соединения"""
        await self.engine.dispose()
```
