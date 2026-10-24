from datetime import date, datetime
from html import escape
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message

from bot import keyboards as kb
from bot.config import settings
from bot.db import repo
from bot.db.engine import session_factory
from bot.db.models import Window
from bot.services.fmt import day_full, local, window_full
from bot.services.notify import notify_master_new_booking

router = Router(name="client")

PRICE_KEY = "price_file_id"
# Прайс по умолчанию: загружается в Telegram при первом показе, дальше шлётся по file_id
PRICE_IMAGE = Path(__file__).resolve().parents[2] / "assets" / "price.jpg"

DAYS_TEXT = "Выбери день 👇"
TIMES_TEXT = "<b>{day}</b>\nВыбери время 👇\n\n<i>к — коррекция, н — наращивание</i>"
NO_WINDOWS_TEXT = "Свободных окон пока нет 😔\nЗагляни чуть позже — мастер скоро откроет новые."
WINDOW_TAKEN_TEXT = "Ой, это окно только что заняли 🙈"


def greeting(name: str) -> str:
    return f"Привет, {escape(name)}! 💅\n\nДавай запишемся 👇"


def thanks_text(start_at: datetime, label: str | None) -> str:
    lines = ["Спасибо за запись! 💖", "", f"🗓 {window_full(start_at, label)}"]
    if settings.master_contact:
        lines += ["", f"Если нужно что-то уточнить, пиши мастеру: {settings.master_contact}"]
    if settings.admin_contact:
        lines += [f"Если бот сработал с ошибкой, напиши администратору: {settings.admin_contact}"]
    return "\n".join(lines)


def now() -> datetime:
    return datetime.now(settings.zone)


async def show(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Заменить текущий экран. Сообщение с фото в текстовое не превратить — шлём новое."""
    if call.message.photo:
        await call.message.delete()
        await call.message.answer(text, reply_markup=markup)
    else:
        await call.message.edit_text(text, reply_markup=markup)


async def load_free_windows() -> list[Window]:
    async with session_factory() as session:
        return await repo.free_windows(session, now())


async def days_screen(prefix: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    windows = await load_free_windows()
    if not windows:
        text = f"{prefix}\n\n{NO_WINDOWS_TEXT}" if prefix else NO_WINDOWS_TEXT
        return text, kb.back_to_menu()
    days = sorted({local(w.start_at).date() for w in windows})
    text = f"{prefix}\n\n{DAYS_TEXT}" if prefix else DAYS_TEXT
    return text, kb.days_menu(days)


async def times_screen(day: date, prefix: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    windows = [w for w in await load_free_windows() if local(w.start_at).date() == day]
    if not windows:
        # на этот день всё разобрали — возвращаем к выбору дня
        return await days_screen(prefix or "На этот день свободных окон уже нет 😔")
    text = TIMES_TEXT.format(day=day_full(day))
    return (f"{prefix}\n\n{text}" if prefix else text), kb.times_menu(windows)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(greeting(message.from_user.first_name), reply_markup=kb.main_menu())


@router.callback_query(kb.Menu.filter(F.action == "main"))
async def on_main(call: CallbackQuery) -> None:
    await show(call, greeting(call.from_user.first_name), kb.main_menu())
    await call.answer()


@router.callback_query(kb.Menu.filter(F.action == "book"))
async def on_book(call: CallbackQuery) -> None:
    await show(call, *await days_screen())
    await call.answer()


@router.callback_query(kb.PickDay.filter())
async def on_pick_day(call: CallbackQuery, callback_data: kb.PickDay) -> None:
    await show(call, *await times_screen(date.fromisoformat(callback_data.day)))
    await call.answer()


@router.callback_query(kb.Menu.filter(F.action == "price"))
async def on_price(call: CallbackQuery) -> None:
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
    except repo.WindowUnavailable:
        if day is not None:
            screen = await times_screen(day, WINDOW_TAKEN_TEXT)
        else:
            screen = await days_screen(WINDOW_TAKEN_TEXT)
        await show(call, *screen)
        await call.answer()
        return

    await call.message.edit_text(
        thanks_text(booking.window.start_at, booking.window.label), reply_markup=kb.back_to_menu()
    )
    await call.answer()
    await notify_master_new_booking(bot, booking)
