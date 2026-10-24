"""Кто сейчас смотрит список окон — чтобы обновить им экран, когда окна меняются.

Хранится в памяти: после перезапуска бота старые экраны не обновятся,
но занять уже занятое окно всё равно нельзя — это проверяет база.
"""
import time
from dataclasses import dataclass
from datetime import date

# Экран старше этого не обновляем — человек, скорее всего, ушёл
SCREEN_TTL_SEC = 30 * 60


@dataclass
class OpenScreen:
    message_id: int
    day: date | None  # None — список дней, иначе — время этого дня
    opened_at: float


_screens: dict[int, OpenScreen] = {}


def register(chat_id: int, message_id: int, day: date | None) -> None:
    _screens[chat_id] = OpenScreen(message_id, day, time.monotonic())


def unregister(chat_id: int) -> None:
    _screens.pop(chat_id, None)


def active(exclude_chat_id: int | None = None) -> list[tuple[int, OpenScreen]]:
    """Открытые экраны, кроме устаревших (их заодно забываем)."""
    deadline = time.monotonic() - SCREEN_TTL_SEC
    for chat_id in [c for c, s in _screens.items() if s.opened_at < deadline]:
        del _screens[chat_id]
    return [(c, s) for c, s in _screens.items() if c != exclude_chat_id]
