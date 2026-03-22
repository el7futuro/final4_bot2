# src/core/engine/whistle_deck.py
"""Колода карточек Свисток"""

from uuid import UUID, uuid4
from typing import List, Optional
import random

from ..models.whistle_card import (
    WhistleCard, CardType, CardEffect, CardTarget,
    CARD_DISTRIBUTION, CARD_TARGETS
)
from ..models.match import Match
from ..models.player import Player


class WhistleDeck:
    """Управление колодой карточек Свисток"""
    
    @staticmethod
    def create_deck() -> List[WhistleCard]:
        """Создать и перемешать колоду (40 карточек)"""
        deck = []
        for card_type, count in CARD_DISTRIBUTION.items():
            for _ in range(count):
                deck.append(WhistleCard(id=uuid4(), card_type=card_type))
        random.shuffle(deck)
        return deck
    
    @staticmethod
    def draw_card(deck: List[WhistleCard]) -> Optional[WhistleCard]:
        """Взять карточку из колоды"""
        if not deck:
            return None
        return deck.pop(0)
    
    @staticmethod
    def get_card_effect(
        card: WhistleCard,
        match: Match,
        manager_id: UUID,
        target_player_id: Optional[UUID] = None
    ) -> CardEffect:
        """
        Определить эффект карточки.
        
        ВАЖНО: Все карточки применяются только к игрокам ТЕКУЩЕГО хода!
        """
        effect = CardEffect(card_id=card.id, card_type=card.card_type)
        current_turn = match.current_turn.turn_number if match.current_turn else 0
        
        # === ПОЗИТИВНЫЕ ДЛЯ СВОЕГО ИГРОКА ===
        if card.card_type == CardType.HAT_TRICK:
            effect.target_player_id = target_player_id
            effect.goals_added = 3
        
        elif card.card_type == CardType.DOUBLE:
            effect.target_player_id = target_player_id
            effect.goals_added = 2
        
        elif card.card_type == CardType.GOAL:
            effect.target_player_id = target_player_id
            effect.goals_added = 1
        
        elif card.card_type == CardType.INTERCEPTION:
            # Перехват: +1 передача СВОЕМУ игроку текущего хода
            effect.target_player_id = target_player_id
            effect.passes_added = 1
        
        elif card.card_type == CardType.TACKLE:
            # Отбор: +1 отбитие СВОЕМУ игроку текущего хода
            effect.target_player_id = target_player_id
            effect.saves_added = 1
        
        # === НЕГАТИВНЫЕ ДЛЯ СВОЕГО ИГРОКА ===
        elif card.card_type == CardType.FOUL:
            # Фол: -1 отбитие СВОЕМУ игроку текущего хода
            effect.target_player_id = target_player_id
            effect.saves_removed = 1
        
        elif card.card_type == CardType.LOSS:
            # Потеря: -1 передача СВОЕМУ игроку текущего хода
            effect.target_player_id = target_player_id
            effect.passes_removed = 1
        
        # === ДЕЙСТВУЮТ НА СОПЕРНИКА ТЕКУЩЕГО ХОДА ===
        elif card.card_type == CardType.OWN_GOAL:
            # Автогол: игрок СОПЕРНИКА текущего хода получает +1 гол
            effect.target_player_id = target_player_id
            effect.target_manager_id = match.get_opponent_id(manager_id)
            effect.goals_added = 1
        
        elif card.card_type == CardType.OFFSIDE:
            # Офсайд: отменяет гол игрока СОПЕРНИКА текущего хода
            effect.target_player_id = target_player_id
            effect.goals_removed = 1
        
        elif card.card_type == CardType.VAR:
            # ВАР: отменяет карточку соперника ЭТОГО хода
            opponent_id = match.get_opponent_id(manager_id)
            opponent_cards = [
                c for c in match.whistle_cards_drawn
                if c.applied_by_manager_id == opponent_id
                and c.turn_applied == current_turn
                and not c.is_used
            ]
            if opponent_cards:
                effect.card_cancelled_id = opponent_cards[-1].id
        
        elif card.card_type == CardType.RED_CARD:
            # Удаление: игрок СОПЕРНИКА теряет ВСЕ действия текущего хода
            effect.target_player_id = target_player_id
            effect.player_removed = True
        
        elif card.card_type == CardType.YELLOW_CARD:
            # Предупреждение: игрок СОПЕРНИКА теряет 1 действие (выбирает соперник)
            effect.target_player_id = target_player_id
            # Конкретное действие выбирается отдельно
        
        # === ОСОБЫЕ ===
        elif card.card_type == CardType.PENALTY:
            # Пенальти: розыгрыш больше/меньше
            effect.target_player_id = target_player_id
            effect.requires_penalty_roll = True
        
        return effect
    
    @staticmethod
    def apply_effect(match: Match, effect: CardEffect) -> Match:
        """Применить эффект карточки к матчу"""
        
        # Находим целевого игрока
        if effect.target_player_id:
            player: Optional[Player] = None
            for team in [match.team1, match.team2]:
                if team:
                    p = team.get_player_by_id(effect.target_player_id)
                    if p:
                        player = p
                        break
            
            if player:
                # Добавление действий
                if effect.goals_added > 0:
                    player.add_goals(effect.goals_added)
                if effect.saves_added > 0:
                    player.add_saves(effect.saves_added)
                if effect.passes_added > 0:
                    player.add_passes(effect.passes_added)
                
                # Удаление действий
                for _ in range(effect.goals_removed):
                    player.remove_action("goal")
                for _ in range(effect.saves_removed):
                    player.remove_action("save")
                for _ in range(effect.passes_removed):
                    player.remove_action("pass")
                
                # Удаление игрока
                if effect.player_removed:
                    player.clear_stats()
        
        # Автогол — добавляем гол сопернику
        if effect.target_manager_id and effect.goals_added > 0:
            team = match.get_team(effect.target_manager_id)
            if team:
                # Добавляем гол любому форварду на поле
                forwards = [p for p in team.get_field_players() 
                          if p.position.value == "forward" and p.is_available]
                if forwards:
                    forwards[0].add_goals(effect.goals_added)
        
        # Отмена карточки
        if effect.card_cancelled_id:
            for card in match.whistle_cards_drawn:
                if card.id == effect.card_cancelled_id:
                    card.is_used = False
                    # TODO: откатить эффект отменённой карточки
                    break
        
        # Пенальти
        if effect.requires_penalty_roll and match.current_turn:
            match.current_turn.waiting_for_penalty_roll = True
        
        return match
    
    @staticmethod
    def get_valid_targets(
        card: WhistleCard,
        match: Match,
        manager_id: UUID
    ) -> List[Player]:
        """
        Получить список допустимых целей для карточки.
        
        ВАЖНО: Цели — только игроки ТЕКУЩЕГО хода!
        """
        target_type = card.get_target_type()
        current_turn = match.current_turn
        
        if not current_turn:
            return []
        
        if target_type == CardTarget.SELF_PLAYER:
            # Свой игрок текущего хода
            if manager_id == match.manager1_id:
                player_id = current_turn.manager1_player_id
            else:
                player_id = current_turn.manager2_player_id
            
            if player_id:
                team = match.get_team(manager_id)
                if team:
                    player = team.get_player_by_id(player_id)
                    if player and player.is_available:
                        # Для негативных карточек — проверяем наличие действия
                        if card.card_type == CardType.FOUL:
                            if player.stats.saves > 0:
                                return [player]
                            return []
                        elif card.card_type == CardType.LOSS:
                            if player.stats.passes > 0:
                                return [player]
                            return []
                        return [player]
            return []
        
        elif target_type == CardTarget.OPPONENT_PLAYER:
            # Игрок соперника текущего хода
            opponent_id = match.get_opponent_id(manager_id)
            if not opponent_id:
                return []
            
            if opponent_id == match.manager1_id:
                player_id = current_turn.manager1_player_id
            else:
                player_id = current_turn.manager2_player_id
            
            if player_id:
                opponent_team = match.get_opponent_team(manager_id)
                if opponent_team:
                    player = opponent_team.get_player_by_id(player_id)
                    if player and player.is_available:
                        # Для офсайда — только если есть гол
                        if card.card_type == CardType.OFFSIDE:
                            if player.stats.goals > 0:
                                return [player]
                            return []
                        return [player]
            return []
        
        return []
