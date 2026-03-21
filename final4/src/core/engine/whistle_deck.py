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
        """Определить эффект карточки"""
        effect = CardEffect(card_id=card.id, card_type=card.card_type)
        
        if card.card_type == CardType.HAT_TRICK:
            effect.target_player_id = target_player_id
            effect.goals_added = 3
        
        elif card.card_type == CardType.DOUBLE:
            effect.target_player_id = target_player_id
            effect.goals_added = 2
        
        elif card.card_type == CardType.GOAL:
            effect.target_player_id = target_player_id
            effect.goals_added = 1
        
        elif card.card_type == CardType.OWN_GOAL:
            # Автогол — соперник получает гол
            effect.target_manager_id = match.get_opponent_id(manager_id)
            effect.goals_added = 1
        
        elif card.card_type == CardType.VAR:
            # Отменяет последнюю карточку соперника в этом ходу
            opponent_id = match.get_opponent_id(manager_id)
            opponent_cards = [
                c for c in match.whistle_cards_drawn
                if c.applied_by_manager_id == opponent_id
                and c.turn_applied == (match.current_turn.turn_number if match.current_turn else 0)
                and not c.is_used
            ]
            if opponent_cards:
                effect.card_cancelled_id = opponent_cards[-1].id
        
        elif card.card_type == CardType.OFFSIDE:
            effect.target_player_id = target_player_id
            effect.goals_removed = 1
        
        elif card.card_type == CardType.PENALTY:
            effect.target_player_id = target_player_id
            effect.requires_penalty_roll = True
        
        elif card.card_type == CardType.RED_CARD:
            effect.target_player_id = target_player_id
            effect.player_removed = True
        
        elif card.card_type == CardType.YELLOW_CARD:
            effect.target_player_id = target_player_id
            # Соперник выбирает какое действие убрать (обрабатывается отдельно)
        
        elif card.card_type == CardType.FOUL:
            effect.target_player_id = target_player_id
            effect.saves_removed = 1
        
        elif card.card_type == CardType.LOSS:
            effect.target_player_id = target_player_id
            effect.passes_removed = 1
        
        elif card.card_type == CardType.INTERCEPTION:
            effect.target_player_id = target_player_id
            effect.passes_added = 1
        
        elif card.card_type == CardType.TACKLE:
            effect.target_player_id = target_player_id
            effect.saves_added = 1
        
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
        """Получить список допустимых целей для карточки"""
        target_type = card.get_target_type()
        
        if target_type == CardTarget.SELF_PLAYER:
            team = match.get_team(manager_id)
            if team:
                return [p for p in team.get_field_players() if p.is_available]
        
        elif target_type == CardTarget.OPPONENT_PLAYER:
            opponent_team = match.get_opponent_team(manager_id)
            if opponent_team:
                players = [p for p in opponent_team.get_field_players() if p.is_available]
                
                # Для офсайда — только игроки с голами
                if card.card_type == CardType.OFFSIDE:
                    players = [p for p in players if p.stats.goals > 0]
                
                # Для фола — только с отбитиями
                elif card.card_type == CardType.FOUL:
                    players = [p for p in players if p.stats.saves > 0]
                
                # Для потери — только с передачами
                elif card.card_type == CardType.LOSS:
                    players = [p for p in players if p.stats.passes > 0]
                
                return players
        
        return []
