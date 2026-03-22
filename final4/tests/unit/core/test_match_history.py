# tests/unit/core/test_match_history.py
"""Тесты для MatchHistory — отслеживание статистики игроков"""

import pytest
from uuid import uuid4

from src.core.engine.game_engine import GameEngine
from src.core.models.match import MatchType, MatchStatus, MatchPhase
from src.core.models.team import Team, Formation, FORMATION_STRUCTURE
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice


def create_team(manager_id, name: str) -> Team:
    """Создать команду с 16 игроками"""
    players = []
    number = 1
    
    # 1 вратарь
    players.append(Player(name="Вратарь", position=Position.GOALKEEPER, number=number))
    number += 1
    
    # 5 защитников
    for i in range(5):
        players.append(Player(name=f"Защитник {i+1}", position=Position.DEFENDER, number=number))
        number += 1
    
    # 6 полузащитников
    for i in range(6):
        players.append(Player(name=f"Полузащитник {i+1}", position=Position.MIDFIELDER, number=number))
        number += 1
    
    # 4 нападающих
    for i in range(4):
        players.append(Player(name=f"Нападающий {i+1}", position=Position.FORWARD, number=number))
        number += 1
    
    return Team(manager_id=manager_id, name=name, players=players)


def select_lineup(team: Team, formation: Formation) -> list:
    """Выбрать состав для формации"""
    structure = FORMATION_STRUCTURE[formation]
    selected = []
    for pos_str, count in structure.items():
        pos = Position(pos_str)
        pos_players = team.get_players_by_position(pos)
        selected.extend(pos_players[:count])
    return [p.id for p in selected]


def setup_match(engine: GameEngine, manager1_id, manager2_id):
    """Настроить матч с обеими командами"""
    match = engine.create_match(manager1_id, MatchType.RANDOM)
    match = engine.join_match(match, manager2_id)
    
    team1 = create_team(manager1_id, "Команда 1")
    team2 = create_team(manager2_id, "Команда 2")
    
    formation = Formation.F_4_4_2
    lineup1 = select_lineup(team1, formation)
    lineup2 = select_lineup(team2, formation)
    
    match = engine.set_team_lineup(match, manager1_id, team1, formation, lineup1)
    match = engine.set_team_lineup(match, manager2_id, team2, formation, lineup2)
    
    return match


class TestMatchHistoryInitialization:
    """Тесты инициализации истории матча"""
    
    def test_history_created_on_match_start(self):
        """История создаётся при старте матча"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        
        history = engine.get_match_history(match)
        assert history is not None
        assert history.match_id == match.id
    
    def test_all_players_initialized_in_history(self):
        """Все 16 игроков обеих команд инициализированы в истории"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        assert len(history.manager1_players) == 16
        assert len(history.manager2_players) == 16
    
    def test_player_stats_start_at_zero(self):
        """Начальная статистика игроков = 0"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        for player_stats in history.manager1_players.values():
            assert player_stats.saves == 0
            assert player_stats.passes == 0
            assert player_stats.goals == 0


class TestMatchHistoryTracking:
    """Тесты записи статистики"""
    
    def test_stats_recorded_on_bet_win(self):
        """Статистика записывается при выигрыше ставки"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        
        # Первый ход — вратари
        gk1 = match.team1.get_goalkeeper()
        gk2 = match.team2.get_goalkeeper()
        
        # Делаем ставки
        bet1 = Bet(
            match_id=match.id, manager_id=manager1_id, player_id=gk1.id,
            turn_number=1, bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.EVEN
        )
        match, _ = engine.place_bet(match, manager1_id, gk1.id, bet1)
        engine.confirm_bets(match, manager1_id)
        
        bet2 = Bet(
            match_id=match.id, manager_id=manager2_id, player_id=gk2.id,
            turn_number=1, bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.ODD
        )
        match, _ = engine.place_bet(match, manager2_id, gk2.id, bet2)
        engine.confirm_bets(match, manager2_id)
        
        # Бросаем кубик
        match, dice_value, won_bets = engine.roll_dice(match)
        
        # Проверяем, что статистика записана в историю
        history = engine.get_match_history(match)
        gk1_stats = history.get_player_stats(manager1_id, gk1.id, match.manager1_id)
        
        assert gk1_stats is not None
        assert gk1_stats.turn_played == 1
        assert gk1_stats.phase_played == MatchPhase.MAIN_TIME
    
    def test_turn_played_recorded(self):
        """Записывается номер хода, когда игрок играл"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        # До хода — turn_played = None
        gk1 = match.team1.get_goalkeeper()
        gk1_stats = history.get_player_stats(manager1_id, gk1.id, match.manager1_id)
        assert gk1_stats.turn_played is None
        
        # Делаем ход
        bet1 = Bet(
            match_id=match.id, manager_id=manager1_id, player_id=gk1.id,
            turn_number=1, bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.EVEN
        )
        match, _ = engine.place_bet(match, manager1_id, gk1.id, bet1)
        engine.confirm_bets(match, manager1_id)
        
        gk2 = match.team2.get_goalkeeper()
        bet2 = Bet(
            match_id=match.id, manager_id=manager2_id, player_id=gk2.id,
            turn_number=1, bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.ODD
        )
        match, _ = engine.place_bet(match, manager2_id, gk2.id, bet2)
        engine.confirm_bets(match, manager2_id)
        
        match, _, _ = engine.roll_dice(match)
        
        # После хода — turn_played = 1
        gk1_stats = history.get_player_stats(manager1_id, gk1.id, match.manager1_id)
        assert gk1_stats.turn_played == 1


class TestMatchHistoryPenalties:
    """Тесты для пенальти"""
    
    def test_players_with_passes_listed(self):
        """Игроки с передачами возвращаются для пенальти"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        # Вручную добавляем передачу игроку
        gk = match.team1.get_goalkeeper()
        gk_stats = history.get_player_stats(manager1_id, gk.id, match.manager1_id)
        gk_stats.add_passes(2, "тест")
        
        players_with_passes = history.get_players_with_passes(manager1_id, match.manager1_id)
        
        assert len(players_with_passes) == 1
        assert players_with_passes[0].player_id == gk.id
        assert players_with_passes[0].passes == 2
    
    def test_penalty_order_extra_time_first(self):
        """Порядок пенальти: сначала Extra Time, потом Main Time"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        # Симулируем Main Time игрока
        defender = match.team1.get_players_by_position(Position.DEFENDER)[0]
        df_stats = history.get_player_stats(manager1_id, defender.id, match.manager1_id)
        df_stats.turn_played = 5
        df_stats.phase_played = MatchPhase.MAIN_TIME
        df_stats.add_passes(1, "тест")
        
        # Симулируем Extra Time игрока
        midfielder = match.team1.get_players_by_position(Position.MIDFIELDER)[0]
        mf_stats = history.get_player_stats(manager1_id, midfielder.id, match.manager1_id)
        mf_stats.turn_played = 2
        mf_stats.phase_played = MatchPhase.EXTRA_TIME
        mf_stats.add_passes(2, "тест")
        
        # Проверяем порядок
        ordered = history.get_all_players_ordered_for_penalties(manager1_id, match.manager1_id)
        
        # Extra Time должен быть первым
        played_players = [p for p in ordered if p.turn_played is not None]
        assert len(played_players) >= 2
        assert played_players[0].phase_played == MatchPhase.EXTRA_TIME
        assert played_players[1].phase_played == MatchPhase.MAIN_TIME


class TestMatchHistoryAddActions:
    """Тесты методов добавления/удаления действий"""
    
    def test_add_saves_updates_stats(self):
        """add_saves обновляет статистику и историю"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        gk = match.team1.get_goalkeeper()
        stats = history.get_player_stats(manager1_id, gk.id, match.manager1_id)
        
        stats.add_saves(3, "чёт/нечёт")
        
        assert stats.saves == 3
        assert "+3 отб (чёт/нечёт)" in stats.history
    
    def test_add_passes_updates_stats(self):
        """add_passes обновляет статистику и историю"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        mf = match.team1.get_players_by_position(Position.MIDFIELDER)[0]
        stats = history.get_player_stats(manager1_id, mf.id, match.manager1_id)
        
        stats.add_passes(2, "больше/меньше")
        
        assert stats.passes == 2
        assert "+2 перед (больше/меньше)" in stats.history
    
    def test_add_goals_updates_stats(self):
        """add_goals обновляет статистику и историю"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        fw = match.team1.get_players_by_position(Position.FORWARD)[0]
        stats = history.get_player_stats(manager1_id, fw.id, match.manager1_id)
        
        stats.add_goals(1, "точное число")
        
        assert stats.goals == 1
        assert "+1 гол (точное число)" in stats.history
    
    def test_remove_saves_decreases_stats(self):
        """remove_saves уменьшает статистику"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        gk = match.team1.get_goalkeeper()
        stats = history.get_player_stats(manager1_id, gk.id, match.manager1_id)
        
        stats.add_saves(3, "тест")
        stats.remove_saves(1, "фол")
        
        assert stats.saves == 2
        assert "-1 отб (фол)" in stats.history
    
    def test_clear_all_resets_stats(self):
        """clear_all обнуляет всю статистику"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        mf = match.team1.get_players_by_position(Position.MIDFIELDER)[0]
        stats = history.get_player_stats(manager1_id, mf.id, match.manager1_id)
        
        stats.add_saves(2, "тест")
        stats.add_passes(3, "тест")
        stats.add_goals(1, "тест")
        
        stats.clear_all("удаление")
        
        assert stats.saves == 0
        assert stats.passes == 0
        assert stats.goals == 0
        assert "Все действия обнулены (удаление)" in stats.history


class TestTotalStats:
    """Тесты суммарной статистики команды"""
    
    def test_get_total_stats_sums_all_players(self):
        """get_total_stats суммирует статистику всех игроков"""
        engine = GameEngine()
        manager1_id = uuid4()
        manager2_id = uuid4()
        
        match = setup_match(engine, manager1_id, manager2_id)
        history = engine.get_match_history(match)
        
        # Добавляем статистику нескольким игрокам
        gk = match.team1.get_goalkeeper()
        gk_stats = history.get_player_stats(manager1_id, gk.id, match.manager1_id)
        gk_stats.add_saves(3, "тест")
        
        df = match.team1.get_players_by_position(Position.DEFENDER)[0]
        df_stats = history.get_player_stats(manager1_id, df.id, match.manager1_id)
        df_stats.add_passes(1, "тест")
        df_stats.add_saves(2, "тест")
        
        fw = match.team1.get_players_by_position(Position.FORWARD)[0]
        fw_stats = history.get_player_stats(manager1_id, fw.id, match.manager1_id)
        fw_stats.add_goals(2, "тест")
        
        total = history.get_total_stats(manager1_id, match.manager1_id)
        
        assert total["saves"] == 5  # 3 + 2
        assert total["passes"] == 1
        assert total["goals"] == 2
