#!/usr/bin/env python3
"""
Скрипт симуляции матча без платформы.

ОБНОВЛЕНО: Теперь с правильной логикой одновременных ставок!
- Оба менеджера делают ставки
- Один бросок кубика для обоих
- Автоматическое вытягивание карточек при выигрыше
- 2 ставки должны быть РАЗНЫХ типов
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


def make_bets_for_manager(engine: GameEngine, match, manager_id, team: Team, turn_num: int) -> bool:
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
    
    # Сколько ставок нужно (1 для вратаря, 2 для полевых)
    required_bets = 1 if turn_num == 1 else 2
    
    print(f"    Игрок: {player.name} ({player.position.value})")
    print(f"    Доступные типы: {[t.value for t in available_types]}")
    
    # Делаем ставки
    used_types = []
    for i in range(min(required_bets, len(available_types))):
        # Выбираем тип, который ещё не использовали
        remaining_types = [t for t in available_types if t not in used_types]
        if not remaining_types:
            break
        
        bet_type = random.choice(remaining_types)
        used_types.append(bet_type)
        
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
            print(f"    Ставка {i+1}: {bet_type.value} -> {bet.get_display_value()}")
        except ValueError as e:
            print(f"    ⚠️ Ошибка ставки: {e}")
            return False
    
    # Подтверждаем завершение ставок
    try:
        engine.confirm_bets(match, manager_id)
        print(f"    ✅ Ставки подтверждены")
    except ValueError as e:
        print(f"    ⚠️ Ошибка подтверждения: {e}")
        return False
    
    return True


def simulate_turn(engine: GameEngine, match, manager1_id, manager2_id, team1: Team, team2: Team, turn_num: int):
    """
    Симулировать один ход (оба менеджера ставят, один бросок).
    """
    print(f"\n{'='*50}")
    print(f"ХОД {turn_num}")
    print(f"{'='*50}")
    
    # Менеджер 1 делает ставки
    print(f"\n  📋 Спартак делает ставки:")
    success1 = make_bets_for_manager(engine, match, manager1_id, team1, turn_num)
    
    # Менеджер 2 делает ставки
    print(f"\n  📋 ЦСКА делает ставки:")
    success2 = make_bets_for_manager(engine, match, manager2_id, team2, turn_num)
    
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
    
    # Показываем вытянутые карточки (автоматически)
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


def main():
    print("=" * 60)
    print("⚽ Final 4 - Симуляция матча")
    print("   (Одновременные ставки + один бросок кубика)")
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
    max_turns = 11  # Основное время
    
    while match.status == MatchStatus.IN_PROGRESS and turn_count < max_turns:
        turn_count += 1
        
        if not match.current_turn:
            break
        
        turn_num = match.current_turn.turn_number
        
        match = simulate_turn(
            engine, match, 
            manager1_id, manager2_id, 
            match.team1, match.team2, 
            turn_num
        )
        
        # Проверяем завершение матча
        if match.status != MatchStatus.IN_PROGRESS:
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
    
    # Показываем вытянутые карточки
    print(f"\n🃏 Вытянуто карточек: {len(match.whistle_cards_drawn)}")
    
    if match.result:
        winner_name = "Спартак" if match.result.winner_id == manager1_id else "ЦСКА"
        print(f"\n🏆 Победитель: {winner_name}")
        print(f"📋 Решено: {match.result.decided_by.value}")
    else:
        print("\n🤝 Ничья или матч не завершён")


if __name__ == "__main__":
    main()
