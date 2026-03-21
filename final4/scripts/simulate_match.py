#!/usr/bin/env python3
"""
Скрипт симуляции матча без платформы.

Демонстрирует работу Core модуля без Telegram/VK/Discord.
Теперь с правильными правилами доступности игроков!
"""

import sys
import os
import random
from uuid import uuid4

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.engine.game_engine import GameEngine, BOT_USER_ID
from src.core.models.match import MatchType, MatchStatus
from src.core.models.team import Team, Formation, FORMATION_STRUCTURE
from src.core.models.player import Player, Position
from src.core.models.bet import Bet, BetType, EvenOddChoice, HighLowChoice


def create_team(manager_id, name: str) -> Team:
    """Создать тестовую команду"""
    players = []
    number = 1
    
    # 2 вратаря
    for i in range(2):
        players.append(Player(
            name=f"Вратарь {i+1}",
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
    
    # 5 полузащитников
    for i in range(5):
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


def simulate_turn(engine: GameEngine, match, manager_id, team: Team, turn_num: int):
    """Симулировать один ход с учётом правил доступности"""
    
    # Получаем доступных игроков через новый метод
    available_players = engine.get_available_players(match, manager_id)
    
    if not available_players:
        print(f"  ⚠️ Нет доступных игроков!")
        # Бросаем кубик без ставок
        match, dice_value, won_bets = engine.roll_dice(match, manager_id)
        match = engine.end_turn(match, manager_id)
        return match, dice_value, 0
    
    print(f"  Доступных игроков: {len(available_players)}")
    
    # Выбираем одного игрока для ставки
    player = random.choice(available_players)
    
    # Получаем доступные типы ставок
    available_types = engine.get_available_bet_types(match, manager_id, player.id)
    
    if not available_types:
        print(f"  ⚠️ Нет доступных типов ставок для {player.name}")
        match, dice_value, won_bets = engine.roll_dice(match, manager_id)
        match = engine.end_turn(match, manager_id)
        return match, dice_value, 0
    
    bet_type = random.choice(available_types)
    
    # Подготавливаем параметры ставки
    bet_kwargs = {
        "match_id": match.id,
        "manager_id": manager_id,
        "player_id": player.id,
        "turn_number": turn_num,
        "bet_type": bet_type
    }
    
    # Устанавливаем значение ставки
    if bet_type == BetType.EVEN_ODD:
        bet_kwargs["even_odd_choice"] = random.choice([EvenOddChoice.EVEN, EvenOddChoice.ODD])
    elif bet_type == BetType.HIGH_LOW:
        bet_kwargs["high_low_choice"] = random.choice([HighLowChoice.HIGH, HighLowChoice.LOW])
    elif bet_type == BetType.EXACT_NUMBER:
        bet_kwargs["exact_number"] = random.randint(1, 6)
    
    try:
        bet = Bet(**bet_kwargs)
        match, _ = engine.place_bet(match, manager_id, player.id, bet)
        print(f"  Ставка: {player.name} ({player.position.value}) -> {bet_type.value}")
    except ValueError as e:
        print(f"  ⚠️ Ошибка ставки: {e}")
    
    # Бросаем кубик
    match, dice_value, won_bets = engine.roll_dice(match, manager_id)
    
    # Берём карточку если выиграли
    if won_bets:
        match, card = engine.draw_whistle_card(match, manager_id)
        if card and not card.requires_target():
            match = engine.apply_whistle_card(match, manager_id, card.id)
    
    # Завершаем ход (это пометит игрока как использованного)
    match = engine.end_turn(match, manager_id)
    
    return match, dice_value, len(won_bets)


def main():
    print("=" * 60)
    print("⚽ Final 4 - Симуляция матча (с правилами доступности)")
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
    
    # Симулируем матч
    print("\n" + "=" * 60)
    print("🎮 НАЧАЛО МАТЧА")
    print("=" * 60)
    
    turn_count = 0
    
    while match.status == MatchStatus.IN_PROGRESS:
        turn_count += 1
        
        if not match.current_turn:
            break
        
        current_manager = match.current_turn.current_manager_id
        is_manager1 = current_manager == manager1_id
        turn_num = match.current_turn.turn_number
        
        team_name = "Спартак" if is_manager1 else "ЦСКА"
        team = match.team1 if is_manager1 else match.team2
        
        print(f"\n--- Ход {turn_count} (внутренний #{turn_num}): {team_name} ---")
        
        match, dice, won = simulate_turn(engine, match, current_manager, team, turn_num)
        
        print(f"  🎲 Кубик: {dice} | Выиграно: {won}")
        
        # Показываем использованных игроков
        used = match.get_used_players(current_manager)
        print(f"  📝 Использовано игроков: {len(used)}")
        
        # Проверяем завершение матча
        if match.status != MatchStatus.IN_PROGRESS:
            break
        
        if turn_count > 30:  # Защита от бесконечного цикла
            print("\n⚠️ Превышен лимит ходов")
            break
    
    # Результаты
    print("\n" + "=" * 60)
    print("🏁 МАТЧ ЗАВЕРШЁН")
    print("=" * 60)
    
    print_team_stats(match.team1, "🔵")
    print_team_stats(match.team2, "🔴")
    
    print(f"\n📊 Счёт: {match.score.manager1_goals}:{match.score.manager2_goals}")
    
    # Показываем использованных игроков
    print(f"\n📋 Использовано игроков:")
    print(f"  Спартак: {len(match.get_used_players(manager1_id))}")
    print(f"  ЦСКА: {len(match.get_used_players(manager2_id))}")
    
    if match.result:
        winner_name = "Спартак" if match.result.winner_id == manager1_id else "ЦСКА"
        print(f"\n🏆 Победитель: {winner_name}")
        print(f"📋 Решено: {match.result.decided_by.value}")
    else:
        print("\n🤝 Ничья или матч не завершён")


if __name__ == "__main__":
    main()
