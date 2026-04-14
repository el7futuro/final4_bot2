# src/platforms/telegram/handlers/pvp_notify.py
"""Уведомления для PvP (отправка сообщений сопернику)"""

import logging
from uuid import UUID

from ..keyboards.inline import Keyboards
from ..renderers.match_renderer import MatchRenderer
from ..storage import get_storage

logger = logging.getLogger(__name__)


async def notify_opponent_waiting_for_roll(bot, match, roller_id: UUID):
    """Уведомить manager2 что ждём броска manager1"""
    storage = get_storage()
    
    opponent_id = match.manager2_id if roller_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        return
    
    renderer = MatchRenderer()
    bets_text = renderer.render_both_bets_before_roll(match, opponent_id)
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=bets_text + "\n\n⏳ <i>Ожидаем бросок соперника...</i>",
            reply_markup=None
        )
    except Exception as e:
        logger.error(f"Failed to notify opponent: {e}")


async def notify_manager1_can_roll(bot, match):
    """Уведомить manager1 что можно бросать кубик"""
    storage = get_storage()
    
    manager1 = storage.get_user_by_id(match.manager1_id)
    if not manager1:
        return
    
    renderer = MatchRenderer()
    bets_text = renderer.render_both_bets_before_roll(match, match.manager1_id)
    
    try:
        await bot.send_message(
            chat_id=manager1.telegram_id,
            text="✅ <b>Соперник подтвердил ставки!</b>\n\n" + bets_text,
            reply_markup=Keyboards.roll_dice_button()
        )
    except Exception as e:
        logger.error(f"Failed to notify manager1: {e}")


async def notify_opponent_turn_result(bot, match, roller_user_id: UUID, dice_value: int, won_bets):
    """Уведомить соперника о результатах хода (PvP)"""
    storage = get_storage()
    
    opponent_id = match.manager2_id if roller_user_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    logger.info(f"[PVP] Notifying opponent: roller={roller_user_id}, opponent_id={opponent_id}, opponent={opponent}")
    
    if not opponent:
        logger.warning(f"[PVP] Opponent not found! opponent_id={opponent_id}")
        return
    
    renderer = MatchRenderer()
    text = renderer.render_dice_result_simultaneous(dice_value, won_bets, match, opponent_id)
    
    cards_text = renderer.render_cards_drawn(match, opponent_id)
    if cards_text:
        text += "\n\n" + cards_text
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=text,
            reply_markup=Keyboards.game_actions_after_roll()
        )
        logger.info(f"[PVP] Notification sent successfully to {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent turn result: {e}")


async def notify_penalty_owner_with_choice(bot, match, penalty_owner_id: UUID):
    """Уведомить владельца пенальти о необходимости выбора (PvP)"""
    storage = get_storage()
    penalty_owner = storage.get_user_by_id(penalty_owner_id)
    
    if not penalty_owner:
        logger.warning(f"[PVP] Penalty owner not found: {penalty_owner_id}")
        return
    
    renderer = MatchRenderer()
    status_text = renderer.render_match_status(match, penalty_owner_id)
    
    text = (
        status_text + "\n\n"
        "⚽ <b>ПЕНАЛЬТИ!</b>\n\n"
        "Выберите направление удара:"
    )
    
    try:
        await bot.send_message(
            chat_id=penalty_owner.telegram_id,
            text=text,
            reply_markup=Keyboards.penalty_choice()
        )
        logger.info(f"[PVP] Penalty choice sent to {penalty_owner.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify penalty owner: {e}")


async def notify_opponent_penalty_result(bot, match, penalty_user_id: UUID, success: bool, dice_value: int, choice: str):
    """Уведомить соперника о результате пенальти"""
    storage = get_storage()
    
    opponent_id = match.manager2_id if penalty_user_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        return
    
    renderer = MatchRenderer()
    
    dice_emoji = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    choice_text = "Больше (4-6)" if choice == "high" else "Меньше (1-3)"
    
    if success:
        result_text = f"⚽ <b>ПЕНАЛЬТИ СОПЕРНИКА</b>\n\nСоперник выбрал: {choice_text}\n🎲 Выпало: {dice_emoji[dice_value]} {dice_value}\n\n❌ Соперник забил гол!"
    else:
        result_text = f"⚽ <b>ПЕНАЛЬТИ СОПЕРНИКА</b>\n\nСоперник выбрал: {choice_text}\n🎲 Выпало: {dice_emoji[dice_value]} {dice_value}\n\n✅ Вы отбили!"
    
    status_text = renderer.render_match_status(match, opponent_id)
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=status_text + "\n\n" + result_text,
            reply_markup=Keyboards.game_actions_after_roll()
        )
        logger.info(f"[PVP] Penalty result sent to opponent {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent penalty result: {e}")


async def notify_yellow_card_owner_with_choice(bot, match, target_manager_id: UUID):
    """Отправить владельцу игрока выбор, какое действие потерять (PvP)"""
    storage = get_storage()
    owner = storage.get_user_by_id(target_manager_id)
    
    if not owner:
        logger.warning(f"[PVP] Yellow card target manager not found: {target_manager_id}")
        return
    
    target_pid = match.current_turn.yellow_card_target_player_id
    target_team = match.get_team(target_manager_id)
    target_player = target_team.get_player_by_id(target_pid) if target_team and target_pid else None
    
    if not target_player:
        return
    
    has_goals = target_player.stats.goals > 0
    has_passes = target_player.stats.passes > 0
    has_saves = target_player.stats.saves > 0
    
    text = (
        f"🟡 <b>ПРЕДУПРЕЖДЕНИЕ!</b>\n\n"
        f"Ваш игрок <b>{target_player.name}</b> получил жёлтую карточку.\n"
        f"Текущие действия: "
    )
    stats_parts = []
    if target_player.stats.goals > 0:
        stats_parts.append(f"⚽{target_player.stats.goals}")
    if target_player.stats.passes > 0:
        stats_parts.append(f"🎯{target_player.stats.passes}")
    if target_player.stats.saves > 0:
        stats_parts.append(f"🛡{target_player.stats.saves}")
    text += " ".join(stats_parts) if stats_parts else "нет"
    text += "\n\nВыберите, какое действие потерять:"
    
    try:
        await bot.send_message(
            chat_id=owner.telegram_id,
            text=text,
            reply_markup=Keyboards.yellow_card_choice(has_goals, has_passes, has_saves)
        )
        logger.info(f"[PVP] Yellow card choice sent to {owner.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify yellow card owner: {e}")


async def notify_opponent_yellow_card_result(bot, match, affected_manager_id: UUID, action_type: str):
    """Уведомить соперника о результате предупреждения"""
    storage = get_storage()
    
    opponent_id = match.manager2_id if affected_manager_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        return
    
    action_names = {"goal": "гол", "pass": "передачу", "save": "отбитие"}
    text = f"🟡 <b>Предупреждение!</b>\nСоперник потерял {action_names.get(action_type, action_type)}."
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=text,
            reply_markup=Keyboards.game_actions_after_roll()
        )
        logger.info(f"[PVP] Yellow card result sent to opponent {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent yellow card result: {e}")


async def notify_opponent_match_finished(bot, match, user_id: UUID, finish_type: str):
    """Уведомить соперника о завершении матча (PvP)"""
    storage = get_storage()
    
    opponent_id = match.manager2_id if user_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        logger.warning(f"[PVP] Opponent not found for match finished notification")
        return
    
    renderer = MatchRenderer()
    result_text = renderer.render_match_result(match, opponent_id)
    
    if finish_type == "penalties":
        text = "⚽ <b>СЕРИЯ ПЕНАЛЬТИ!</b>\n\n" + result_text
    else:
        text = result_text
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=text,
            reply_markup=Keyboards.match_finished_menu()
        )
        logger.info(f"[PVP] Match finished notification sent to {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent match finished: {e}")


async def notify_opponent_extra_time(bot, match, user_id: UUID):
    """Уведомить соперника о переходе в Extra Time (PvP)"""
    storage = get_storage()
    
    opponent_id = match.manager2_id if user_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        return
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text="⏱ <b>ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ!</b>\n\n"
                 "Счёт равный, начинаем дополнительные 5 ходов.\n"
                 "⚠️ Каждый игрок ОБЯЗАН делать ставку на гол!",
            reply_markup=Keyboards.game_actions_simultaneous(0, 2, False, False)
        )
        logger.info(f"[PVP] Extra time notification sent to {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent extra time: {e}")


async def notify_opponent_new_turn(bot, match, user_id: UUID):
    """Уведомить соперника о новом ходе (PvP)"""
    storage = get_storage()
    
    opponent_id = match.manager2_id if user_id == match.manager1_id else match.manager1_id
    opponent = storage.get_user_by_id(opponent_id)
    
    if not opponent:
        logger.warning(f"[PVP] Opponent not found for new turn notification")
        return
    
    renderer = MatchRenderer()
    text = renderer.render_match_status(match, opponent_id)
    text += "\n\n" + renderer.render_turn_info_simultaneous(match, opponent_id)
    
    turn_num = match.current_turn.turn_number if match.current_turn else 1
    bets_count = len([b for b in match.bets 
                      if b.manager_id == opponent_id and b.turn_number == turn_num])
    from src.core.models.match import MatchPhase
    required_bets = 2 if match.phase == MatchPhase.EXTRA_TIME else (1 if turn_num == 1 else 2)
    
    try:
        await bot.send_message(
            chat_id=opponent.telegram_id,
            text=f"➡️ <b>Ход {turn_num}</b>\n\n" + text,
            reply_markup=Keyboards.game_actions_simultaneous(
                bets_count=bets_count,
                required_bets=required_bets,
                is_confirmed=False,
                both_ready=False
            )
        )
        logger.info(f"[PVP] New turn notification sent to {opponent.telegram_id}")
    except Exception as e:
        logger.error(f"[PVP] Failed to notify opponent new turn: {e}")
