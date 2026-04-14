# tests/integration/test_db_integration.py
"""Интеграционный тест: PostgreSQL CRUD через репозитории"""

import asyncio
import pytest
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.infrastructure.db.models import Base
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.repositories.match_repository import MatchRepository
from src.core.models.match import Match, MatchType, MatchStatus, MatchPhase, MatchScore, MatchResult, PenaltyKick
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, EvenOddChoice
from src.core.models.whistle_card import WhistleCard, CardType
from src.core.models.user import User, UserPlan, PlatformIds, UserStats, DailyLimits


DATABASE_URL = "postgresql+asyncpg://final4:final4_password@localhost:5432/final4"


@pytest.fixture
async def session():
    eng = create_async_engine(DATABASE_URL, echo=False)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()
    await eng.dispose()


def _make_team(mgr_id, name):
    players = [Player(name='GK', position=Position.GOALKEEPER, number=1)]
    for i in range(5):
        players.append(Player(name=f'DF{i+1}', position=Position.DEFENDER, number=2+i))
    for i in range(6):
        players.append(Player(name=f'MF{i+1}', position=Position.MIDFIELDER, number=7+i))
    for i in range(4):
        players.append(Player(name=f'FW{i+1}', position=Position.FORWARD, number=13+i))
    return Team(manager_id=mgr_id, name=name, players=players)


class TestUserRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_user(self, session):
        repo = UserRepository(session)
        
        user = User(
            username="TestPlayer",
            platform_ids=PlatformIds(telegram_id=123456789),
            rating=1200
        )
        
        created = await repo.create(user)
        assert created.id is not None
        assert created.username == "TestPlayer"
        
        found = await repo.get_by_telegram_id(123456789)
        assert found is not None
        assert found.username == "TestPlayer"
        assert found.rating == 1200
    
    @pytest.mark.asyncio
    async def test_update_user_stats(self, session):
        repo = UserRepository(session)
        
        user = User(
            username="StatsPlayer",
            platform_ids=PlatformIds(telegram_id=987654321),
        )
        created = await repo.create(user)
        
        created.stats.matches_played = 10
        created.stats.matches_won = 7
        created.rating = 1500
        await repo.update(created)
        
        found = await repo.get_by_id(created.id)
        assert found.stats.matches_played == 10
        assert found.stats.matches_won == 7
        assert found.rating == 1500


class TestMatchRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_match(self, session):
        # Сначала создаём пользователей
        user_repo = UserRepository(session)
        u1 = await user_repo.create(User(
            username="Player1",
            platform_ids=PlatformIds(telegram_id=111111111),
        ))
        u2 = await user_repo.create(User(
            username="Player2",
            platform_ids=PlatformIds(telegram_id=222222222),
        ))
        
        # Создаём матч
        t1 = _make_team(u1.id, "Team1")
        t2 = _make_team(u2.id, "Team2")
        
        match = Match(
            match_type=MatchType.RANDOM,
            manager1_id=u1.id,
            manager2_id=u2.id,
            team1=t1,
            team2=t2,
            status=MatchStatus.IN_PROGRESS,
        )
        
        repo = MatchRepository(session)
        created = await repo.create(match)
        assert created.id is not None
        
        found = await repo.get_by_id(created.id)
        assert found is not None
        assert found.match_type == MatchType.RANDOM
        assert found.team1 is not None
        assert len(found.team1.players) == 16
    
    @pytest.mark.asyncio
    async def test_save_and_load_match_state(self, session):
        """Полный цикл: создать, обновить (ставки, карточки, пенальти), загрузить"""
        user_repo = UserRepository(session)
        u1 = await user_repo.create(User(
            username="P1", platform_ids=PlatformIds(telegram_id=333333333),
        ))
        u2 = await user_repo.create(User(
            username="P2", platform_ids=PlatformIds(telegram_id=444444444),
        ))
        
        t1 = _make_team(u1.id, "T1")
        t2 = _make_team(u2.id, "T2")
        
        match = Match(
            match_type=MatchType.RANDOM,
            manager1_id=u1.id,
            manager2_id=u2.id,
            team1=t1,
            team2=t2,
            status=MatchStatus.FINISHED,
        )
        
        # Добавляем данные
        match.used_players_main_m1 = [str(t1.players[i].id) for i in range(11)]
        match.used_players_main_m2 = [str(t2.players[i].id) for i in range(11)]
        match.score = MatchScore(manager1_goals=2, manager2_goals=2)
        match.penalty_results = [
            PenaltyKick(manager_id=u1.id, player_name="FW1", scored=True),
            PenaltyKick(manager_id=u2.id, player_name="FW2", scored=False),
        ]
        match.penalty_score_m1 = 1
        match.penalty_score_m2 = 0
        match.result = MatchResult(
            winner_id=u1.id,
            loser_id=u2.id,
            final_score=match.score,
            decided_by=MatchPhase.PENALTIES,
        )
        
        # Ставка
        match.bets.append(Bet(
            match_id=match.id, manager_id=u1.id,
            player_id=t1.players[0].id, turn_number=1,
            bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.EVEN
        ))
        
        # Карточки
        match.whistle_cards_drawn.append(WhistleCard(card_type=CardType.GOAL))
        
        repo = MatchRepository(session)
        await repo.create(match)
        await repo.update(match)
        
        loaded = await repo.get_by_id(match.id)
        assert loaded.status == MatchStatus.FINISHED
        assert len(loaded.used_players_main_m1) == 11
        assert loaded.penalty_score_m1 == 1
        assert len(loaded.penalty_results) == 2
        assert loaded.penalty_results[0].player_name == "FW1"
        assert loaded.penalty_results[0].scored is True
        assert len(loaded.bets) == 1
        assert loaded.bets[0].bet_type == BetType.EVEN_ODD
        assert len(loaded.whistle_cards_drawn) == 1
        assert loaded.result.decided_by == MatchPhase.PENALTIES
