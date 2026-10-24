"""Начальное заполнение услуг и графика.

Запуск: docker compose run --rm bot python -m bot.seed
Таблицу, в которой уже есть данные, скрипт не трогает — можно запускать повторно.

ВНИМАНИЕ: данные ниже — примерные. Замените на настоящие от мастера.
"""
import asyncio
from datetime import time

from sqlalchemy import func, select

from bot.db.engine import engine, session_factory
from bot.db.models import Service, WorkSchedule

SERVICES = [
    # название, длительность (мин), цена (₽)
    ("Маникюр без покрытия", 60, 1000),
    ("Маникюр с покрытием гель-лак", 120, 2000),
    ("Наращивание", 180, 3500),
    ("Снятие покрытия", 30, 500),
]

# день недели (0 = пн): начало, конец, перерыв с, перерыв по
SCHEDULE = {
    1: (time(10), time(20), time(14), time(15)),
    2: (time(10), time(20), time(14), time(15)),
    3: (time(10), time(20), time(14), time(15)),
    4: (time(10), time(20), time(14), time(15)),
    5: (time(10), time(18), None, None),
}


async def seed() -> None:
    async with session_factory() as session, session.begin():
        if await session.scalar(select(func.count()).select_from(Service)):
            print("services: уже заполнено, пропускаю")
        else:
            session.add_all(
                Service(name=n, duration_min=d, price=p) for n, d, p in SERVICES
            )
            print(f"services: добавлено {len(SERVICES)}")

        if await session.scalar(select(func.count()).select_from(WorkSchedule)):
            print("work_schedule: уже заполнено, пропускаю")
        else:
            session.add_all(
                WorkSchedule(
                    weekday=wd, start_time=s, end_time=e, break_start=bs, break_end=be
                )
                for wd, (s, e, bs, be) in SCHEDULE.items()
            )
            print(f"work_schedule: добавлено {len(SCHEDULE)} дней")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
