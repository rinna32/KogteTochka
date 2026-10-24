"""Разбор расписания, которое мастер присылает текстом.

Пример:
    24 сб 👻
    9:00 (к/н)
    10:30 (к)

Строка с числом и днём недели начинает день, строки со временем — окна этого дня.
Месяц не пишут, поэтому берём ближайшую дату с этим числом, у которой совпадает день недели.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

DAY_RE = re.compile(r"^\s*(\d{1,2})\s*(пн|вт|ср|чт|пт|сб|вс)", re.IGNORECASE)
TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*(?:\(([^)]*)\))?")

# Дата из расписания может быть немного в прошлом (мастер прислала старый список)
PAST_LOOKBACK_DAYS = 14
# Сколько ближайших дат с этим числом проверять. Больше двух нельзя:
# опечатка в дне недели молча унесёт окно на несколько месяцев вперёд.
CANDIDATES = 2


@dataclass
class ParsedWindow:
    start_at: datetime
    label: str | None


@dataclass
class ParseResult:
    windows: list[ParsedWindow] = field(default_factory=list)
    past_days: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def resolve_day(day: int, weekday: int, today: date) -> date | None:
    """Ближайшая дата с числом `day` и днём недели `weekday`, начиная с недавнего прошлого."""
    start = today - timedelta(days=PAST_LOOKBACK_DAYS)
    year, month = start.year, start.month
    checked = 0
    while checked < CANDIDATES and year <= start.year + 1:
        try:
            candidate = date(year, month, day)
        except ValueError:
            candidate = None
        if candidate and candidate >= start:
            checked += 1
            if candidate.weekday() == weekday:
                return candidate
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return None


def normalize_label(raw: str | None) -> str | None:
    if raw is None:
        return None
    label = re.sub(r"\s+", "", raw).lower()
    return label or None


def parse_schedule(text: str, now: datetime) -> ParseResult:
    """`now` — текущее время с часовым поясом мастера."""
    tz: ZoneInfo = now.tzinfo  # type: ignore[assignment]
    result = ParseResult()
    current_day: date | None = None
    skip_day = False

    for line in text.splitlines():
        if not line.strip():
            continue

        if m := DAY_RE.match(line):
            raw = line.strip()
            weekday = WEEKDAYS.index(m.group(2).lower())
            current_day = resolve_day(int(m.group(1)), weekday, now.date())
            skip_day = False
            if current_day is None:
                result.errors.append(f"«{raw}» — не нашла такую дату")
                skip_day = True
            elif current_day < now.date():
                result.past_days.append(raw)
                skip_day = True
            continue

        if m := TIME_RE.match(line):
            if skip_day:
                continue
            if current_day is None:
                result.errors.append(f"«{line.strip()}» — время без даты выше")
                continue
            hour, minute = int(m.group(1)), int(m.group(2))
            if hour > 23 or minute > 59:
                result.errors.append(f"«{line.strip()}» — неверное время")
                continue
            start_at = datetime.combine(current_day, time(hour, minute), tzinfo=tz)
            if start_at <= now:
                continue
            result.windows.append(ParsedWindow(start_at, normalize_label(m.group(3))))
            continue

        result.errors.append(f"«{line.strip()}» — не поняла строку")

    return result
