import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from bot import keyboards as kb
from bot.db import repo
from bot.db.engine import session_factory
from bot.services.fmt import window_full

log = logging.getLogger(__name__)

# Лимит Telegram — около 30 сообщений в секунду; держимся с запасом
SEND_INTERVAL_SEC = 0.05


@dataclass
class BroadcastResult:
    sent: int = 0
    blocked: int = 0
    failed: int = 0


def hot_window_text(start_at: datetime, label: str | None) -> str:
    return f"🔥 Горит окошко на\n<b>{window_full(start_at, label)}</b>"


async def broadcast_hot_window(
    bot: Bot, window_id: int, start_at: datetime, label: str | None, exclude: set[int]
) -> BroadcastResult:
    async with session_factory() as session:
        recipients = await repo.broadcast_recipients(session, exclude)

    text = hot_window_text(start_at, label)
    markup = kb.hot_window(window_id)
    result = BroadcastResult()
    for tg_id in recipients:
        try:
            try:
                await bot.send_message(tg_id, text, reply_markup=markup)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                await bot.send_message(tg_id, text, reply_markup=markup)
            result.sent += 1
        except TelegramForbiddenError:
            # заблокировала бота
            result.blocked += 1
            async with session_factory() as session, session.begin():
                await repo.mark_blocked(session, tg_id)
        except Exception:
            result.failed += 1
            log.exception("Рассылка: не удалось отправить %s", tg_id)
        await asyncio.sleep(SEND_INTERVAL_SEC)
    return result
