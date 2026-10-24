from datetime import datetime

from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Booking, Client, Setting, Window
from bot.services.schedule_parser import ParsedWindow

class WindowUnavailable(Exception):
    """Окно уже заняли, удалили или его время прошло."""


class AlreadyBooked(Exception):
    """У клиентки уже есть будущая запись."""

    # Значения, а не объект Window: после отката транзакции объект устаревает
    def __init__(self, start_at: datetime, label: str | None):
        self.start_at = start_at
        self.label = label


async def add_windows(session: AsyncSession, parsed: list[ParsedWindow]) -> int:
    """Добавляет окна, пропуская уже существующие. Возвращает число новых."""
    if not parsed:
        return 0
    stmt = (
        insert(Window)
        .values([{"start_at": w.start_at, "label": w.label} for w in parsed])
        .on_conflict_do_nothing(index_elements=["start_at"])
        .returning(Window.id)
    )
    return len((await session.execute(stmt)).all())


def _is_booked():
    return exists().where(Booking.window_id == Window.id, Booking.status == "active")


async def free_windows(session: AsyncSession, now: datetime) -> list[Window]:
    stmt = (
        select(Window)
        .where(Window.start_at > now, ~_is_booked())
        .order_by(Window.start_at)
    )
    return list(await session.scalars(stmt))


async def upcoming_windows(session: AsyncSession, now: datetime) -> list[tuple[Window, Booking | None]]:
    """Все будущие окна с активной записью, если она есть — для мастера."""
    stmt = (
        select(Window, Booking)
        .outerjoin(Booking, (Booking.window_id == Window.id) & (Booking.status == "active"))
        .where(Window.start_at > now)
        .order_by(Window.start_at)
    )
    return [(w, b) for w, b in (await session.execute(stmt)).all()]


async def active_booking_window(session: AsyncSession, tg_id: int, now: datetime) -> Window | None:
    """Окно будущей активной записи клиентки, если она есть."""
    stmt = (
        select(Window)
        .join(Booking, Booking.window_id == Window.id)
        .where(Booking.client_tg_id == tg_id, Booking.status == "active", Window.start_at > now)
        .order_by(Window.start_at)
        .limit(1)
    )
    return await session.scalar(stmt)


async def book_window(
    session: AsyncSession,
    window_id: int,
    now: datetime,
    tg_id: int,
    name: str,
    username: str | None,
) -> Booking:
    # Блокировка на клиентку до конца транзакции: двойное нажатие на два окна
    # не создаст две записи — вторая транзакция дождётся первой и увидит её запись
    await session.execute(select(func.pg_advisory_xact_lock(tg_id)))
    if existing := await active_booking_window(session, tg_id, now):
        raise AlreadyBooked(existing.start_at, existing.label)

    window = await session.get(Window, window_id)
    if window is None or window.start_at <= now:
        raise WindowUnavailable
    booking = Booking(
        window_id=window.id, client_tg_id=tg_id, client_name=name, client_username=username
    )
    session.add(booking)
    try:
        # уникальный индекс one_active_booking_per_window не даст занять окно дважды
        await session.flush()
    except IntegrityError:
        raise WindowUnavailable
    booking.window = window
    return booking


async def delete_window(session: AsyncSession, window_id: int) -> Window | None:
    """Удаляет свободное окно. Занятое не трогает и возвращает None."""
    window = await session.get(Window, window_id)
    if window is None:
        return None
    booked = await session.scalar(
        select(exists().where(Booking.window_id == window_id, Booking.status == "active"))
    )
    if booked:
        return None
    await session.delete(window)
    return window


async def get_setting(session: AsyncSession, key: str) -> str | None:
    setting = await session.get(Setting, key)
    return setting.value if setting else None


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    stmt = insert(Setting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": value})
    await session.execute(stmt)



async def cancel_window_booking(session: AsyncSession, window_id: int) -> Booking | None:
    """Отменяет активную запись на окне. Возвращает её (с окном) или None, если записи нет."""
    stmt = (
        select(Booking)
        .where(Booking.window_id == window_id, Booking.status == "active")
        .with_for_update()
    )
    booking = await session.scalar(stmt)
    if booking is None:
        return None
    booking.status = "cancelled"
    booking.window = await session.get(Window, window_id)
    return booking


async def upsert_client(session: AsyncSession, tg_id: int, name: str, username: str | None) -> None:
    stmt = insert(Client).values(tg_id=tg_id, name=name, username=username)
    stmt = stmt.on_conflict_do_update(
        index_elements=["tg_id"],
        set_={"name": name, "username": username, "is_blocked": False},
    )
    await session.execute(stmt)


async def broadcast_recipients(session: AsyncSession, exclude: set[int]) -> list[int]:
    stmt = select(Client.tg_id).where(~Client.is_blocked)
    if exclude:
        stmt = stmt.where(Client.tg_id.not_in(exclude))
    return list(await session.scalars(stmt))


async def mark_blocked(session: AsyncSession, tg_id: int) -> None:
    await session.execute(update(Client).where(Client.tg_id == tg_id).values(is_blocked=True))
