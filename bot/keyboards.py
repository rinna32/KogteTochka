from datetime import date

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.models import Window
from bot.services.fmt import day_button, time_button

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


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Записаться", callback_data=Menu(action="book"))
    kb.button(text="💰 Прайс", callback_data=Menu(action="price"))
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
    kb = InlineKeyboardBuilder()
    for d in days[:MAX_DAYS]:
        kb.button(text=day_button(d), callback_data=PickDay(day=d.isoformat()))
    kb.adjust(DAYS_PER_ROW)
    kb.row(*back_button(Menu(action="main")))
    return kb.as_markup()


def times_menu(windows: list[Window]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for w in windows:
        kb.button(text=time_button(w.start_at, w.label), callback_data=PickWindow(id=w.id))
    kb.adjust(TIMES_PER_ROW)
    kb.row(*back_button(Menu(action="book")))
    return kb.as_markup()


def back_button(target: CallbackData) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="⬅️ Назад", callback_data=target.pack())]
