from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.models import Window
from bot.services.fmt import local, window_button

WINDOWS_PER_ROW = 2


class Menu(CallbackData, prefix="menu"):
    action: str  # main | book | price


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


def windows_menu(windows: list[Window]) -> InlineKeyboardMarkup:
    """Свободные окна; окна одного дня — в своих рядах."""
    rows: list[list[InlineKeyboardButton]] = []
    row_day = None
    for w in windows:
        day = local(w.start_at).date()
        if not rows or day != row_day or len(rows[-1]) == WINDOWS_PER_ROW:
            rows.append([])
        row_day = day
        rows[-1].append(
            InlineKeyboardButton(
                text=window_button(w.start_at, w.label),
                callback_data=PickWindow(id=w.id).pack(),
            )
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=Menu(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
