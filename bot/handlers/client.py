from datetime import datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import keyboards as kb
from bot.config import settings
from bot.db import repo
from bot.db.engine import session_factory
from bot.services.fmt import window_full
from bot.services.notify import notify_master_new_booking

router = Router(name="client")

PRICE_KEY = "price_file_id"
WINDOWS_TEXT = "Выбери свободное окно 👇\n\n<i>к — коррекция, н — наращивание</i>"
NO_WINDOWS_TEXT = "Свободных окон пока нет 😔\nЗагляни чуть позже — мастер скоро откроет новые."
WINDOW_TAKEN_TEXT = "Ой, это окно только что заняли 🙈 Выбери другое 👇"


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


async def windows_screen(prefix: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    async with session_factory() as session:
        windows = await repo.free_windows(session, now())
    if not windows:
        return NO_WINDOWS_TEXT, kb.back_to_menu()
    text = f"{prefix}\n\n{WINDOWS_TEXT}" if prefix else WINDOWS_TEXT
    return text, kb.windows_menu(windows)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(greeting(message.from_user.first_name), reply_markup=kb.main_menu())


@router.callback_query(kb.Menu.filter(F.action == "main"))
async def on_main(call: CallbackQuery) -> None:
    await show(call, greeting(call.from_user.first_name), kb.main_menu())
    await call.answer()


@router.callback_query(kb.Menu.filter(F.action == "book"))
async def on_book(call: CallbackQuery) -> None:
    await show(call, *await windows_screen())
    await call.answer()


@router.callback_query(kb.Menu.filter(F.action == "price"))
async def on_price(call: CallbackQuery) -> None:
    async with session_factory() as session:
        file_id = await repo.get_setting(session, PRICE_KEY)
    if file_id is None:
        await show(call, "Прайс скоро появится 🙏", kb.price_menu())
    else:
        await call.message.delete()
        await call.message.answer_photo(file_id, reply_markup=kb.price_menu())
    await call.answer()


@router.callback_query(kb.PickWindow.filter())
async def on_pick_window(call: CallbackQuery, callback_data: kb.PickWindow, bot: Bot) -> None:
    user = call.from_user
    try:
        async with session_factory() as session, session.begin():
            booking = await repo.book_window(
                session, callback_data.id, now(), user.id, user.full_name, user.username
            )
    except repo.WindowUnavailable:
        await show(call, *await windows_screen(WINDOW_TAKEN_TEXT))
        await call.answer()
        return

    await call.message.edit_text(
        thanks_text(booking.window.start_at, booking.window.label), reply_markup=kb.back_to_menu()
    )
    await call.answer()
    await notify_master_new_booking(bot, booking)
