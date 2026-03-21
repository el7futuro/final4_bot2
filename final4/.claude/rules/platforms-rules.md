---
glob: src/platforms/**/*.py
---

# Правила для Platforms

## 1. Изоляция от Core
Адаптеры НЕ содержат бизнес-логики:
```python
# ✅ Правильно — вызов Core
@router.callback_query(GameCallback.filter(F.action == "roll_dice"))
async def roll_dice(callback: CallbackQuery, user: User, match_service: MatchService):
    match, dice_value, won_bets = await match_service.roll_dice(match_id, user.id)
    await callback.message.edit_text(render_turn_summary(dice_value, won_bets))

# ❌ Неправильно — бизнес-логика в адаптере
async def roll_dice(callback: CallbackQuery):
    dice = random.randint(1, 6)  # Логика должна быть в Core!
```

## 2. Callback Data
Уникальные префиксы для каждого типа:
```python
# Telegram (aiogram 3.x)
class MenuCallback(CallbackData, prefix="menu"):
    action: str

class MatchCallback(CallbackData, prefix="match"):
    action: str
    match_id: Optional[str] = None

class BetCallback(CallbackData, prefix="bet"):
    action: str
    bet_type: Optional[str] = None
    player_id: Optional[str] = None
```

## 3. Рендеринг
Отдельный модуль для форматирования:
```python
# renderers/match_renderer.py
class MatchRenderer:
    @staticmethod
    def render_match_status(match: Match, user: User) -> str:
        """Рендерит статус матча для конкретной платформы"""
        ...
```

## 4. Клавиатуры
Отдельный модуль:
```python
# keyboards/inline.py
class Keyboards:
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        ...
    
    @staticmethod
    def bet_type_select(player: Player, available: List[BetType]) -> InlineKeyboardMarkup:
        ...
```

## 5. Middleware
Auth и Rate Limit:
```python
class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = await get_or_create_user(event.from_user.id)
        data["user"] = user
        return await handler(event, data)
```

## 6. FSM States
Для сложных диалогов:
```python
class MatchStates(StatesGroup):
    waiting_opponent = State()
    selecting_formation = State()
    selecting_lineup = State()
    placing_bets = State()
```

## 7. Обработка ошибок
```python
try:
    match = await match_service.place_bet(...)
except ValueError as e:
    await callback.answer(str(e), show_alert=True)
    return
```
