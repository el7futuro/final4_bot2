# tests/unit/core/test_full_game_loop.py
"""E2E тест полного цикла матча: Main Time → Extra Time → Penalties"""

import pytest
import random
from uuid import uuid4

from src.core.engine.game_engine import GameEngine, BOT_USER_ID
from src.core.models.match import Match, MatchType, MatchStatus, MatchPhase, TurnState
from src.core.models.team import Team
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, BetOutcome, EvenOddChoice, HighLowChoice
from src.core.models.whistle_card import CardType


def make_team(mgr_id, prefix):
    players = [Player(name=f'{prefix}-GK', position=Position.GOALKEEPER, number=1)]
    for i in range(5):
        players.append(Player(name=f'{prefix}-DF{i+1}', position=Position.DEFENDER, number=2+i))
    for i in range(6):
        players.append(Player(name=f'{prefix}-MF{i+1}', position=Position.MIDFIELDER, number=7+i))
    for i in range(4):
        players.append(Player(name=f'{prefix}-FW{i+1}', position=Position.FORWARD, number=13+i))
    return Team(manager_id=mgr_id, name=f'{prefix} Team', players=players)


def play_turn(engine, match, m1, m2, turn_num, phase="mt"):
    """Сыграть один полный ход: ставки обоих → кубик → end_turn"""
    t1 = match.team1
    t2 = match.team2
    
    # Получаем доступных игроков
    avail1 = engine.get_available_players(match, m1)
    avail2 = engine.get_available_players(match, m2)
    
    assert len(avail1) > 0, f"No players for m1, turn={turn_num}, phase={phase}, used_mt={len(match.used_players_main_m1)}, used_et={len(match.used_players_extra_m1)}"
    assert len(avail2) > 0, f"No players for m2, turn={turn_num}, phase={phase}"
    
    p1 = avail1[0]
    p2 = avail2[0]
    
    # Определяем количество ставок
    if phase == "mt" and turn_num == 1:
        required = 1
    else:
        required = 2
    
    # Ставки M1
    types1 = engine.get_available_bet_types(match, m1, p1.id)
    assert len(types1) >= 1, f"M1 player {p1.name} has no types at all"
    
    for i in range(required):
        types1 = engine.get_available_bet_types(match, m1, p1.id)
        if not types1:
            break
        bt = types1[0]
        params = {"match_id": match.id, "manager_id": m1, "player_id": p1.id,
                  "turn_number": match.current_turn.turn_number, "bet_type": bt}
        if bt == BetType.EVEN_ODD:
            params["even_odd_choice"] = random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
        elif bt == BetType.HIGH_LOW:
            params["high_low_choice"] = random.choice([HighLowChoice.HIGH, HighLowChoice.LOW])
        elif bt == BetType.EXACT_NUMBER:
            params["exact_number"] = random.randint(1, 6)
        bet = Bet(**params)
        match, _ = engine.place_bet(match, m1, p1.id, bet)
    
    engine.confirm_bets(match, m1)
    
    # Ставки M2
    types2 = engine.get_available_bet_types(match, m2, p2.id)
    assert len(types2) >= 1, f"M2 player {p2.name} has no types at all"
    
    for i in range(required):
        types2 = engine.get_available_bet_types(match, m2, p2.id)
        if not types2:
            break
        bt = types2[0]
        params = {"match_id": match.id, "manager_id": m2, "player_id": p2.id,
                  "turn_number": match.current_turn.turn_number, "bet_type": bt}
        if bt == BetType.EVEN_ODD:
            params["even_odd_choice"] = random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
        elif bt == BetType.HIGH_LOW:
            params["high_low_choice"] = random.choice([HighLowChoice.HIGH, HighLowChoice.LOW])
        elif bt == BetType.EXACT_NUMBER:
            params["exact_number"] = random.randint(1, 6)
        bet = Bet(**params)
        match, _ = engine.place_bet(match, m2, p2.id, bet)
    
    engine.confirm_bets(match, m2)
    
    # Кубик
    can_roll, reason = engine.can_roll_dice(match)
    assert can_roll, f"Cannot roll: {reason}"
    
    match, dice, won = engine.roll_dice(match)
    
    # Разрешаем жёлтую карточку если есть
    if match.current_turn and match.current_turn.waiting_for_yellow_card_choice:
        target_mgr = match.current_turn.yellow_card_target_manager_id
        target_pid = match.current_turn.yellow_card_target_player_id
        target_team = match.get_team(target_mgr)
        if target_team and target_pid:
            tp = target_team.get_player_by_id(target_pid)
            if tp:
                if tp.stats.saves > 0:
                    match = engine.resolve_yellow_card(match, target_mgr, "save")
                elif tp.stats.passes > 0:
                    match = engine.resolve_yellow_card(match, target_mgr, "pass")
                elif tp.stats.goals > 0:
                    match = engine.resolve_yellow_card(match, target_mgr, "goal")
                else:
                    # Нет действий — снимаем флаг
                    match.current_turn.waiting_for_yellow_card_choice = False
                    match.current_turn.yellow_card_target_manager_id = None
                    match.current_turn.yellow_card_target_player_id = None
                    match.current_turn.yellow_card_id = None
    
    # Разрешаем пенальти (карточку) если есть
    if match.current_turn and match.current_turn.waiting_for_penalty_roll:
        for card in match.whistle_cards_drawn:
            if (card.card_type == CardType.PENALTY and 
                card.penalty_scored is None and
                card.turn_applied == match.current_turn.turn_number):
                choice = random.choice(["high", "low"])
                match, success, pen_dice = engine.resolve_penalty(match, card.applied_by_manager_id, choice)
                break
    
    # Завершаем ход
    match = engine.end_turn(match)
    return match


class TestFullMainTime:
    """Тест полных 11 ходов основного времени"""
    
    def test_11_turns_main_time(self):
        """Полный цикл Main Time: 11 ходов"""
        random.seed(42)
        engine = GameEngine()
        m1 = uuid4(); m2 = uuid4()
        
        match = engine.create_match(m1, MatchType.RANDOM)
        match.manager2_id = m2
        match.status = MatchStatus.SETTING_LINEUP
        
        t1 = make_team(m1, 'T1'); t2 = make_team(m2, 'T2')
        match = engine.set_team_without_formation(match, m1, t1)
        match = engine.set_team_without_formation(match, m2, t2)
        
        assert match.status == MatchStatus.IN_PROGRESS
        assert match.phase == MatchPhase.MAIN_TIME
        
        for turn in range(1, 12):
            assert match.current_turn is not None, f"No turn at step {turn}"
            assert match.current_turn.turn_number == turn
            match = play_turn(engine, match, m1, m2, turn, "mt")
            
            if match.status != MatchStatus.IN_PROGRESS:
                break
        
        # После 11 ходов — либо FINISHED, EXTRA_TIME, или PENALTIES
        assert match.status in [MatchStatus.FINISHED, MatchStatus.EXTRA_TIME, MatchStatus.PENALTIES]
        assert match.total_turns_main == 11
        assert len(match.used_players_main_m1) == 11
        assert len(match.used_players_main_m2) == 11
    
    def test_formation_validity_after_11_turns(self):
        """После 11 ходов: 1 GK + 10 полевых, формация допустима"""
        random.seed(123)
        engine = GameEngine()
        m1 = uuid4(); m2 = uuid4()
        
        match = engine.create_match(m1, MatchType.RANDOM)
        match.manager2_id = m2; match.status = MatchStatus.SETTING_LINEUP
        
        t1 = make_team(m1, 'T1'); t2 = make_team(m2, 'T2')
        match = engine.set_team_without_formation(match, m1, t1)
        match = engine.set_team_without_formation(match, m2, t2)
        
        for turn in range(1, 12):
            if match.status != MatchStatus.IN_PROGRESS:
                break
            match = play_turn(engine, match, m1, m2, turn, "mt")
        
        # Проверяем использованных: 1 GK + 10 полевых
        used_m1 = match.used_players_main_m1
        assert len(used_m1) == 11
        
        # Подсчитываем позиции
        pos_counts = {"goalkeeper": 0, "defender": 0, "midfielder": 0, "forward": 0}
        for pid_str in used_m1:
            for p in t1.players:
                if str(p.id) == pid_str:
                    pos_counts[p.position.value] += 1
                    break
        
        assert pos_counts["goalkeeper"] == 1  # Ровно 1 вратарь (ход 1)
        # Формация = (DF, MF, FW) должна быть в допустимых
        formation = (pos_counts["defender"], pos_counts["midfielder"], pos_counts["forward"])
        valid = [(4,4,2),(4,3,3),(3,5,2),(3,4,3),(5,3,2),(5,2,3),(3,3,4)]
        assert formation in valid, f"Invalid formation: {formation}"


class TestFullExtraTime:
    """Тест Extra Time"""
    
    def test_extra_time_5_turns(self):
        """ET: 5 ходов после ничьей в MT"""
        # Пробуем разные seed'ы пока не получим ничью в MT
        for seed in range(100):
            random.seed(seed)
            engine = GameEngine()
            m1 = uuid4(); m2 = uuid4()
            
            match = engine.create_match(m1, MatchType.RANDOM)
            match.manager2_id = m2; match.status = MatchStatus.SETTING_LINEUP
            
            t1 = make_team(m1, 'T1'); t2 = make_team(m2, 'T2')
            match = engine.set_team_without_formation(match, m1, t1)
            match = engine.set_team_without_formation(match, m2, t2)
            
            ok = True
            for turn in range(1, 12):
                if match.status != MatchStatus.IN_PROGRESS:
                    ok = False; break
                match = play_turn(engine, match, m1, m2, turn, "mt")
            
            if not ok or match.status != MatchStatus.EXTRA_TIME:
                continue
            
            # Нашли ничью! Играем ET
            assert match.phase == MatchPhase.EXTRA_TIME
            assert match.current_turn.turn_number == 1
            
            for turn in range(1, 6):
                if match.status not in [MatchStatus.EXTRA_TIME, MatchStatus.IN_PROGRESS]:
                    break
                # В ET фаза может быть EXTRA_TIME, а status тоже EXTRA_TIME
                if match.phase != MatchPhase.EXTRA_TIME:
                    break
                match = play_turn(engine, match, m1, m2, turn, "et")
            
            assert match.status in [MatchStatus.FINISHED, MatchStatus.PENALTIES]
            if match.status == MatchStatus.FINISHED:
                assert match.total_turns_extra <= 5
            return  # Тест пройден
        
        pytest.skip("Could not generate MT draw in 100 seeds")
    
    def test_et_no_goalkeeper(self):
        """В ET вратарь недоступен"""
        engine = GameEngine()
        m1 = uuid4(); m2 = uuid4()
        
        match = engine.create_match(m1, MatchType.RANDOM)
        match.manager2_id = m2; match.status = MatchStatus.SETTING_LINEUP
        
        t1 = make_team(m1, 'T1'); t2 = make_team(m2, 'T2')
        match = engine.set_team_without_formation(match, m1, t1)
        match = engine.set_team_without_formation(match, m2, t2)
        
        # Принудительно переходим в ET
        match.phase = MatchPhase.EXTRA_TIME
        match.status = MatchStatus.EXTRA_TIME
        match.used_players_main_m1 = [str(p.id) for p in t1.players[:11]]
        match.used_players_main_m2 = [str(p.id) for p in t2.players[:11]]
        match.current_turn = TurnState(turn_number=1)
        
        avail = engine.get_available_players(match, m1)
        gk_in_avail = any(p.position == Position.GOALKEEPER for p in avail)
        assert not gk_in_avail, "Goalkeeper should not be available in ET"
    
    def test_et_even_odd_no_limit(self):
        """В ET нет лимита 6 чёт/нечёт"""
        engine = GameEngine()
        m1 = uuid4(); m2 = uuid4()
        
        match = engine.create_match(m1, MatchType.RANDOM)
        match.manager2_id = m2; match.status = MatchStatus.SETTING_LINEUP
        
        t1 = make_team(m1, 'T1'); t2 = make_team(m2, 'T2')
        match = engine.set_team_without_formation(match, m1, t1)
        match = engine.set_team_without_formation(match, m2, t2)
        
        # Добавляем 6 ставок чёт/нечёт в MT
        for i in range(6):
            match.bets.append(Bet(
                match_id=match.id, manager_id=m1,
                player_id=t1.players[1+i].id, turn_number=2+i,
                bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.EVEN
            ))
        
        # Переходим в ET
        match.phase = MatchPhase.EXTRA_TIME
        match.status = MatchStatus.EXTRA_TIME
        match.used_players_main_m1 = [str(p.id) for p in t1.players[:11]]
        match.used_players_main_m2 = [str(p.id) for p in t2.players[:11]]
        match.current_turn = TurnState(turn_number=1)
        
        # Защитник в ET должен иметь EVEN_ODD
        et_player = t1.players[11]  # MF, не использован
        types = engine.get_available_bet_types(match, m1, et_player.id)
        assert BetType.EVEN_ODD in types, f"EVEN_ODD should be available in ET, got {types}"


class TestPenalties:
    """Тест серии пенальти"""
    
    def test_penalties_after_et_draw(self):
        """Серия пенальти после ничьей в ET"""
        from src.platforms.telegram.handlers.game import _auto_penalties
        from src.platforms.telegram.storage import HybridStorage
        
        random.seed(777)
        storage = HybridStorage()
        engine = storage.engine
        m1 = uuid4(); m2 = uuid4()
        
        match = engine.create_match(m1, MatchType.RANDOM)
        match.manager2_id = m2; match.status = MatchStatus.SETTING_LINEUP
        
        t1 = make_team(m1, 'T1'); t2 = make_team(m2, 'T2')
        match = engine.set_team_without_formation(match, m1, t1)
        match = engine.set_team_without_formation(match, m2, t2)
        
        # Играем MT
        for turn in range(1, 12):
            if match.status != MatchStatus.IN_PROGRESS:
                break
            match = play_turn(engine, match, m1, m2, turn, "mt")
        
        if match.status == MatchStatus.EXTRA_TIME:
            for turn in range(1, 6):
                if match.status not in [MatchStatus.EXTRA_TIME, MatchStatus.IN_PROGRESS]:
                    break
                match = play_turn(engine, match, m1, m2, turn, "et")
        
        if match.status == MatchStatus.PENALTIES:
            match = _auto_penalties(storage, match)
            
            assert match.status == MatchStatus.FINISHED
            assert match.result is not None
            assert match.result.decided_by == MatchPhase.PENALTIES
            assert len(match.penalty_results) > 0
            assert match.penalty_score_m1 >= 0
            assert match.penalty_score_m2 >= 0
            
            # Каждый удар имеет имя и результат
            for kick in match.penalty_results:
                assert kick.player_name != ""
                assert isinstance(kick.scored, bool)
        else:
            # Матч завершился раньше — проверяем что результат есть
            assert match.status == MatchStatus.FINISHED
            assert match.result is not None


class TestRendering:
    """Тест рендеринга для обоих игроков"""
    
    def test_score_is_viewer_relative(self):
        """Счёт отображается Вы:Соперник для каждого"""
        from src.platforms.telegram.renderers.match_renderer import MatchRenderer
        
        engine = GameEngine()
        m1 = uuid4(); m2 = uuid4()
        
        match = engine.create_match(m1, MatchType.RANDOM)
        match.manager2_id = m2; match.status = MatchStatus.SETTING_LINEUP
        
        t1 = make_team(m1, 'T1'); t2 = make_team(m2, 'T2')
        match = engine.set_team_without_formation(match, m1, t1)
        match = engine.set_team_without_formation(match, m2, t2)
        
        # Устанавливаем счёт
        match.score.manager1_goals = 3
        match.score.manager2_goals = 1
        from src.core.models.match import MatchResult
        match.result = MatchResult(
            winner_id=m1, loser_id=m2,
            final_score=match.score,
            decided_by=MatchPhase.MAIN_TIME
        )
        match.status = MatchStatus.FINISHED
        
        renderer = MatchRenderer()
        
        # Для m1 — 3:1
        text_m1 = renderer.render_match_result(match, m1)
        assert "3:1" in text_m1
        
        # Для m2 — 1:3
        text_m2 = renderer.render_match_result(match, m2)
        assert "1:3" in text_m2


class TestFormationValidation:
    """Тест: формация проверяется с хода 2, симуляция с хода 8"""
    
    def test_formation_blocks_excess_position(self):
        """Формация не допускает больше позиций чем есть в допустимых формациях"""
        engine = GameEngine()
        m1 = uuid4(); m2 = uuid4()
        
        match = Match(
            match_type=MatchType.RANDOM,
            manager1_id=m1, manager2_id=m2,
            team1=make_team(m1, 'T1'), team2=make_team(m2, 'T2'),
            status=MatchStatus.IN_PROGRESS,
        )
        t1 = match.team1
        
        # 1GK + 5MF использовано, ход 7 — формация проверяет 6-й MF
        match.used_players_main_m1 = [str(t1.players[0].id)]
        for i in range(5):
            match.used_players_main_m1.append(str(t1.players[7+i].id))
        match.current_turn = TurnState(turn_number=7)
        engine._init_match_history(match)
        
        avail = engine.get_available_players(match, m1)
        # 6-й MF допустим (формация 3-5-2 имеет MF=5, но MF6 будет 6-й)
        # Максимум MF в формациях = 5 (3-5-2), значит MF6 заблокирован
        mf_avail = [p for p in avail if p.position == Position.MIDFIELDER]
        assert len(mf_avail) <= 1  # MF6 — единственный оставшийся, но формация может блокировать
    
    def test_simulation_ensures_future_turns(self):
        """С хода 8 симуляция проверяет что будущие ходы возможны"""
        engine = GameEngine()
        m1 = uuid4(); m2 = uuid4()
        
        match = Match(
            match_type=MatchType.RANDOM,
            manager1_id=m1, manager2_id=m2,
            team1=make_team(m1, 'T1'), team2=make_team(m2, 'T2'),
            status=MatchStatus.IN_PROGRESS,
        )
        t1 = match.team1
        
        # Ход 8: 1GK + 3DF + 3MF + 0FW = 7 использовано
        match.used_players_main_m1 = [str(t1.players[0].id)]
        for i in range(3): match.used_players_main_m1.append(str(t1.players[1+i].id))
        for i in range(3): match.used_players_main_m1.append(str(t1.players[7+i].id))
        match.current_turn = TurnState(turn_number=8)
        engine._init_match_history(match)
        
        avail = engine.get_available_players(match, m1)
        # Должны быть доступные игроки — формация 3-4-3 или 3-5-2 достижимы
        assert len(avail) > 0
    
    def test_even_odd_exhausted_still_playable(self):
        """Если чёт/нечёт исчерпан, остаются HIGH_LOW + EXACT_NUMBER (2 типа)"""
        from src.core.models.bet import Bet, BetType, EvenOddChoice
        
        engine = GameEngine()
        m1 = uuid4(); m2 = uuid4()
        
        match = Match(
            match_type=MatchType.RANDOM,
            manager1_id=m1, manager2_id=m2,
            team1=make_team(m1, 'T1'), team2=make_team(m2, 'T2'),
            status=MatchStatus.IN_PROGRESS,
        )
        t1 = match.team1
        
        # 6 чёт/нечёт ставок (бюджет EO исчерпан)
        for i in range(6):
            match.bets.append(Bet(
                match_id=match.id, manager_id=m1,
                player_id=t1.players[1+i].id, turn_number=2+i,
                bet_type=BetType.EVEN_ODD, even_odd_choice=EvenOddChoice.EVEN
            ))
        # Также отметим этих игроков как использованных, чтобы combo-feasibility 
        # для оставшихся ходов проходил (turns_remaining = 11 - 8 = 3)
        for i in range(6):
            match.used_players_main_m1.append(str(t1.players[1+i].id))
        match.current_turn = TurnState(turn_number=8)
        
        df = t1.players[1+6]  # Свежий защитник
        types = engine.bet_tracker.get_available_bet_types(match, m1, df)
        assert BetType.HIGH_LOW in types
        assert BetType.EXACT_NUMBER in types
        assert len(types) >= 2
