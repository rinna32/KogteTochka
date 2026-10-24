"""Меню мастера — всё на кнопках, команды запоминать не нужно.

Расписание мастер присылает обычным текстом в любой момент.
"""
import asyncio
import logging
from datetime import date, datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, User

from bot import keyboards as kb
from bot.config import settings
from bot.db import repo
from bot.db.engine import session_factory
from bot.db.models import Booking
from bot.handlers.client import PRICE_KEY, greeting, refresh_open_screens, show, show_static
from bot.services.broadcast import broadcast_hot_window
from bot.services.fmt import day_full, local, window_full
from bot.services.notify import client_link
from bot.services.schedule_parser import parse_schedule

log = logging.getLogger(__name__)
router = Router(name="master")
router.message.filter(F.from_user.id.in_(settings.staff_ids))
router.callback_query.filter(F.from_user.id.in_(settings.staff_ids))

# ссылки на фоновые рассылки, чтобы их не собрал сборщик мусора
_background: set[asyncio.Task] = set()

MENU_TEXT = "Привет, {name}! 💅\n\nЭто меню {panel} 👇"
ADD_TEXT = (
    "➕ <b>Как добавить окна</b>\n\n"
    "Просто пришли сюда расписание одним сообщением, как обычно:\n\n"
    "<code>24 сб\n9:00 (к/н)\n10:30 (к)\n\n25 вс\n11:30 (к/н)</code>\n\n"
    "к — коррекция, н — наращивание. Я сама разберу и добавлю окна."
)


class MasterStates(StatesGroup):
    waiting_price = State()


def menu_text(user: User) -> str:
    return MENU_TEXT.format(name=escape(user.first_name), panel=settings.panel_name(user.id))


def now() -> datetime:
    return datetime.now(settings.zone)


def booking_text(booking: Booking) -> str:
    created = local(booking.created_at)
    return (
        "📋 <b>Запись</b>\n\n"
        f"🗓 {window_full(booking.window.start_at, booking.window.label)}\n"
        f"👤 {client_link(booking)}\n"
        f"🕒 Записалась {created:%d.%m} в {created:%H:%M}"
    )


# --- главное меню ---

@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    panel = settings.panel_name(user.id)
    if panel == "админа":
        # админ чаще записывается сама, поэтому сначала — меню записи
        await message.answer(greeting(user), reply_markup=kb.main_menu(panel))
    else:
        await message.answer(menu_text(user), reply_markup=kb.master_menu())


@router.callback_query(kb.Master.filter(F.action == "menu"))
async def on_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_static(call, menu_text(call.from_user), kb.master_menu())
    await call.answer()


@router.callback_query(kb.Master.filter(F.action == "client"))
async def on_client_view(call: CallbackQuery) -> None:
    await show_static(call, greeting(call.from_user), kb.main_menu(settings.panel_name(call.from_user.id)))
    await call.answer()


# --- записи ---

@router.callback_query(kb.Master.filter(F.action == "bookings"))
async def on_bookings(call: CallbackQuery) -> None:
    async with session_factory() as session:
        bookings = await repo.upcoming_bookings(session, now())
    if bookings:
        text = f"📋 <b>Записи</b> ({len(bookings)})\n\nНажми на запись, чтобы посмотреть подробности или отменить"
    else:
        text = "📋 Будущих записей пока нет"
    await show_static(call, text, kb.bookings_list(bookings))
    await call.answer()


@router.callback_query(kb.Master.filter(F.action == "booking"))
async def on_booking(call: CallbackQuery, callback_data: kb.Master) -> None:
    async with session_factory() as session:
        booking = await repo.get_booking(session, callback_data.id)
    if booking is None or booking.status != "active":
        await show_static(call, "Эта запись уже отменена", kb.to_bookings())
    else:
        await show_static(call, booking_text(booking), kb.booking_card(booking.id))
    await call.answer()


@router.callback_query(kb.Master.filter(F.action == "cancel"))
async def on_cancel_ask(call: CallbackQuery, callback_data: kb.Master) -> None:
    async with session_factory() as session:
        booking = await repo.get_booking(session, callback_data.id)
    if booking is None or booking.status != "active":
        await show_static(call, "Эта запись уже отменена", kb.to_bookings())
        await call.answer()
        return
    text = (
        "<b>Отменить запись?</b>\n\n"
        f"🗓 {window_full(booking.window.start_at, booking.window.label)}\n"
        f"👤 {client_link(booking)}\n\n"
        "Клиентке придёт сообщение об отмене"
    )
    if booking.window.start_at > now():
        text += ", а всем остальным — «🔥 Горит окошко»"
    await show_static(call, text, kb.cancel_confirm(booking.id))
    await call.answer()


@router.callback_query(kb.Master.filter(F.action == "cancel_yes"))
async def on_cancel_yes(call: CallbackQuery, callback_data: kb.Master, bot: Bot) -> None:
    async with session_factory() as session, session.begin():
        booking = await repo.cancel_booking(session, callback_data.id)
    if booking is None:
        await show_static(call, "Эта запись уже отменена", kb.to_bookings())
        await call.answer()
        return

    window = booking.window
    when = window_full(window.start_at, window.label)
    hot = window.start_at > now()
    text = f"❌ <b>Запись отменена</b>\n\n🗓 {when}\n👤 {client_link(booking)}"
    if hot:
        text += "\n\n🔥 Рассылаю клиенткам «Горит окошко»…"
    await show_static(call, text, kb.to_bookings())
    await call.answer("Запись отменена")

    await notify_client_cancelled(bot, booking.client_tg_id, when)
    await refresh_open_screens(bot)
    if hot:
        # рассылка может идти долго — не держим нажатие
        task = asyncio.create_task(
            run_hot_window_broadcast(
                bot, call.message.chat.id, window.id, window.start_at, window.label,
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


# --- свободные окна ---

async def free_windows_by_day() -> dict[date, list]:
    async with session_factory() as session:
        windows = await repo.free_windows(session, now())
    by_day: dict[date, list] = {}
    for w in windows:
        by_day.setdefault(local(w.start_at).date(), []).append(w)
    return by_day


async def show_master_days(call: CallbackQuery, prefix: str = "") -> None:
    by_day = await free_windows_by_day()
    if by_day:
        await show_static(call, f"{prefix}🗓 <b>Свободные окна</b>\nВыбери день 👇", kb.master_days(sorted(by_day)))
    else:
        await show_static(call, f"{prefix}Свободных окон нет. Нажми «➕ Добавить окна»", kb.to_master_menu())


async def show_master_times(call: CallbackQuery, day: date, prefix: str = "") -> None:
    windows = (await free_windows_by_day()).get(day)
    if not windows:
        await show_master_days(call, prefix)
        return
    text = f"{prefix}<b>{day_full(day)}</b>\nНажми на окно, чтобы удалить его"
    await show_static(call, text, kb.master_times(windows))


@router.callback_query(kb.Master.filter(F.action == "windows"))
async def on_windows(call: CallbackQuery) -> None:
    await show_master_days(call)
    await call.answer()


@router.callback_query(kb.Master.filter(F.action == "wday"))
async def on_windows_day(call: CallbackQuery, callback_data: kb.Master) -> None:
    await show_master_times(call, date.fromisoformat(callback_data.day))
    await call.answer()


@router.callback_query(kb.Master.filter(F.action == "window"))
async def on_window(call: CallbackQuery, callback_data: kb.Master) -> None:
    by_day = await free_windows_by_day()
    window = next((w for ws in by_day.values() for w in ws if w.id == callback_data.id), None)
    if window is None:
        await show_master_days(call, "Это окно уже заняли или удалили.\n\n")
    else:
        day = local(window.start_at).date().isoformat()
        text = f"<b>Удалить окно?</b>\n\n🗓 {window_full(window.start_at, window.label)}"
        await show_static(call, text, kb.delete_confirm(window.id, day))
    await call.answer()


@router.callback_query(kb.Master.filter(F.action == "del_yes"))
async def on_delete_window(call: CallbackQuery, callback_data: kb.Master, bot: Bot) -> None:
    async with session_factory() as session, session.begin():
        window = await repo.delete_window(session, callback_data.id)
    day = date.fromisoformat(callback_data.day)
    if window is None:
        prefix = "Это окно уже заняли — отменить запись можно в «📋 Записи».\n\n"
    else:
        prefix = "🗑 Окно удалено\n\n"
    await show_master_times(call, day, prefix)
    await call.answer()
    if window is not None:
        await refresh_open_screens(bot)


# --- добавление окон ---

@router.callback_query(kb.Master.filter(F.action == "add"))
async def on_add(call: CallbackQuery) -> None:
    await show_static(call, ADD_TEXT, kb.to_master_menu())
    await call.answer()


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
        lines.append("Не нашла в сообщении окон 🤔\n\n" + ADD_TEXT)
    await message.answer("\n".join(lines), reply_markup=kb.to_master_menu())
    if added:
        await refresh_open_screens(bot)


# --- прайс ---

@router.callback_query(kb.Master.filter(F.action == "price"))
async def on_price(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MasterStates.waiting_price)
    await show(call, "💰 Пришли картинку с новым прайсом одним фото", kb.to_master_menu())
    await call.answer()


@router.message(StateFilter(MasterStates.waiting_price), F.photo)
@router.message(F.photo, F.caption.startswith("/setprice"))
async def set_price(message: Message, state: FSMContext) -> None:
    async with session_factory() as session, session.begin():
        await repo.set_setting(session, PRICE_KEY, message.photo[-1].file_id)
    await state.clear()
    await message.answer("✅ Прайс обновлён", reply_markup=kb.to_master_menu())
