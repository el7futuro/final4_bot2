# Модуль: REST API

## Обзор

REST API для будущего мобильного/веб-приложения. Использует FastAPI.

---

## 1. Структура модуля

```
src/platforms/api/
├── __init__.py
├── main.py                 # FastAPI приложение
├── routes/
│   ├── __init__.py
│   ├── auth.py             # Аутентификация
│   ├── users.py            # Пользователи
│   ├── matches.py          # Матчи
│   ├── bets.py             # Ставки
│   └── leaderboard.py      # Рейтинг
├── schemas/
│   ├── __init__.py
│   ├── auth.py             # Auth schemas
│   ├── users.py            # User schemas
│   ├── matches.py          # Match schemas
│   └── responses.py        # Generic responses
├── dependencies/
│   ├── __init__.py
│   ├── auth.py             # Auth dependencies
│   └── database.py         # DB dependencies
└── middleware/
    ├── __init__.py
    └── rate_limit.py       # Rate limiting
```

---

## 2. API Schemas

```python
# src/platforms/api/schemas/auth.py

from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from uuid import UUID

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until expiration")

class LoginRequest(BaseModel):
    platform: str = Field(description="telegram/vk/discord")
    platform_id: int = Field(description="Platform-specific user ID")
    platform_token: str = Field(description="Platform auth token for verification")

class RefreshRequest(BaseModel):
    refresh_token: str
```

```python
# src/platforms/api/schemas/users.py

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class UserStatsSchema(BaseModel):
    matches_played: int
    matches_won: int
    matches_lost: int
    matches_draw: int
    tournaments_won: int
    goals_scored: int
    goals_conceded: int
    win_streak: int
    best_win_streak: int

class UserResponse(BaseModel):
    id: UUID
    username: str
    plan: str
    rating: int
    stats: UserStatsSchema
    created_at: datetime

class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=1, max_length=50)

class LeaderboardEntrySchema(BaseModel):
    rank: int
    user_id: UUID
    username: str
    rating: int
    matches_won: int
```

```python
# src/platforms/api/schemas/matches.py

from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from enum import Enum

class MatchTypeEnum(str, Enum):
    RANDOM = "random"
    VS_BOT = "vs_bot"
    TOURNAMENT = "tournament"

class MatchStatusEnum(str, Enum):
    WAITING_FOR_OPPONENT = "waiting_for_opponent"
    SETTING_LINEUP = "setting_lineup"
    IN_PROGRESS = "in_progress"
    EXTRA_TIME = "extra_time"
    PENALTIES = "penalties"
    FINISHED = "finished"
    CANCELLED = "cancelled"

class FormationEnum(str, Enum):
    F_5_3_2 = "1-5-3-2"
    F_5_2_3 = "1-5-2-3"
    F_4_4_2 = "1-4-4-2"
    F_4_3_3 = "1-4-3-3"
    F_3_5_2 = "1-3-5-2"
    F_3_4_3 = "1-3-4-3"
    F_3_3_4 = "1-3-3-4"

class PlayerStatsSchema(BaseModel):
    saves: int
    passes: int
    goals: int

class PlayerSchema(BaseModel):
    id: UUID
    name: str
    position: str
    number: int
    stats: PlayerStatsSchema
    is_on_field: bool
    is_available: bool

class TeamSchema(BaseModel):
    id: UUID
    name: str
    formation: Optional[FormationEnum]
    players: List[PlayerSchema]
    total_saves: int
    total_passes: int
    total_goals: int

class ScoreSchema(BaseModel):
    manager1_goals: int
    manager2_goals: int

class TurnStateSchema(BaseModel):
    turn_number: int
    current_manager_id: UUID
    dice_rolled: bool
    dice_value: Optional[int]
    card_drawn: bool

class MatchResponse(BaseModel):
    id: UUID
    match_type: MatchTypeEnum
    status: MatchStatusEnum
    phase: str
    manager1_id: UUID
    manager2_id: Optional[UUID]
    score: ScoreSchema
    current_turn: Optional[TurnStateSchema]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

class MatchDetailResponse(MatchResponse):
    team1: Optional[TeamSchema]
    team2: Optional[TeamSchema]
    winner_id: Optional[UUID]
    loser_id: Optional[UUID]

class CreateMatchRequest(BaseModel):
    match_type: MatchTypeEnum

class JoinMatchRequest(BaseModel):
    match_id: UUID

class SetLineupRequest(BaseModel):
    formation: FormationEnum
    player_ids: List[UUID] = Field(min_length=11, max_length=11)

class MatchListResponse(BaseModel):
    matches: List[MatchResponse]
    total: int
    page: int
    per_page: int
```

```python
# src/platforms/api/schemas/bets.py

from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from enum import Enum

class BetTypeEnum(str, Enum):
    EVEN_ODD = "even_odd"
    HIGH_LOW = "high_low"
    EXACT_NUMBER = "exact_number"

class EvenOddChoice(str, Enum):
    EVEN = "even"
    ODD = "odd"

class HighLowChoice(str, Enum):
    LOW = "low"
    HIGH = "high"

class BetOutcomeEnum(str, Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"

class PlaceBetRequest(BaseModel):
    player_id: UUID
    bet_type: BetTypeEnum
    even_odd_choice: Optional[EvenOddChoice] = None
    high_low_choice: Optional[HighLowChoice] = None
    exact_number: Optional[int] = Field(None, ge=1, le=6)

class BetResponse(BaseModel):
    id: UUID
    player_id: UUID
    bet_type: BetTypeEnum
    even_odd_choice: Optional[EvenOddChoice]
    high_low_choice: Optional[HighLowChoice]
    exact_number: Optional[int]
    dice_roll: Optional[int]
    outcome: BetOutcomeEnum

class RollDiceResponse(BaseModel):
    dice_value: int
    won_bets: List[BetResponse]
    can_draw_card: bool
```

```python
# src/platforms/api/schemas/responses.py

from pydantic import BaseModel
from typing import Optional, Any

class SuccessResponse(BaseModel):
    success: bool = True
    message: str
    data: Optional[Any] = None

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
```

---

## 3. API Endpoints

```python
# src/platforms/api/main.py

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from src.infrastructure.db.database import Database
from src.infrastructure.cache.redis_client import RedisClient

from .routes import auth, users, matches, bets, leaderboard
from .middleware.rate_limit import RateLimitMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.database = Database(settings.DATABASE_URL)
    app.state.redis = RedisClient(settings.REDIS_URL)
    yield
    # Shutdown
    await app.state.database.close()
    await app.state.redis.close()

app = FastAPI(
    title="Final 4 API",
    description="REST API для игры Final 4",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting
app.add_middleware(RateLimitMiddleware)

# Routes
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(matches.router, prefix="/api/v1/matches", tags=["matches"])
app.include_router(bets.router, prefix="/api/v1/matches", tags=["bets"])
app.include_router(leaderboard.router, prefix="/api/v1/leaderboard", tags=["leaderboard"])

# Error handlers
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": str(exc)}
    )

@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"}
    )
```

```python
# src/platforms/api/routes/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timedelta
import jwt

from ..schemas.auth import TokenResponse, LoginRequest, RefreshRequest
from ..schemas.responses import ErrorResponse
from ..dependencies.database import get_database
from src.infrastructure.repositories.user_repository import UserRepository
from src.core.models.user import User, PlatformIds

router = APIRouter()

SECRET_KEY = "your-secret-key"  # From config
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "access"},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

@router.post(
    "/login",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}}
)
async def login(
    request: LoginRequest,
    database = Depends(get_database)
):
    """
    Аутентификация через платформу.
    
    Проверяет токен платформы и возвращает JWT токены.
    """
    # Verify platform token (implementation depends on platform)
    # For now, trust the platform_id
    
    async with database.session() as session:
        repo = UserRepository(session)
        
        if request.platform == "telegram":
            user = await repo.get_by_telegram_id(request.platform_id)
        elif request.platform == "vk":
            user = await repo.get_by_vk_id(request.platform_id)
        elif request.platform == "discord":
            user = await repo.get_by_discord_id(request.platform_id)
        else:
            raise HTTPException(status_code=400, detail="Invalid platform")
        
        if not user:
            # Create new user
            platform_ids = PlatformIds()
            if request.platform == "telegram":
                platform_ids.telegram_id = request.platform_id
            elif request.platform == "vk":
                platform_ids.vk_id = request.platform_id
            elif request.platform == "discord":
                platform_ids.discord_id = request.platform_id
            
            user = User(
                id=uuid4(),
                username=f"User_{request.platform_id}",
                platform_ids=platform_ids,
                created_at=datetime.utcnow(),
                last_active_at=datetime.utcnow()
            )
            user = await repo.create(user)
    
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}}
)
async def refresh_token(request: RefreshRequest):
    """Обновить access token."""
    try:
        payload = jwt.decode(
            request.refresh_token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        user_id = payload.get("sub")
        
        return TokenResponse(
            access_token=create_access_token(user_id),
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

```python
# src/platforms/api/routes/matches.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from uuid import UUID

from ..schemas.matches import (
    MatchResponse, MatchDetailResponse, MatchListResponse,
    CreateMatchRequest, JoinMatchRequest, SetLineupRequest,
    MatchStatusEnum
)
from ..schemas.responses import SuccessResponse, ErrorResponse
from ..dependencies.auth import get_current_user
from ..dependencies.database import get_database
from src.core.models.user import User
from src.core.models.match import MatchType
from src.application.services.match_service import MatchService

router = APIRouter()

@router.get(
    "",
    response_model=MatchListResponse,
    summary="Получить список матчей"
)
async def get_matches(
    status: Optional[MatchStatusEnum] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """
    Получить список матчей пользователя.
    
    - **status**: Фильтр по статусу (опционально)
    - **page**: Номер страницы
    - **per_page**: Количество на странице
    """
    match_service = MatchService(database)
    matches, total = await match_service.get_user_matches(
        user.id, status, page, per_page
    )
    
    return MatchListResponse(
        matches=[MatchResponse.model_validate(m) for m in matches],
        total=total,
        page=page,
        per_page=per_page
    )

@router.post(
    "",
    response_model=MatchResponse,
    status_code=201,
    summary="Создать матч"
)
async def create_match(
    request: CreateMatchRequest,
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """
    Создать новый матч.
    
    - **match_type**: Тип матча (random, vs_bot, tournament)
    """
    if not user.can_play_match():
        raise HTTPException(
            status_code=429,
            detail="Daily match limit reached"
        )
    
    match_service = MatchService(database)
    
    match_type = MatchType(request.match_type.value)
    match = await match_service.create_match(user.id, match_type, "api")
    
    return MatchResponse.model_validate(match)

@router.get(
    "/waiting",
    response_model=list[MatchResponse],
    summary="Получить ожидающие матчи"
)
async def get_waiting_matches(
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """Получить список матчей, ожидающих соперника."""
    match_service = MatchService(database)
    matches = await match_service.get_waiting_matches("api")
    
    # Exclude user's own matches
    matches = [m for m in matches if m.manager1_id != user.id]
    
    return [MatchResponse.model_validate(m) for m in matches]

@router.get(
    "/{match_id}",
    response_model=MatchDetailResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Получить детали матча"
)
async def get_match(
    match_id: UUID,
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """Получить детальную информацию о матче."""
    match_service = MatchService(database)
    match = await match_service.get_match(match_id)
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Check access
    if match.manager1_id != user.id and match.manager2_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return MatchDetailResponse.model_validate(match)

@router.post(
    "/{match_id}/join",
    response_model=MatchResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse}
    },
    summary="Присоединиться к матчу"
)
async def join_match(
    match_id: UUID,
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """Присоединиться к ожидающему матчу."""
    if not user.can_play_match():
        raise HTTPException(
            status_code=429,
            detail="Daily match limit reached"
        )
    
    match_service = MatchService(database)
    
    try:
        match = await match_service.join_match(match_id, user.id)
        return MatchResponse.model_validate(match)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/{match_id}/lineup",
    response_model=MatchResponse,
    responses={400: {"model": ErrorResponse}},
    summary="Установить состав"
)
async def set_lineup(
    match_id: UUID,
    request: SetLineupRequest,
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """
    Установить формацию и состав команды.
    
    - **formation**: Формация (1-4-4-2, etc.)
    - **player_ids**: Список из 11 UUID игроков
    """
    match_service = MatchService(database)
    
    try:
        match = await match_service.set_lineup(
            match_id,
            user.id,
            request.formation.value,
            request.player_ids
        )
        return MatchResponse.model_validate(match)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/{match_id}/roll",
    response_model=dict,
    responses={400: {"model": ErrorResponse}},
    summary="Бросить кубик"
)
async def roll_dice(
    match_id: UUID,
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """Бросить кубик и определить результаты ставок."""
    match_service = MatchService(database)
    
    try:
        match, dice_value, won_bets = await match_service.roll_dice(match_id, user.id)
        
        return {
            "dice_value": dice_value,
            "won_bets": [BetResponse.model_validate(b) for b in won_bets],
            "can_draw_card": len(won_bets) > 0
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/{match_id}/card/draw",
    response_model=dict,
    summary="Взять карточку Свисток"
)
async def draw_card(
    match_id: UUID,
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """Взять карточку из колоды Свисток."""
    match_service = MatchService(database)
    
    try:
        match, card = await match_service.draw_whistle_card(match_id, user.id)
        
        if card:
            return {
                "card": {
                    "id": str(card.id),
                    "type": card.card_type.value,
                    "requires_target": card.get_target_type() != "self_team"
                }
            }
        else:
            return {"card": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/{match_id}/card/apply",
    response_model=SuccessResponse,
    summary="Применить карточку"
)
async def apply_card(
    match_id: UUID,
    card_id: UUID,
    target_player_id: Optional[UUID] = None,
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """Применить карточку Свисток к цели."""
    match_service = MatchService(database)
    
    try:
        await match_service.apply_whistle_card(
            match_id, user.id, card_id, target_player_id
        )
        return SuccessResponse(message="Card applied")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/{match_id}/end-turn",
    response_model=MatchResponse,
    summary="Завершить ход"
)
async def end_turn(
    match_id: UUID,
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """Завершить текущий ход."""
    match_service = MatchService(database)
    
    try:
        match = await match_service.end_turn(match_id, user.id)
        return MatchResponse.model_validate(match)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

```python
# src/platforms/api/routes/bets.py

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from ..schemas.bets import PlaceBetRequest, BetResponse
from ..schemas.responses import ErrorResponse
from ..dependencies.auth import get_current_user
from ..dependencies.database import get_database
from src.core.models.user import User
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice

router = APIRouter()

@router.post(
    "/{match_id}/bets",
    response_model=BetResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}},
    summary="Разместить ставку"
)
async def place_bet(
    match_id: UUID,
    request: PlaceBetRequest,
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """
    Разместить ставку на игрока.
    
    - **player_id**: UUID игрока
    - **bet_type**: Тип ставки (even_odd, high_low, exact_number)
    - **even_odd_choice**: Для even_odd: even или odd
    - **high_low_choice**: Для high_low: low или high
    - **exact_number**: Для exact_number: число от 1 до 6
    """
    match_service = MatchService(database)
    
    # Build bet object
    bet = Bet(
        id=uuid4(),
        match_id=match_id,
        manager_id=user.id,
        player_id=request.player_id,
        turn_number=0,  # Will be set by service
        bet_type=BetType(request.bet_type.value)
    )
    
    if request.bet_type == BetTypeEnum.EVEN_ODD:
        if not request.even_odd_choice:
            raise HTTPException(status_code=400, detail="even_odd_choice required")
        bet.even_odd_choice = EvenOddChoice(request.even_odd_choice.value)
    
    elif request.bet_type == BetTypeEnum.HIGH_LOW:
        if not request.high_low_choice:
            raise HTTPException(status_code=400, detail="high_low_choice required")
        bet.high_low_choice = HighLowChoice(request.high_low_choice.value)
    
    elif request.bet_type == BetTypeEnum.EXACT_NUMBER:
        if not request.exact_number:
            raise HTTPException(status_code=400, detail="exact_number required")
        bet.exact_number = request.exact_number
    
    try:
        match, bet = await match_service.place_bet(match_id, user.id, request.player_id, bet)
        return BetResponse.model_validate(bet)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get(
    "/{match_id}/bets",
    response_model=list[BetResponse],
    summary="Получить ставки матча"
)
async def get_match_bets(
    match_id: UUID,
    user: User = Depends(get_current_user),
    database = Depends(get_database)
):
    """Получить все ставки пользователя в матче."""
    match_service = MatchService(database)
    bets = await match_service.get_user_bets_in_match(match_id, user.id)
    
    return [BetResponse.model_validate(b) for b in bets]
```

```python
# src/platforms/api/routes/leaderboard.py

from fastapi import APIRouter, Depends, Query

from ..schemas.users import LeaderboardEntrySchema
from ..dependencies.database import get_database
from src.infrastructure.repositories.user_repository import UserRepository

router = APIRouter()

@router.get(
    "",
    response_model=list[LeaderboardEntrySchema],
    summary="Таблица лидеров"
)
async def get_leaderboard(
    limit: int = Query(100, ge=1, le=500),
    database = Depends(get_database)
):
    """
    Получить таблицу лидеров по рейтингу.
    
    - **limit**: Максимальное количество записей (по умолчанию 100)
    """
    async with database.session() as session:
        repo = UserRepository(session)
        users = await repo.get_leaderboard(limit)
    
    return [
        LeaderboardEntrySchema(
            rank=i + 1,
            user_id=u.id,
            username=u.username,
            rating=u.rating,
            matches_won=u.stats.matches_won
        )
        for i, u in enumerate(users)
    ]
```

---

## 4. Dependencies

```python
# src/platforms/api/dependencies/auth.py

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from uuid import UUID

from .database import get_database
from src.infrastructure.repositories.user_repository import UserRepository
from src.core.models.user import User

security = HTTPBearer()

SECRET_KEY = "your-secret-key"  # From config
ALGORITHM = "HS256"

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    database = Depends(get_database)
) -> User:
    """Получить текущего пользователя из JWT токена."""
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = UUID(payload.get("sub"))
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    async with database.session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User banned: {user.ban_reason}"
        )
    
    return user
```

```python
# src/platforms/api/dependencies/database.py

from fastapi import Request
from src.infrastructure.db.database import Database

def get_database(request: Request) -> Database:
    """Получить экземпляр базы данных."""
    return request.app.state.database
```

---

## 5. API Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Аутентификация |
| POST | `/api/v1/auth/refresh` | Обновление токена |
| GET | `/api/v1/users/me` | Текущий пользователь |
| PATCH | `/api/v1/users/me` | Обновить профиль |
| GET | `/api/v1/matches` | Список матчей |
| POST | `/api/v1/matches` | Создать матч |
| GET | `/api/v1/matches/waiting` | Ожидающие матчи |
| GET | `/api/v1/matches/{id}` | Детали матча |
| POST | `/api/v1/matches/{id}/join` | Присоединиться |
| POST | `/api/v1/matches/{id}/lineup` | Установить состав |
| POST | `/api/v1/matches/{id}/bets` | Разместить ставку |
| GET | `/api/v1/matches/{id}/bets` | Ставки матча |
| POST | `/api/v1/matches/{id}/roll` | Бросить кубик |
| POST | `/api/v1/matches/{id}/card/draw` | Взять карточку |
| POST | `/api/v1/matches/{id}/card/apply` | Применить карточку |
| POST | `/api/v1/matches/{id}/end-turn` | Завершить ход |
| GET | `/api/v1/leaderboard` | Таблица лидеров |
