from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    # Все даты-время храним с часовым поясом (timestamptz)
    type_annotation_map = {datetime: DateTime(timezone=True)}


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    duration_min: Mapped[int]
    price: Mapped[int]  # в рублях
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

    __table_args__ = (
        CheckConstraint("duration_min > 0", name="duration_positive"),
        CheckConstraint("price >= 0", name="price_non_negative"),
    )


class WorkSchedule(Base):
    __tablename__ = "work_schedule"

    # 0 = понедельник … 6 = воскресенье, как date.weekday()
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    start_time: Mapped[time]
    end_time: Mapped[time]
    break_start: Mapped[time | None]
    break_end: Mapped[time | None]

    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("end_time > start_time", name="work_interval"),
        CheckConstraint(
            "(break_start IS NULL AND break_end IS NULL) OR "
            "(break_start >= start_time AND break_end <= end_time AND break_end > break_start)",
            name="break_inside_work",
        ),
    )


class DayOff(Base):
    __tablename__ = "days_off"

    day: Mapped[date] = mapped_column(primary_key=True)


class Window(Base):
    """Окно, которое мастер открыла для записи."""

    __tablename__ = "windows"

    id: Mapped[int] = mapped_column(primary_key=True)
    start_at: Mapped[datetime] = mapped_column(unique=True)
    # пометка из расписания мастера: «к», «н», «к/н»
    label: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    window_id: Mapped[int] = mapped_column(ForeignKey("windows.id", ondelete="CASCADE"))
    client_tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    client_name: Mapped[str] = mapped_column(String(100))
    client_username: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(32))
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    # active | cancelled
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    window: Mapped[Window] = relationship()
    service: Mapped[Service | None] = relationship()
    photos: Mapped[list["BookingPhoto"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("status IN ('active', 'cancelled')", name="booking_status"),
        # Защита от двойной записи: на одно окно — одна активная запись
        Index(
            "one_active_booking_per_window",
            "window_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )


class BookingPhoto(Base):
    __tablename__ = "booking_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[str] = mapped_column(String(255))

    booking: Mapped[Booking] = relationship(back_populates="photos")


class Client(Base):
    """Все, кто писал боту, — получатели рассылки «Горит окошко»."""

    __tablename__ = "clients"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100))
    username: Mapped[str | None] = mapped_column(String(64))
    # заблокировала бота — не шлём, пока снова не напишет
    is_blocked: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
