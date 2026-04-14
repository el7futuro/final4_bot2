# src/platforms/telegram/handlers/bot_logic.py
"""Логика бота (автоматические ставки и пенальти)"""

import random
from uuid import UUID

from src.core.models.match import MatchPhase, PenaltyKick
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice
from src.core.engine.game_engine import BOT_USER_ID

from ..storage import get_storage


def bot_make_bets(storage, match):
    """Бот автоматически делает ставки"""
    engine = storage.engine
    
    available = engine.get_available_players(match, BOT_USER_ID)
    if not available:
        return match
    
    player = random.choice(available)
    
    available_types = engine.get_available_bet_types(match, BOT_USER_ID, player.id)
    if not available_types:
        return match
    
    turn_number = match.current_turn.turn_number if match.current_turn else 1
    is_goalkeeper_turn = turn_number == 1 and match.phase == MatchPhase.MAIN_TIME
    
    if is_goalkeeper_turn:
        bet_type = available_types[0]
        bet = _create_bot_bet(match, player, bet_type, turn_number)
        match, _ = engine.place_bet(match, BOT_USER_ID, player.id, bet)
    else:
        for i in range(min(2, len(available_types))):
            bet_type = available_types[i]
            bet = _create_bot_bet(match, player, bet_type, turn_number)
            match, _ = engine.place_bet(match, BOT_USER_ID, player.id, bet)
            available_types = engine.get_available_bet_types(match, BOT_USER_ID, player.id)
            if not available_types:
                break
    
    engine.confirm_bets(match, BOT_USER_ID)
    return match


def _create_bot_bet(match, player, bet_type, turn_number):
    """Создать ставку бота"""
    params = {
        "match_id": match.id,
        "manager_id": BOT_USER_ID,
        "player_id": player.id,
        "turn_number": turn_number,
        "bet_type": bet_type,
    }
    
    if bet_type == BetType.EVEN_ODD:
        params["even_odd_choice"] = random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
    elif bet_type == BetType.HIGH_LOW:
        params["high_low_choice"] = random.choice([HighLowChoice.HIGH, HighLowChoice.LOW])
    elif bet_type == BetType.EXACT_NUMBER:
        params["exact_number"] = random.randint(1, 6)
    
    return Bet(**params)


def auto_penalties(storage, match):
    """Автоматическая серия пенальти с сохранением результатов каждого удара"""
    engine = storage.engine
    history = engine.get_match_history(match)
    
    if not history:
        return engine.finish_by_lottery(match)
    
    players1 = history.get_all_players_ordered_for_penalties(match.manager1_id, match.manager1_id)
    players2 = history.get_all_players_ordered_for_penalties(match.manager2_id, match.manager1_id)
    
    goals1, goals2 = 0, 0
    max_kicks = min(5, len(players1), len(players2))
    penalty_results = []
    
    for i in range(max_kicks):
        p1 = players1[i]
        scored1 = p1.passes > 0
        if scored1:
            goals1 += 1
        penalty_results.append(PenaltyKick(
            manager_id=match.manager1_id,
            player_name=p1.player_name,
            scored=scored1
        ))
        
        p2 = players2[i]
        scored2 = p2.passes > 0
        if scored2:
            goals2 += 1
        penalty_results.append(PenaltyKick(
            manager_id=match.manager2_id,
            player_name=p2.player_name,
            scored=scored2
        ))
    
    match.penalty_results = penalty_results
    match.penalty_score_m1 = goals1
    match.penalty_score_m2 = goals2
    match.score.manager1_goals += goals1
    match.score.manager2_goals += goals2
    
    if goals1 > goals2:
        winner_id = match.manager1_id
    elif goals2 > goals1:
        winner_id = match.manager2_id
    else:
        winner_id = random.choice([match.manager1_id, match.manager2_id])
    
    match = engine.finish_penalty_shootout(match, winner_id)
    return match
