from datetime import date

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.models import Booking, Window
from bot.services.fmt import day_button, time_button, window_button

DAYS_PER_ROW = 2
# Telegram показывает не больше 100 кнопок в одном сообщении
MAX_DAYS = 60
TIMES_PER_ROW = 3


class Menu(CallbackData, prefix="menu"):
    action: str  # main | book | price


class PickDay(CallbackData, prefix="day"):
    day: str  # ISO-дата, 2026-10-25


class PickWindow(CallbackData, prefix="win"):
    id: int


class Master(CallbackData, prefix="m"):
    # menu | bookings | booking | cancel | cancel_yes | windows | wday | window | del_yes
    # | add | price | client
    action: str
    id: int = 0
    day: str = ""


def main_menu(panel: str | None = None) -> InlineKeyboardMarkup:
    """panel — «мастера» или «админа»: добавляет кнопку перехода в меню управления."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Записаться", callback_data=Menu(action="book"))
    kb.button(text="💰 Прайс", callback_data=Menu(action="price"))
    if panel:
        kb.button(text=f"⚙️ Меню {panel}", callback_data=Master(action="menu"))
    return kb.adjust(2).as_markup()


def price_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=Menu(action="main"))
    kb.button(text="📅 К записи", callback_data=Menu(action="book"))
    return kb.adjust(2).as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data=Menu(action="main"))
    return kb.as_markup()


def hot_window(window_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Записаться на это окно", callback_data=PickWindow(id=window_id))
    return kb.as_markup()


def book_again() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Записаться снова", callback_data=Menu(action="book"))
    return kb.as_markup()


def days_menu(days: list[date]) -> InlineKeyboardMarkup:
    return _days(days, lambda d: PickDay(day=d), Menu(action="main"))


def times_menu(windows: list[Window]) -> InlineKeyboardMarkup:
    return _times(windows, lambda w: PickWindow(id=w.id), Menu(action="book"))


def _days(days: list[date], make_cb, back: CallbackData) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in days[:MAX_DAYS]:
        kb.button(text=day_button(d), callback_data=make_cb(d.isoformat()))
    kb.adjust(DAYS_PER_ROW)
    kb.row(*back_button(back))
    return kb.as_markup()


def _times(windows: list[Window], make_cb, back: CallbackData) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for w in windows:
        kb.button(text=time_button(w.start_at, w.label), callback_data=make_cb(w))
    kb.adjust(TIMES_PER_ROW)
    kb.row(*back_button(back))
    return kb.as_markup()


def back_button(target: CallbackData, text: str = "⬅️ Назад") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=text, callback_data=target.pack())]


# --- мастер ---

MAX_BOOKINGS = 90
NAME_IN_BUTTON = 18


def master_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Записи", callback_data=Master(action="bookings"))
    kb.button(text="🗓 Свободные окна", callback_data=Master(action="windows"))
    kb.button(text="➕ Добавить окна", callback_data=Master(action="add"))
    kb.button(text="💰 Обновить прайс", callback_data=Master(action="price"))
    kb.button(text="👀 Как видят клиентки", callback_data=Master(action="client"))
    return kb.adjust(2, 2, 1).as_markup()


def to_master_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_button(Master(action="menu"), "⬅️ В меню мастера")])


def bookings_list(bookings: list[Booking]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in bookings[:MAX_BOOKINGS]:
        name = b.client_name if len(b.client_name) <= NAME_IN_BUTTON else b.client_name[:NAME_IN_BUTTON] + "…"
        kb.button(
            text=f"{window_button(b.window.start_at, b.window.label)} — {name}",
            callback_data=Master(action="booking", id=b.id),
        )
    kb.adjust(1)
    kb.row(*back_button(Master(action="menu")))
    return kb.as_markup()


def booking_card(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить запись", callback_data=Master(action="cancel", id=booking_id))
    kb.row(*back_button(Master(action="bookings"), "⬅️ К списку"))
    return kb.as_markup()


def cancel_confirm(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, отменить", callback_data=Master(action="cancel_yes", id=booking_id))
    kb.button(text="⬅️ Нет", callback_data=Master(action="booking", id=booking_id))
    return kb.adjust(2).as_markup()


def to_bookings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_button(Master(action="bookings"), "⬅️ К списку")])


def open_booking(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Открыть запись", callback_data=Master(action="booking", id=booking_id))
    return kb.as_markup()


def master_days(days: list[date]) -> InlineKeyboardMarkup:
    return _days(days, lambda d: Master(action="wday", day=d), Master(action="menu"))


def master_times(windows: list[Window]) -> InlineKeyboardMarkup:
    return _times(windows, lambda w: Master(action="window", id=w.id), Master(action="windows"))


def delete_confirm(window_id: int, day: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить", callback_data=Master(action="del_yes", id=window_id, day=day))
    kb.button(text="⬅️ Назад", callback_data=Master(action="wday", day=day))
    return kb.adjust(2).as_markup()
