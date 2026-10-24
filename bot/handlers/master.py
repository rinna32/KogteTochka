import asyncio
import logging
from datetime import datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot import keyboards as kb
from bot.config import settings
from bot.db import repo
from bot.db.engine import session_factory
from bot.handlers.client import PRICE_KEY, refresh_open_screens
from bot.services.broadcast import broadcast_hot_window
from bot.services.fmt import window_button, window_full
from bot.services.notify import client_link
from bot.services.schedule_parser import parse_schedule

log = logging.getLogger(__name__)
router = Router(name="master")
# ссылки на фоновые рассылки, чтобы их не собрал сборщик мусора
_background: set[asyncio.Task] = set()
router.message.filter(F.from_user.id.in_(settings.staff_ids))

HELP = (
    "<b>Команды мастера</b>\n\n"
    "📅 <b>Добавить окна</b> — просто пришли расписание текстом:\n"
    "<code>24 сб\n9:00 (к/н)\n10:30 (к)</code>\n\n"
    "/windows — все будущие окна и кто записан\n"
    "/cancel 12 — отменить запись на окне №12: клиентке придёт сообщение, "
    "остальным — «🔥 Горит окошко»\n"
    "/delwindow 12 — удалить свободное окно №12\n"
    "💰 <b>Прайс</b> — пришли картинку с подписью /setprice"
)


def now() -> datetime:
    return datetime.now(settings.zone)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


@router.message(F.photo, F.caption.startswith("/setprice"))
async def set_price(message: Message) -> None:
    async with session_factory() as session, session.begin():
        await repo.set_setting(session, PRICE_KEY, message.photo[-1].file_id)
    await message.answer("✅ Прайс обновлён")


@router.message(Command("windows"))
async def cmd_windows(message: Message) -> None:
    async with session_factory() as session:
        rows = await repo.upcoming_windows(session, now())
    if not rows:
        await message.answer("Будущих окон нет. Пришли расписание, чтобы добавить.")
        return
    lines = ["<b>Окна</b> (№ — для /cancel и /delwindow)\n"]
    for window, booking in rows:
        who = client_link(booking) if booking else "свободно"
        lines.append(f"№{window.id} · {window_button(window.start_at, window.label)} — {who}")
    await message.answer("\n".join(lines))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, command: CommandObject, bot: Bot) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Напиши номер окна: /cancel 12\nНомера — в /windows")
        return
    async with session_factory() as session, session.begin():
        booking = await repo.cancel_window_booking(session, int(command.args))
    if booking is None:
        await message.answer("На этом окне нет активной записи. Номера — в /windows")
        return

    window = booking.window
    when = window_full(window.start_at, window.label)
    await message.answer(f"❌ Запись отменена\n🗓 {when}\n👤 {client_link(booking)}")
    await notify_client_cancelled(bot, booking.client_tg_id, when)
    await refresh_open_screens(bot)

    if window.start_at > now():
        await message.answer("🔥 Рассылаю клиенткам «Горит окошко»…")
        # рассылка может идти долго — не держим команду
        task = asyncio.create_task(
            run_hot_window_broadcast(
                bot, message.chat.id, window.id, window.start_at, window.label,
                exclude={booking.client_tg_id},
            )
        )
        _background.add(task)
        task.add_done_callback(_background.discard)


async def notify_client_cancelled(bot: Bot, tg_id: int, when: str) -> None:
    text = f"Твоя запись отменена 😔\n🗓 {when}"
    if settings.master_contact:
        text += f"\n\nЕсли есть вопросы — пиши мастеру: {settings.master_contact}"
    try:
        await bot.send_message(tg_id, text, reply_markup=kb.book_again())
    except TelegramAPIError as e:
        log.warning("Не удалось сообщить клиентке %s об отмене: %s", tg_id, e)


async def run_hot_window_broadcast(
    bot: Bot,
    report_chat_id: int,
    window_id: int,
    start_at: datetime,
    label: str | None,
    exclude: set[int],
) -> None:
    try:
        result = await broadcast_hot_window(bot, window_id, start_at, label, exclude)
        text = f"✅ «Горит окошко» отправлено: {result.sent}"
        if result.blocked:
            text += f"\nЗаблокировали бота: {result.blocked}"
        if result.failed:
            text += f"\nНе удалось отправить: {result.failed}"
    except Exception:
        log.exception("Рассылка «Горит окошко» упала")
        text = "⚠️ Рассылка «Горит окошко» прервалась с ошибкой"
    await bot.send_message(report_chat_id, text)


@router.message(Command("delwindow"))
async def cmd_delwindow(message: Message, command: CommandObject, bot: Bot) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Напиши номер окна: /delwindow 12\nНомера — в /windows")
        return
    async with session_factory() as session, session.begin():
        window = await repo.delete_window(session, int(command.args))
    if window is None:
        await message.answer("Такого свободного окна нет. Занятые окна удалить нельзя.")
    else:
        await message.answer(f"🗑 Удалено: {window_button(window.start_at, window.label)}")
        await refresh_open_screens(bot)


@router.message(F.text, ~F.text.startswith("/"))
async def add_schedule(message: Message, bot: Bot) -> None:
    result = parse_schedule(message.text, now())
    async with session_factory() as session, session.begin():
        added = await repo.add_windows(session, result.windows)

    lines = []
    if result.windows:
        lines.append(f"✅ Добавлено окон: {added}")
        if skipped := len(result.windows) - added:
            lines.append(f"Уже были в списке: {skipped}")
    if result.past_days:
        lines.append("\nПропустила прошедшие дни: " + ", ".join(escape(d) for d in result.past_days))
    if result.errors:
        lines.append("\n⚠️ Не поняла:\n" + "\n".join(escape(e) for e in result.errors))
    if not lines:
        lines.append("Не нашла в сообщении окон. /help — как прислать расписание")
    await message.answer("\n".join(lines))
    if added:
        await refresh_open_screens(bot)
