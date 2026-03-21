# src/infrastructure/repositories/team_repository.py
"""Реализация репозитория команд"""

from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.team import Team, Formation
from src.core.models.player import Player, Position
from src.core.interfaces.repositories import ITeamRepository
from ..db.models import TeamModel


# Дефолтные имена игроков по позициям
DEFAULT_PLAYERS = {
    Position.GOALKEEPER: ["Вратарь 1", "Вратарь 2"],
    Position.DEFENDER: ["Защитник 1", "Защитник 2", "Защитник 3", "Защитник 4", "Защитник 5"],
    Position.MIDFIELDER: ["Полузащитник 1", "Полузащитник 2", "Полузащитник 3", "Полузащитник 4", "Полузащитник 5"],
    Position.FORWARD: ["Форвард 1", "Форвард 2", "Форвард 3", "Форвард 4"],
}


class TeamRepository(ITeamRepository):
    """PostgreSQL репозиторий команд"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, team_id: UUID) -> Optional[Team]:
        """Получить команду по ID"""
        result = await self.session.execute(
            select(TeamModel).where(TeamModel.id == team_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def get_by_user_id(self, user_id: UUID) -> Optional[Team]:
        """Получить команду пользователя"""
        result = await self.session.execute(
            select(TeamModel).where(TeamModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
    
    async def create(self, team: Team) -> Team:
        """Создать команду"""
        model = self._to_model(team)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_domain(model)
    
    async def update(self, team: Team) -> Team:
        """Обновить команду"""
        players_data = [p.model_dump(mode='json') for p in team.players]
        
        await self.session.execute(
            update(TeamModel)
            .where(TeamModel.id == team.id)
            .values(
                name=team.name,
                players=players_data,
                formation=team.formation.value if team.formation else None
            )
        )
        await self.session.flush()
        return team
    
    async def create_default_team(self, user_id: UUID, team_name: str) -> Team:
        """Создать команду с дефолтными игроками (16 штук)"""
        players: List[Player] = []
        number = 1
        
        for position, names in DEFAULT_PLAYERS.items():
            for name in names:
                players.append(Player(
                    id=uuid4(),
                    name=name,
                    position=position,
                    number=number,
                ))
                number += 1
        
        team = Team(
            id=uuid4(),
            manager_id=user_id,
            name=team_name,
            players=players
        )
        
        return await self.create(team)
    
    def _to_domain(self, model: TeamModel) -> Team:
        """Преобразовать модель БД в доменную модель"""
        players = []
        for p_data in model.players or []:
            # Конвертируем строковую позицию в enum
            if isinstance(p_data.get('position'), str):
                p_data['position'] = Position(p_data['position'])
            players.append(Player(**p_data))
        
        formation = None
        if model.formation:
            formation = Formation(model.formation)
        
        return Team(
            id=model.id,
            manager_id=model.user_id,
            name=model.name,
            players=players,
            formation=formation
        )
    
    def _to_model(self, team: Team) -> TeamModel:
        """Преобразовать доменную модель в модель БД"""
        players_data = [p.model_dump(mode='json') for p in team.players]
        
        return TeamModel(
            id=team.id,
            user_id=team.manager_id,
            name=team.name,
            players=players_data,
            formation=team.formation.value if team.formation else None
        )
