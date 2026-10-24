from datetime import datetime
from zoneinfo import ZoneInfo

from bot.services.schedule_parser import parse_schedule

MSK = ZoneInfo("Europe/Moscow")
# суббота, 24 октября 2026, 12:00
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=MSK)

SAMPLE = """
17 сб 👻

9:00 (к/н)
10:30 (к)

22 чт 👻

11:30 (к/н)

24 сб 👻

9:00 (к/н)
11:30 (к/н)
12:00 (к)
14:30 ( к / н )
17:30

25 вс👻

9:00 (к/н)
10:30 (к)

2 пн
10:00 (н)
"""


def starts(result):
    return [(w.start_at.strftime("%d.%m %H:%M"), w.label) for w in result.windows]


def test_sample_schedule():
    r = parse_schedule(SAMPLE, NOW)
    assert starts(r) == [
        ("24.10 14:30", "к/н"),
        ("24.10 17:30", None),
        ("25.10 09:00", "к/н"),
        ("25.10 10:30", "к"),
        ("02.11 10:00", "н"),
    ]
    assert r.past_days == ["17 сб 👻", "22 чт 👻"]
    assert r.errors == []


def test_today_skips_passed_and_current_time():
    r = parse_schedule("24 сб\n9:00 (к)\n12:00 (к)\n12:30 (к)", NOW)
    assert starts(r) == [("24.10 12:30", "к")]


def test_timezone_is_moscow():
    r = parse_schedule("25 вс\n9:00", NOW)
    assert r.windows[0].start_at.utcoffset().total_seconds() == 3 * 3600


def test_month_rollover_to_next_year():
    now = datetime(2026, 12, 28, 10, 0, tzinfo=MSK)
    r = parse_schedule("5 вт\n10:00 (к)", now)  # 5 января 2027 — вторник
    assert starts(r) == [("05.01 10:00", "к")]
    assert r.windows[0].start_at.year == 2027


def test_wrong_weekday_is_error():
    r = parse_schedule("26 сб\n10:00", NOW)  # 26 октября — понедельник
    assert r.windows == []
    assert len(r.errors) == 1


def test_next_month_when_this_month_weekday_differs():
    r = parse_schedule("26 чт\n10:00", NOW)  # 26 октября — пн, 26 ноября — чт
    assert starts(r) == [("26.11 10:00", None)]


def test_garbage_and_time_without_day():
    r = parse_schedule("10:00\nпривет\n25 вс\n25:00", NOW)
    assert r.windows == []
    assert len(r.errors) == 3
