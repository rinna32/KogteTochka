from datetime import datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import settings
from bot.db import repo
from bot.db.engine import session_factory
from bot.handlers.client import PRICE_KEY, refresh_open_screens
from bot.services.fmt import window_button
from bot.services.notify import client_link
from bot.services.schedule_parser import parse_schedule

router = Router(name="master")
router.message.filter(F.from_user.id.in_(settings.staff_ids))

HELP = (
    "<b>Команды мастера</b>\n\n"
    "📅 <b>Добавить окна</b> — просто пришли расписание текстом:\n"
    "<code>24 сб\n9:00 (к/н)\n10:30 (к)</code>\n\n"
    "/windows — все будущие окна и кто записан\n"
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
    lines = ["<b>Окна</b> (№ — для /delwindow)\n"]
    for window, booking in rows:
        who = client_link(booking) if booking else "свободно"
        lines.append(f"№{window.id} · {window_button(window.start_at, window.label)} — {who}")
    await message.answer("\n".join(lines))


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
