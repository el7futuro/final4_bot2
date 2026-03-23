# src/platforms/telegram/states/game_states.py
"""FSM состояния для игры"""

from aiogram.fsm.state import State, StatesGroup


class MatchStates(StatesGroup):
    """Состояния матча"""
    
    # Поиск/создание
    searching = State()
    waiting_opponent = State()
    
    # Настройка
    selecting_formation = State()
    selecting_lineup = State()
    
    # Игра
    in_game = State()
    making_bet = State()
    selecting_bet_player = State()
    selecting_bet_type = State()
    selecting_bet_value = State()
    waiting_roll = State()  # Ожидание броска кубика (показаны ставки)
    
    # Карточки
    applying_card = State()
    selecting_card_target = State()
    
    # Пенальти
    penalty_kick = State()


class ProfileStates(StatesGroup):
    """Состояния профиля"""
    
    viewing = State()
    editing_team_name = State()


class TeamStates(StatesGroup):
    """Состояния управления командой"""
    
    viewing = State()
    editing_player_name = State()
    selecting_player = State()
