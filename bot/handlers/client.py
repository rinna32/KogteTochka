import asyncio
import logging
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import NamedTuple

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message, User

from bot import keyboards as kb
from bot.config import settings
from bot.db import repo
from bot.db.engine import session_factory
from bot.db.models import Window
from bot.services import live
from bot.services.fmt import day_full, local, window_full
from bot.services.notify import notify_master_new_booking

log = logging.getLogger(__name__)
router = Router(name="client")

PRICE_KEY = "price_file_id"
# Прайс по умолчанию: загружается в Telegram при первом показе, дальше шлётся по file_id
PRICE_IMAGE = Path(__file__).resolve().parents[2] / "assets" / "price.jpg"

DAYS_TEXT = "Выбери день 👇"
TIMES_TEXT = "<b>{day}</b>\nВыбери время 👇\n\n<i>к — коррекция, н — наращивание</i>"
NO_WINDOWS_TEXT = "Свободных окон пока нет 😔\nЗагляни чуть позже — мастер скоро откроет новые."
WINDOW_TAKEN_TEXT = "Ой, это окно только что заняли 🙈"


class Screen(NamedTuple):
    text: str
    markup: InlineKeyboardMarkup
    # что показано: None — список дней (или «окон нет»), иначе — время этого дня
    day: date | None = None


ADMIN_GREETING = "Кобыла, время точить копыта! 🐴💅"


def greeting(user: User) -> str:
    if settings.admin_id and user.id == settings.admin_id:
        return ADMIN_GREETING
    return client_greeting(user.first_name)


def client_greeting(name: str) -> str:
    return f"Привет, {escape(name)}! 💅\n\nДавай запишемся 👇"


def contacts_lines() -> list[str]:
    lines = []
    if settings.master_contact:
        lines += ["", f"Если нужно что-то уточнить, пиши мастеру: {settings.master_contact}"]
    if settings.admin_contact:
        lines += [f"Если бот сработал с ошибкой, напиши администратору: {settings.admin_contact}"]
    return lines


def thanks_text(start_at: datetime, label: str | None) -> str:
    return "\n".join(
        ["Спасибо за запись! 💖", "", f"🗓 {window_full(start_at, label)}", *contacts_lines()]
    )


def already_booked_text(start_at: datetime, label: str | None) -> str:
    return "\n".join(
        [
            "У тебя уже есть запись 💅",
            "",
            f"🗓 {window_full(start_at, label)}",
            "",
            "Записаться можно только на одно окно. Если нужно перенести или отменить — напиши мастеру.",
            *contacts_lines(),
        ]
    )


def now() -> datetime:
    return datetime.now(settings.zone)


async def show(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> Message:
    """Заменить текущий экран. Сообщение с фото в текстовое не превратить — шлём новое."""
    if call.message.photo:
        await call.message.delete()
        return await call.message.answer(text, reply_markup=markup)
    return await call.message.edit_text(text, reply_markup=markup)


async def show_live(call: CallbackQuery, screen: Screen) -> None:
    """Показать список окон и запомнить экран, чтобы обновлять его при изменениях."""
    message = await show(call, screen.text, screen.markup)
    live.register(call.message.chat.id, message.message_id, screen.day)


async def show_static(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    live.unregister(call.message.chat.id)
    await show(call, text, markup)


async def load_free_windows() -> list[Window]:
    async with session_factory() as session:
        return await repo.free_windows(session, now())


def with_prefix(prefix: str | None, text: str) -> str:
    return f"{prefix}\n\n{text}" if prefix else text


async def days_screen(prefix: str | None = None) -> Screen:
    windows = await load_free_windows()
    if not windows:
        return Screen(with_prefix(prefix, NO_WINDOWS_TEXT), kb.back_to_menu())
    days = sorted({local(w.start_at).date() for w in windows})
    return Screen(with_prefix(prefix, DAYS_TEXT), kb.days_menu(days))


async def times_screen(day: date, prefix: str | None = None) -> Screen:
    windows = [w for w in await load_free_windows() if local(w.start_at).date() == day]
    if not windows:
        # на этот день всё разобрали — возвращаем к выбору дня
        return await days_screen(prefix or "На этот день свободных окон уже нет 😔")
    text = TIMES_TEXT.format(day=day_full(day))
    return Screen(with_prefix(prefix, text), kb.times_menu(windows), day)


async def refresh_open_screens(bot: Bot, exclude_chat_id: int | None = None) -> None:
    """Перерисовать открытые списки окон у всех, кто их сейчас смотрит."""
    for chat_id, opened in live.active(exclude_chat_id):
        screen = await (times_screen(opened.day) if opened.day else days_screen())
        try:
            await bot.edit_message_text(
                screen.text, chat_id=chat_id, message_id=opened.message_id, reply_markup=screen.markup
            )
        except TelegramAPIError as e:
            # «message is not modified» — экран и так актуален; остальное — сообщение удалено и т.п.
            if "not modified" not in str(e):
                log.info("Не удалось обновить экран в чате %s: %s", chat_id, e)
                live.unregister(chat_id)
            continue
        live.register(chat_id, opened.message_id, screen.day)
        # лимит Telegram — около 30 сообщений в секунду на бота
        await asyncio.sleep(0.05)


async def booked_window(tg_id: int) -> Window | None:
    async with session_factory() as session:
        return await repo.active_booking_window(session, tg_id, now())


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    live.unregister(message.chat.id)
    await message.answer(greeting(message.from_user), reply_markup=kb.main_menu())


@router.callback_query(kb.Menu.filter(F.action == "main"))
async def on_main(call: CallbackQuery) -> None:
    is_staff = call.from_user.id in settings.staff_ids
    await show_static(call, greeting(call.from_user), kb.main_menu(is_staff))
    await call.answer()


@router.callback_query(kb.Menu.filter(F.action == "book"))
async def on_book(call: CallbackQuery) -> None:
    if window := await booked_window(call.from_user.id):
        await show_static(call, already_booked_text(window.start_at, window.label), kb.back_to_menu())
    else:
        await show_live(call, await days_screen())
    await call.answer()


@router.callback_query(kb.PickDay.filter())
async def on_pick_day(call: CallbackQuery, callback_data: kb.PickDay) -> None:
    await show_live(call, await times_screen(date.fromisoformat(callback_data.day)))
    await call.answer()


@router.callback_query(kb.Menu.filter(F.action == "price"))
async def on_price(call: CallbackQuery) -> None:
    live.unregister(call.message.chat.id)
    async with session_factory() as session:
        file_id = await repo.get_setting(session, PRICE_KEY)
    await call.message.delete()
    sent = await call.message.answer_photo(
        file_id or FSInputFile(PRICE_IMAGE), reply_markup=kb.price_menu()
    )
    if file_id is None:
        async with session_factory() as session, session.begin():
            await repo.set_setting(session, PRICE_KEY, sent.photo[-1].file_id)
    await call.answer()


@router.callback_query(kb.PickWindow.filter())
async def on_pick_window(call: CallbackQuery, callback_data: kb.PickWindow, bot: Bot) -> None:
    user = call.from_user
    day: date | None = None
    try:
        async with session_factory() as session, session.begin():
            window = await session.get(Window, callback_data.id)
            # запоминаем до записи: после отката транзакции объект окна устаревает
            day = local(window.start_at).date() if window else None
            booking = await repo.book_window(
                session, callback_data.id, now(), user.id, user.full_name, user.username
            )
    except repo.AlreadyBooked as e:
        await show_static(call, already_booked_text(e.start_at, e.label), kb.back_to_menu())
        await call.answer()
        return
    except repo.WindowUnavailable:
        screen = await (times_screen(day, WINDOW_TAKEN_TEXT) if day else days_screen(WINDOW_TAKEN_TEXT))
        await show_live(call, screen)
        await call.answer()
        return

    await show_static(
        call, thanks_text(booking.window.start_at, booking.window.label), kb.back_to_menu()
    )
    await call.answer()
    await notify_master_new_booking(bot, booking)
    await refresh_open_screens(bot, exclude_chat_id=call.message.chat.id)
