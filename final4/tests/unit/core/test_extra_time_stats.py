# tests/unit/core/test_extra_time_stats.py
"""Тесты изоляции статистики Extra Time"""

import pytest
from uuid import uuid4

from src.core.models.match import Match, MatchType, MatchPhase, MatchStatus, TurnState
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, HighLowChoice, EvenOddChoice
from src.core.engine.game_engine import GameEngine
from src.core.engine.score_calculator import ScoreCalculator


def create_test_team(manager_id):
    """Создать тестовую команду"""
    players = [
        Player(name="Вратарь", position=Position.GOALKEEPER, number=1),
    ]
    for i in range(5):
        players.append(Player(name=f"Защитник {i+1}", position=Position.DEFENDER, number=2+i))
    for i in range(6):
        players.append(Player(name=f"Полузащитник {i+1}", position=Position.MIDFIELDER, number=7+i))
    for i in range(4):
        players.append(Player(name=f"Форвард {i+1}", position=Position.FORWARD, number=13+i))
    
    return Team(manager_id=manager_id, name="Test Team", players=players)


class TestExtraTimeStatsIsolation:
    """Тесты изоляции статистики Extra Time"""
    
    def test_et_stats_separate_from_main_time(self):
        """Статистика ET должна считаться отдельно от Main Time"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = engine.create_match(manager1_id, MatchType.VS_BOT)
        match.manager2_id = manager2_id
        
        team1 = create_test_team(manager1_id)
        team2 = create_test_team(manager2_id)
        
        match = engine.set_team_without_formation(match, manager1_id, team1)
        match = engine.set_team_without_formation(match, manager2_id, team2)
        
        # Даём игроку Main Time статистику
        mt_player = team1.players[1]  # Защитник
        mt_player.add_passes(5)
        mt_player.add_goals(2)
        match.mark_player_used(manager1_id, mt_player.id)
        
        # Переходим в Extra Time
        match.phase = MatchPhase.EXTRA_TIME
        match.status = MatchStatus.EXTRA_TIME
        
        # Даём другому игроку ET статистику
        et_player = team1.players[5]  # Другой защитник
        et_player.add_passes(1)
        et_player.add_goals(1)
        match.used_players_extra_m1.append(str(et_player.id))
        
        # Проверяем что calculate_extra_time_score учитывает ТОЛЬКО ET игрока
        from src.platforms.telegram.renderers.match_renderer import MatchRenderer
        goals1, goals2, _ = MatchRenderer.calculate_extra_time_score(match)
        
        # В ET у team1 должен быть только 1 гол от et_player, не 2 от mt_player
        assert goals1 == 1
    
    def test_score_calculator_uses_phase_stats(self):
        """ScoreCalculator должен использовать только статистику указанной фазы"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = engine.create_match(manager1_id, MatchType.VS_BOT)
        match.manager2_id = manager2_id
        
        team1 = create_test_team(manager1_id)
        team2 = create_test_team(manager2_id)
        
        match = engine.set_team_without_formation(match, manager1_id, team1)
        match = engine.set_team_without_formation(match, manager2_id, team2)
        
        history = engine.get_match_history(match)
        assert history is not None
        
        # Добавляем статистику Main Time
        mt_stats = history.get_player_stats(manager1_id, team1.players[1].id, manager1_id)
        mt_stats.phase_played = MatchPhase.MAIN_TIME
        mt_stats.add_goals(3, "main time test")
        
        # Добавляем статистику Extra Time
        et_stats = history.get_player_stats(manager1_id, team1.players[5].id, manager1_id)
        et_stats.phase_played = MatchPhase.EXTRA_TIME
        et_stats.add_goals(1, "extra time test")
        
        calculator = ScoreCalculator()
        
        # Проверяем расчёт только по ET
        et_score = calculator.calculate_score_from_history(
            history, manager1_id, manager2_id, phase=MatchPhase.EXTRA_TIME
        )
        assert et_score.manager1_goals == 1  # Только ET гол
        
        # Проверяем расчёт по MT
        mt_score = calculator.calculate_score_from_history(
            history, manager1_id, manager2_id, phase=MatchPhase.MAIN_TIME
        )
        assert mt_score.manager1_goals == 3  # Только MT голы


class TestExtraTimeBettingRules:
    """Тесты правил ставок в Extra Time"""
    
    def test_et_second_bet_must_be_goal_if_first_not_goal(self):
        """Если первая ставка не на гол, вторая ОБЯЗАТЕЛЬНО на гол"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = engine.create_match(manager1_id, MatchType.VS_BOT)
        match.manager2_id = manager2_id
        
        team1 = create_test_team(manager1_id)
        team2 = create_test_team(manager2_id)
        
        match = engine.set_team_without_formation(match, manager1_id, team1)
        match = engine.set_team_without_formation(match, manager2_id, team2)
        
        # Переходим в Extra Time
        match.phase = MatchPhase.EXTRA_TIME
        match.status = MatchStatus.EXTRA_TIME
        match.current_turn = TurnState(turn_number=1)
        
        player = team1.players[1]  # Защитник
        
        # Первая ставка — больше/меньше (не гол)
        bet1 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=player.id,
            turn_number=1,
            bet_type=BetType.HIGH_LOW,
            high_low_choice=HighLowChoice.HIGH
        )
        match, _ = engine.place_bet(match, manager1_id, player.id, bet1)
        
        # Проверяем доступные типы для второй ставки — должен быть ТОЛЬКО гол
        available = engine.get_available_bet_types(match, manager1_id, player.id)
        assert available == [BetType.EXACT_NUMBER]
    
    def test_et_second_bet_must_be_positional_if_first_goal(self):
        """Если первая ставка на гол, вторая ОБЯЗАТЕЛЬНО позиционная"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = engine.create_match(manager1_id, MatchType.VS_BOT)
        match.manager2_id = manager2_id
        
        team1 = create_test_team(manager1_id)
        team2 = create_test_team(manager2_id)
        
        match = engine.set_team_without_formation(match, manager1_id, team1)
        match = engine.set_team_without_formation(match, manager2_id, team2)
        
        # Переходим в Extra Time
        match.phase = MatchPhase.EXTRA_TIME
        match.status = MatchStatus.EXTRA_TIME
        match.current_turn = TurnState(turn_number=1)
        
        player = team1.players[1]  # Защитник
        
        # Первая ставка — на гол
        bet1 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=player.id,
            turn_number=1,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=3
        )
        match, _ = engine.place_bet(match, manager1_id, player.id, bet1)
        
        # Проверяем доступные типы для второй ставки — НЕ должно быть гола
        available = engine.get_available_bet_types(match, manager1_id, player.id)
        assert BetType.EXACT_NUMBER not in available
        assert BetType.HIGH_LOW in available
        assert BetType.EVEN_ODD in available  # Защитник может чёт/нечёт
    
    def test_et_forward_only_high_low_for_second(self):
        """Форвард в ET: гол + больше/меньше (не чёт/нечёт)"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = engine.create_match(manager1_id, MatchType.VS_BOT)
        match.manager2_id = manager2_id
        
        team1 = create_test_team(manager1_id)
        team2 = create_test_team(manager2_id)
        
        match = engine.set_team_without_formation(match, manager1_id, team1)
        match = engine.set_team_without_formation(match, manager2_id, team2)
        
        # Переходим в Extra Time
        match.phase = MatchPhase.EXTRA_TIME
        match.status = MatchStatus.EXTRA_TIME
        match.current_turn = TurnState(turn_number=1)
        
        forward = team1.players[13]  # Форвард
        
        # Первая ставка — на гол
        bet1 = Bet(
            match_id=match.id,
            manager_id=manager1_id,
            player_id=forward.id,
            turn_number=1,
            bet_type=BetType.EXACT_NUMBER,
            exact_number=4
        )
        match, _ = engine.place_bet(match, manager1_id, forward.id, bet1)
        
        # Проверяем доступные типы для второй ставки форварда
        available = engine.get_available_bet_types(match, manager1_id, forward.id)
        assert BetType.EXACT_NUMBER not in available  # Гол уже сделан
        assert BetType.HIGH_LOW in available  # Больше/меньше доступно
        assert BetType.EVEN_ODD not in available  # Форварды не могут чёт/нечёт
