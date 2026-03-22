#!/usr/bin/env python3
"""
Скрипт симуляции матча без платформы.

ОБНОВЛЕНО: Полный цикл Main Time -> Extra Time -> Penalties
- Оба менеджера делают ставки одновременно
- Один бросок кубика для обоих
- Автоматическое вытягивание карточек при выигрыше
- Статистика через MatchHistory
- Автоматический расчёт пенальти
"""

import sys
import os
import random
from uuid import uuid4, UUID
from typing import Optional

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.engine.game_engine import GameEngine, BOT_USER_ID
from src.core.models.match import MatchType, MatchStatus, MatchPhase
from src.core.models.team import Team, Formation, FORMATION_STRUCTURE
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice


def create_team(manager_id, name: str) -> Team:
    """
    Создать команду с 16 игроками по правилам:
    - 1 вратарь
    - 5 защитников
    - 6 полузащитников
    - 4 форварда
    """
    players = []
    number = 1
    
    # 1 вратарь
    players.append(Player(
        name=f"Вратарь",
        position=Position.GOALKEEPER,
        number=number
    ))
    number += 1
    
    # 5 защитников
    for i in range(5):
        players.append(Player(
            name=f"Защитник {i+1}",
            position=Position.DEFENDER,
            number=number
        ))
        number += 1
    
    # 6 полузащитников
    for i in range(6):
        players.append(Player(
            name=f"Полузащитник {i+1}",
            position=Position.MIDFIELDER,
            number=number
        ))
        number += 1
    
    # 4 нападающих
    for i in range(4):
        players.append(Player(
            name=f"Нападающий {i+1}",
            position=Position.FORWARD,
            number=number
        ))
        number += 1
    
    return Team(manager_id=manager_id, name=name, players=players)


def select_lineup(team: Team, formation: Formation) -> list:
    """Автоматически выбрать состав для формации"""
    structure = FORMATION_STRUCTURE[formation]
    selected = []
    
    for pos_str, count in structure.items():
        pos = Position(pos_str)
        pos_players = team.get_players_by_position(pos)
        selected.extend(pos_players[:count])
    
    return [p.id for p in selected]


def print_team_stats(team: Team, label: str):
    """Вывести статистику команды"""
    team.calculate_stats()
    print(f"\n{label}: {team.name}")
    print(f"  Отбития: {team.stats.total_saves}")
    print(f"  Передачи: {team.stats.total_passes}")
    print(f"  Голы: {team.stats.total_goals}")


def print_match_history_stats(engine: GameEngine, match, manager1_id: UUID, manager2_id: UUID):
    """Вывести статистику из MatchHistory"""
    history = engine.get_match_history(match)
    if not history:
        print("  История не найдена")
        return
    
    # Статистика Спартака
    print(f"\n📊 СТАТИСТИКА ИЗ MatchHistory:")
    print(f"\n  🔵 Спартак:")
    total1 = history.get_total_stats(manager1_id, match.manager1_id)
    print(f"     ИТОГО: {total1['saves']} отб, {total1['passes']} перед, {total1['goals']} гол")
    
    for p in history.manager1_players.values():
        if p.turn_played is not None:
            phase = "ET" if p.phase_played == MatchPhase.EXTRA_TIME else "MT"
            print(f"     {p.player_name}: {p.saves} отб, {p.passes} перед, {p.goals} гол (ход {p.turn_played} {phase})")
            if p.history:
                for h in p.history[-3:]:  # Показываем последние 3 изменения
                    print(f"        └─ {h}")
    
    # Статистика ЦСКА
    print(f"\n  🔴 ЦСКА:")
    total2 = history.get_total_stats(manager2_id, match.manager1_id)
    print(f"     ИТОГО: {total2['saves']} отб, {total2['passes']} перед, {total2['goals']} гол")
    
    for p in history.manager2_players.values():
        if p.turn_played is not None:
            phase = "ET" if p.phase_played == MatchPhase.EXTRA_TIME else "MT"
            print(f"     {p.player_name}: {p.saves} отб, {p.passes} перед, {p.goals} гол (ход {p.turn_played} {phase})")
            if p.history:
                for h in p.history[-3:]:
                    print(f"        └─ {h}")


def make_bets_for_manager(engine: GameEngine, match, manager_id, team: Team, turn_num: int, phase: MatchPhase) -> bool:
    """
    Сделать ставки для одного менеджера.
    
    Returns:
        True если ставки успешно сделаны, False если нет доступных игроков
    """
    # Получаем доступных игроков
    available_players = engine.get_available_players(match, manager_id)
    
    if not available_players:
        print(f"    ⚠️ Нет доступных игроков!")
        return False
    
    # Выбираем одного игрока
    player = random.choice(available_players)
    
    # Получаем доступные типы ставок
    available_types = engine.get_available_bet_types(match, manager_id, player.id)
    
    if not available_types:
        print(f"    ⚠️ Нет типов ставок для {player.name}")
        return False
    
    # Сколько ставок нужно
    if phase == MatchPhase.MAIN_TIME and turn_num == 1:
        required_bets = 1  # Вратарь
    else:
        required_bets = 2  # Полевые
    
    print(f"    Игрок: {player.name} ({player.position.value})")
    print(f"    Доступные типы: {[t.value for t in available_types]}")
    
    # В Extra Time — ОБЯЗАТЕЛЬНО одна ставка на гол
    if phase == MatchPhase.EXTRA_TIME:
        # Сначала ставим на гол
        if BetType.EXACT_NUMBER in available_types:
            bet_kwargs = {
                "match_id": match.id,
                "manager_id": manager_id,
                "player_id": player.id,
                "turn_number": turn_num,
                "bet_type": BetType.EXACT_NUMBER,
                "exact_number": random.randint(1, 6)
            }
            try:
                bet = Bet(**bet_kwargs)
                match, _ = engine.place_bet(match, manager_id, player.id, bet)
                print(f"    Ставка 1: гол на {bet.exact_number}")
            except ValueError as e:
                print(f"    ⚠️ Ошибка ставки на гол: {e}")
                return False
            
            # Вторая ставка — чёт/нечёт или больше/меньше
            other_types = [t for t in available_types if t != BetType.EXACT_NUMBER]
            if other_types:
                bet_type = random.choice(other_types)
                bet_kwargs = {
                    "match_id": match.id,
                    "manager_id": manager_id,
                    "player_id": player.id,
                    "turn_number": turn_num,
                    "bet_type": bet_type
                }
                if bet_type == BetType.EVEN_ODD:
                    bet_kwargs["even_odd_choice"] = random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
                else:
                    bet_kwargs["high_low_choice"] = random.choice([HighLowChoice.HIGH, HighLowChoice.LOW])
                
                try:
                    bet = Bet(**bet_kwargs)
                    match, _ = engine.place_bet(match, manager_id, player.id, bet)
                    print(f"    Ставка 2: {bet_type.value} -> {bet.get_display_value()}")
                except ValueError as e:
                    print(f"    ⚠️ Ошибка второй ставки: {e}")
        
        # Подтверждаем ставки
        try:
            engine.confirm_bets(match, manager_id)
            print(f"    ✅ Ставки подтверждены")
        except ValueError as e:
            print(f"    ⚠️ Ошибка подтверждения: {e}")
            return False
        
        return True
    
    # Основное время — стандартная логика
    used_types = []
    for i in range(min(required_bets, len(available_types))):
        remaining_types = [t for t in available_types if t not in used_types]
        if not remaining_types:
            break
        
        bet_type = random.choice(remaining_types)
        used_types.append(bet_type)
        
        bet_kwargs = {
            "match_id": match.id,
            "manager_id": manager_id,
            "player_id": player.id,
            "turn_number": turn_num,
            "bet_type": bet_type
        }
        
        if bet_type == BetType.EVEN_ODD:
            bet_kwargs["even_odd_choice"] = random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
        elif bet_type == BetType.HIGH_LOW:
            bet_kwargs["high_low_choice"] = random.choice([HighLowChoice.HIGH, HighLowChoice.LOW])
        elif bet_type == BetType.EXACT_NUMBER:
            bet_kwargs["exact_number"] = random.randint(1, 6)
        
        try:
            bet = Bet(**bet_kwargs)
            match, _ = engine.place_bet(match, manager_id, player.id, bet)
            print(f"    Ставка {i+1}: {bet_type.value} -> {bet.get_display_value()}")
        except ValueError as e:
            print(f"    ⚠️ Ошибка ставки: {e}")
            return False
    
    try:
        engine.confirm_bets(match, manager_id)
        print(f"    ✅ Ставки подтверждены")
    except ValueError as e:
        print(f"    ⚠️ Ошибка подтверждения: {e}")
        return False
    
    return True


def simulate_turn(engine: GameEngine, match, manager1_id, manager2_id, turn_num: int, phase: MatchPhase):
    """
    Симулировать один ход (оба менеджера ставят, один бросок).
    """
    phase_name = "Extra Time" if phase == MatchPhase.EXTRA_TIME else "Main Time"
    print(f"\n{'='*50}")
    print(f"ХОД {turn_num} ({phase_name})")
    print(f"{'='*50}")
    
    # Менеджер 1 делает ставки
    print(f"\n  📋 Спартак делает ставки:")
    success1 = make_bets_for_manager(engine, match, manager1_id, match.team1, turn_num, phase)
    
    # Менеджер 2 делает ставки
    print(f"\n  📋 ЦСКА делает ставки:")
    success2 = make_bets_for_manager(engine, match, manager2_id, match.team2, turn_num, phase)
    
    # Проверяем, можно ли бросить кубик
    can_roll, reason = engine.can_roll_dice(match)
    if not can_roll:
        print(f"\n  ⚠️ Нельзя бросить кубик: {reason}")
        return match
    
    # Бросаем кубик — ОДИН для обоих!
    print(f"\n  🎲 Бросок кубика...")
    match, dice_value, won_bets = engine.roll_dice(match)
    
    print(f"  🎲 Результат: {dice_value}")
    
    # Показываем результаты для каждого менеджера
    for manager_id, bets in won_bets.items():
        team_name = "Спартак" if manager_id == manager1_id else "ЦСКА"
        if bets:
            print(f"  ✅ {team_name} выиграл {len(bets)} ставок!")
            for bet in bets:
                print(f"      - {bet.bet_type.value}: {bet.get_display_value()}")
        else:
            print(f"  ❌ {team_name} проиграл все ставки")
    
    # Показываем вытянутые карточки
    if match.current_turn.manager1_card_id:
        card = next((c for c in match.whistle_cards_drawn 
                    if c.id == match.current_turn.manager1_card_id), None)
        if card:
            print(f"  🃏 Спартак получил карточку: {card.card_type.value}")
    
    if match.current_turn.manager2_card_id:
        card = next((c for c in match.whistle_cards_drawn 
                    if c.id == match.current_turn.manager2_card_id), None)
        if card:
            print(f"  🃏 ЦСКА получил карточку: {card.card_type.value}")
    
    # Завершаем ход
    match = engine.end_turn(match)
    
    # Показываем использованных игроков
    print(f"\n  📝 Использовано игроков:")
    print(f"      Спартак: {len(match.get_used_players(manager1_id))}")
    print(f"      ЦСКА: {len(match.get_used_players(manager2_id))}")
    
    return match


def simulate_penalties(engine: GameEngine, match, manager1_id: UUID, manager2_id: UUID):
    """
    Симулировать серию пенальти.
    
    Правила:
    - Порядок: Extra Time (обратный) -> Main Time (обратный)
    - Игрок с передачей -> ГОЛ
    - Игрок без передачи -> промах
    """
    print(f"\n{'='*60}")
    print(f"⚽ СЕРИЯ ПЕНАЛЬТИ")
    print(f"{'='*60}")
    
    history = engine.get_match_history(match)
    if not history:
        print("  ⚠️ История матча не найдена!")
        return match
    
    # Получаем игроков в порядке для пенальти
    players1 = history.get_all_players_ordered_for_penalties(manager1_id, match.manager1_id)
    players2 = history.get_all_players_ordered_for_penalties(manager2_id, match.manager1_id)
    
    print(f"\n  📋 Порядок пробития:")
    print(f"    Спартак: {[p.player_name for p in players1[:5]]}")
    print(f"    ЦСКА: {[p.player_name for p in players2[:5]]}")
    
    goals1 = 0
    goals2 = 0
    
    # Основная серия — 5 ударов от каждого
    max_kicks = min(5, len(players1), len(players2))
    
    for i in range(max_kicks):
        print(f"\n  Удар {i+1}:")
        
        # Спартак
        p1 = players1[i]
        if p1.passes > 0:
            goals1 += 1
            print(f"    🔵 {p1.player_name}: ГОЛ! ({p1.passes} передач)")
        else:
            print(f"    🔵 {p1.player_name}: промах (0 передач)")
        
        # ЦСКА
        p2 = players2[i]
        if p2.passes > 0:
            goals2 += 1
            print(f"    🔴 {p2.player_name}: ГОЛ! ({p2.passes} передач)")
        else:
            print(f"    🔴 {p2.player_name}: промах (0 передач)")
        
        print(f"    Счёт пенальти: {goals1}:{goals2}")
        
        # Досрочная проверка
        remaining = max_kicks - i - 1
        if goals1 > goals2 + remaining:
            print(f"\n  🏆 Спартак выигрывает досрочно!")
            break
        if goals2 > goals1 + remaining:
            print(f"\n  🏆 ЦСКА выигрывает досрочно!")
            break
    
    print(f"\n  📊 Итого пенальти: {goals1}:{goals2}")
    
    # Определяем победителя
    if goals1 > goals2:
        winner_id = manager1_id
        winner_name = "Спартак"
    elif goals2 > goals1:
        winner_id = manager2_id
        winner_name = "ЦСКА"
    else:
        # Жребий
        winner_id = random.choice([manager1_id, manager2_id])
        winner_name = "Спартак" if winner_id == manager1_id else "ЦСКА"
        print(f"\n  🎲 Ничья! Победитель по жребию: {winner_name}")
    
    # Обновляем счёт
    match.score.manager1_goals += goals1
    match.score.manager2_goals += goals2
    
    # Финализируем матч
    match = engine.finish_penalty_shootout(match, winner_id)
    
    return match


def main():
    print("=" * 60)
    print("⚽ Final 4 - Полная симуляция матча")
    print("   Main Time -> Extra Time -> Penalties")
    print("=" * 60)
    
    engine = GameEngine()
    
    # Создаём игроков
    manager1_id = uuid4()
    manager2_id = uuid4()
    
    print(f"\n👤 Менеджер 1: Спартак")
    print(f"👤 Менеджер 2: ЦСКА")
    
    # Создаём матч
    match = engine.create_match(manager1_id, MatchType.RANDOM)
    match = engine.join_match(match, manager2_id)
    
    print(f"\n📋 Матч создан")
    
    # Создаём команды
    team1 = create_team(manager1_id, "Спартак")
    team2 = create_team(manager2_id, "ЦСКА")
    
    # Выбираем формации и составы
    formation = Formation.F_4_4_2
    
    lineup1 = select_lineup(team1, formation)
    lineup2 = select_lineup(team2, formation)
    
    match = engine.set_team_lineup(match, manager1_id, team1, formation, lineup1)
    match = engine.set_team_lineup(match, manager2_id, team2, formation, lineup2)
    
    print(f"\n✅ Составы выбраны (формация: {formation.value})")
    print(f"📊 Статус: {match.status.value}")
    
    # ===================== ОСНОВНОЕ ВРЕМЯ =====================
    print("\n" + "=" * 60)
    print("🎮 ОСНОВНОЕ ВРЕМЯ (11 ходов)")
    print("=" * 60)
    
    while match.phase == MatchPhase.MAIN_TIME and match.status == MatchStatus.IN_PROGRESS:
        if not match.current_turn:
            break
        
        turn_num = match.current_turn.turn_number
        match = simulate_turn(engine, match, manager1_id, manager2_id, turn_num, MatchPhase.MAIN_TIME)
        
        if match.status != MatchStatus.IN_PROGRESS:
            break
    
    # Промежуточная статистика
    print_match_history_stats(engine, match, manager1_id, manager2_id)
    
    # Счёт после основного времени
    print(f"\n📊 Счёт после основного времени: {match.score.manager1_goals}:{match.score.manager2_goals}")
    
    # ===================== ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ =====================
    if match.phase == MatchPhase.EXTRA_TIME:
        print("\n" + "=" * 60)
        print("⏱️ ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ (5 ходов)")
        print("   (Обязательная ставка на гол для каждого игрока)")
        print("=" * 60)
        
        while match.phase == MatchPhase.EXTRA_TIME and match.status == MatchStatus.EXTRA_TIME:
            if not match.current_turn:
                break
            
            turn_num = match.current_turn.turn_number
            match = simulate_turn(engine, match, manager1_id, manager2_id, turn_num, MatchPhase.EXTRA_TIME)
            
            if match.status not in [MatchStatus.EXTRA_TIME, MatchStatus.IN_PROGRESS]:
                break
        
        # Статистика после Extra Time
        print_match_history_stats(engine, match, manager1_id, manager2_id)
        print(f"\n📊 Счёт после дополнительного времени: {match.score.manager1_goals}:{match.score.manager2_goals}")
    
    # ===================== ПЕНАЛЬТИ =====================
    if match.phase == MatchPhase.PENALTIES:
        match = simulate_penalties(engine, match, manager1_id, manager2_id)
    
    # ===================== РЕЗУЛЬТАТЫ =====================
    print("\n" + "=" * 60)
    print("🏁 МАТЧ ЗАВЕРШЁН")
    print("=" * 60)
    
    print_team_stats(match.team1, "🔵")
    print_team_stats(match.team2, "🔴")
    
    print(f"\n📊 Финальный счёт: {match.score.manager1_goals}:{match.score.manager2_goals}")
    
    # Использованные игроки
    print(f"\n📋 Использовано игроков:")
    print(f"  Спартак: {len(match.get_used_players(manager1_id))}")
    print(f"  ЦСКА: {len(match.get_used_players(manager2_id))}")
    
    # Карточки
    print(f"\n🃏 Вытянуто карточек: {len(match.whistle_cards_drawn)}")
    
    if match.result:
        winner_name = "Спартак" if match.result.winner_id == manager1_id else "ЦСКА"
        print(f"\n🏆 Победитель: {winner_name}")
        print(f"📋 Решено: {match.result.decided_by.value}")
        if match.result.decided_by_lottery:
            print("   (по жребию)")
    else:
        print("\n🤝 Ничья или матч не завершён")


if __name__ == "__main__":
    main()
