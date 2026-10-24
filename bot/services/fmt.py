from datetime import datetime

from bot.config import settings

WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WEEKDAYS_FULL = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def local(dt: datetime) -> datetime:
    return dt.astimezone(settings.zone)


def window_button(start_at: datetime, label: str | None) -> str:
    """«сб 24.10 · 9:00 к/н» — текст кнопки."""
    dt = local(start_at)
    text = f"{WEEKDAYS_SHORT[dt.weekday()]} {dt:%d.%m} · {dt.hour}:{dt:%M}"
    return f"{text} {label}" if label else text


def window_full(start_at: datetime, label: str | None) -> str:
    """«суббота, 24 октября, 9:00 (к/н)» — в сообщениях."""
    dt = local(start_at)
    text = f"{WEEKDAYS_FULL[dt.weekday()]}, {dt.day} {MONTHS_GEN[dt.month - 1]}, {dt.hour}:{dt:%M}"
    return f"{text} ({label})" if label else text
