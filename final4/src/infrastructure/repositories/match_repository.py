# src/infrastructure/repositories/match_repository.py
"""Реализация репозитория матчей"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_, or_, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.match import (
    Match, MatchStatus, MatchType, MatchPhase,
    TurnState, MatchScore, MatchResult
)
from src.core.models.team import Team
from src.core.models.bet import Bet
from src.core.models.whistle_card import WhistleCard
from src.core.interfaces.repositories import IMatchRepository
from ..db.models import MatchModel


class MatchRepository(IMatchRepository):
    """PostgreSQL репозиторий матчей"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, match_id: UUID) -> Optional[Match]:
        """Получить матч по ID"""
        result = await self.session.execute(
            select(MatchModel).where(MatchModel.id == match_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def create(self, match: Match) -> Match:
        """Создать матч"""
        model = self._to_model(match)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_domain(model)
    
    async def update(self, match: Match) -> Match:
        """Обновить матч"""
        await self.session.execute(
            update(MatchModel)
            .where(MatchModel.id == match.id)
            .values(
                status=match.status.value,
                phase=match.phase.value,
                manager2_id=match.manager2_id,
                team1_snapshot=match.team1.model_dump(mode='json') if match.team1 else None,
                team2_snapshot=match.team2.model_dump(mode='json') if match.team2 else None,
                current_turn=match.current_turn.model_dump(mode='json') if match.current_turn else None,
                total_turns_main=match.total_turns_main,
                total_turns_extra=match.total_turns_extra,
                used_players_main_m1=match.used_players_main_m1,
                used_players_main_m2=match.used_players_main_m2,
                used_players_extra_m1=match.used_players_extra_m1,
                used_players_extra_m2=match.used_players_extra_m2,
                whistle_deck=[c.model_dump(mode='json') for c in match.whistle_deck],
                whistle_cards_drawn=[c.model_dump(mode='json') for c in match.whistle_cards_drawn],
                bets=[b.model_dump(mode='json') for b in match.bets],
                score_manager1=match.score.manager1_goals,
                score_manager2=match.score.manager2_goals,
                winner_id=match.result.winner_id if match.result else None,
                loser_id=match.result.loser_id if match.result else None,
                decided_by=match.result.decided_by.value if match.result else None,
                decided_by_lottery=match.result.decided_by_lottery if match.result else False,
                penalty_results=[p.model_dump(mode='json') for p in match.penalty_results],
                penalty_score_m1=match.penalty_score_m1,
                penalty_score_m2=match.penalty_score_m2,
                started_at=match.started_at,
                finished_at=match.finished_at
            )
        )
        await self.session.flush()
        return match
    
    async def get_waiting_matches(self, platform: str) -> List[Match]:
        """Получить ожидающие соперника матчи"""
        result = await self.session.execute(
            select(MatchModel)
            .where(
                and_(
                    MatchModel.platform == platform,
                    MatchModel.status == MatchStatus.WAITING_FOR_OPPONENT.value,
                    MatchModel.match_type == MatchType.RANDOM.value
                )
            )
            .order_by(MatchModel.created_at)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]
    
    async def get_user_active_match(self, user_id: UUID) -> Optional[Match]:
        """Получить активный матч пользователя"""
        active_statuses = [
            MatchStatus.WAITING_FOR_OPPONENT.value,
            MatchStatus.SETTING_LINEUP.value,
            MatchStatus.IN_PROGRESS.value,
            MatchStatus.EXTRA_TIME.value,
            MatchStatus.PENALTIES.value,
        ]
        
        result = await self.session.execute(
            select(MatchModel)
            .where(
                and_(
                    or_(
                        MatchModel.manager1_id == user_id,
                        MatchModel.manager2_id == user_id
                    ),
                    MatchModel.status.in_(active_statuses)
                )
            )
            .order_by(desc(MatchModel.created_at))
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def get_user_matches(
        self,
        user_id: UUID,
        status: Optional[MatchStatus] = None,
        limit: int = 10
    ) -> List[Match]:
        """Получить матчи пользователя"""
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
        """Получить историю матчей"""
        query = select(MatchModel).where(
            and_(
                or_(
                    MatchModel.manager1_id == user_id,
                    MatchModel.manager2_id == user_id
                ),
                MatchModel.status == MatchStatus.FINISHED.value
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
        """Преобразовать модель БД в доменную модель"""
        team1 = self._parse_team(model.team1_snapshot) if model.team1_snapshot else None
        team2 = self._parse_team(model.team2_snapshot) if model.team2_snapshot else None
        
        current_turn = TurnState(**model.current_turn) if model.current_turn else None
        
        bets = [Bet(**b_data) for b_data in model.bets or []]
        whistle_deck = [WhistleCard(**c) for c in model.whistle_deck or []]
        whistle_cards_drawn = [WhistleCard(**c) for c in model.whistle_cards_drawn or []]
        
        # Пенальти
        from src.core.models.match import PenaltyKick
        penalty_results = [PenaltyKick(**p) for p in model.penalty_results or []]
        
        result = None
        if model.winner_id:
            result = MatchResult(
                winner_id=model.winner_id,
                loser_id=model.loser_id,
                final_score=MatchScore(
                    manager1_goals=model.score_manager1,
                    manager2_goals=model.score_manager2
                ),
                decided_by=MatchPhase(model.decided_by) if model.decided_by else MatchPhase.MAIN_TIME,
                decided_by_lottery=model.decided_by_lottery
            )
        
        return Match(
            id=model.id,
            match_type=MatchType(model.match_type),
            status=MatchStatus(model.status),
            phase=MatchPhase(model.phase),
            manager1_id=model.manager1_id,
            manager2_id=model.manager2_id,
            team1=team1,
            team2=team2,
            current_turn=current_turn,
            total_turns_main=model.total_turns_main,
            total_turns_extra=model.total_turns_extra,
            used_players_main_m1=model.used_players_main_m1 or [],
            used_players_main_m2=model.used_players_main_m2 or [],
            used_players_extra_m1=model.used_players_extra_m1 or [],
            used_players_extra_m2=model.used_players_extra_m2 or [],
            bets=bets,
            whistle_cards_drawn=whistle_cards_drawn,
            whistle_deck=whistle_deck,
            score=MatchScore(
                manager1_goals=model.score_manager1,
                manager2_goals=model.score_manager2
            ),
            result=result,
            penalty_results=penalty_results,
            penalty_score_m1=model.penalty_score_m1,
            penalty_score_m2=model.penalty_score_m2,
            created_at=model.created_at,
            started_at=model.started_at,
            finished_at=model.finished_at,
            platform=model.platform
        )
    
    def _parse_team(self, data: dict) -> Team:
        """Парсить команду из JSON"""
        from src.core.models.player import Player, Position
        from src.core.models.team import Formation
        
        players = []
        for p_data in data.get('players', []):
            if isinstance(p_data.get('position'), str):
                p_data['position'] = Position(p_data['position'])
            players.append(Player(**p_data))
        
        formation = None
        if data.get('formation'):
            formation = Formation(data['formation'])
        
        return Team(
            id=UUID(data['id']) if isinstance(data['id'], str) else data['id'],
            manager_id=UUID(data['manager_id']) if isinstance(data['manager_id'], str) else data['manager_id'],
            name=data['name'],
            players=players,
            formation=formation
        )
    
    def _to_model(self, match: Match) -> MatchModel:
        """Преобразовать доменную модель в модель БД"""
        return MatchModel(
            id=match.id,
            match_type=match.match_type.value,
            status=match.status.value,
            phase=match.phase.value,
            manager1_id=match.manager1_id,
            manager2_id=match.manager2_id,
            team1_snapshot=match.team1.model_dump(mode='json') if match.team1 else None,
            team2_snapshot=match.team2.model_dump(mode='json') if match.team2 else None,
            current_turn=match.current_turn.model_dump(mode='json') if match.current_turn else None,
            total_turns_main=match.total_turns_main,
            total_turns_extra=match.total_turns_extra,
            used_players_main_m1=match.used_players_main_m1,
            used_players_main_m2=match.used_players_main_m2,
            used_players_extra_m1=match.used_players_extra_m1,
            used_players_extra_m2=match.used_players_extra_m2,
            whistle_deck=[c.model_dump(mode='json') for c in match.whistle_deck],
            whistle_cards_drawn=[c.model_dump(mode='json') for c in match.whistle_cards_drawn],
            bets=[b.model_dump(mode='json') for b in match.bets],
            score_manager1=match.score.manager1_goals,
            score_manager2=match.score.manager2_goals,
            winner_id=match.result.winner_id if match.result else None,
            loser_id=match.result.loser_id if match.result else None,
            decided_by=match.result.decided_by.value if match.result else None,
            decided_by_lottery=match.result.decided_by_lottery if match.result else False,
            penalty_results=[p.model_dump(mode='json') for p in match.penalty_results],
            penalty_score_m1=match.penalty_score_m1,
            penalty_score_m2=match.penalty_score_m2,
            platform=match.platform,
            created_at=match.created_at,
            started_at=match.started_at,
            finished_at=match.finished_at
        )
