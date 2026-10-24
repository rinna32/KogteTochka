import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from bot import keyboards as kb
from bot.config import settings
from bot.db.models import Booking
from bot.services.fmt import window_full

log = logging.getLogger(__name__)


def client_link(booking: Booking) -> str:
    link = f'<a href="tg://user?id={booking.client_tg_id}">{escape(booking.client_name)}</a>'
    if booking.client_username:
        link += f" (@{escape(booking.client_username)})"
    return link


async def notify_master_new_booking(bot: Bot, booking: Booking) -> None:
    text = (
        "🎉 <b>Новая запись</b>\n\n"
        f"🗓 {window_full(booking.window.start_at, booking.window.label)}\n"
        f"👤 {client_link(booking)}"
    )
    await send_to_master(bot, text, kb.open_booking(booking.id))


async def send_to_master(bot: Bot, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    if not settings.master_id:
        log.warning("MASTER_ID не задан — уведомление никому не отправлено:\n%s", text)
        return
    try:
        await bot.send_message(settings.master_id, text, reply_markup=markup)
    except TelegramAPIError as e:
        # Чаще всего — мастер ещё не нажала /start в боте
        log.error("Не удалось отправить мастеру: %s\n%s", e, text)
        if settings.admin_id and settings.admin_id != settings.master_id:
            try:
                await bot.send_message(
                    settings.admin_id,
                    f"⚠️ Не удалось отправить мастеру сообщение ({escape(str(e))}):\n\n{text}",
                )
            except TelegramAPIError:
                log.exception("Не удалось предупредить админа")
