from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from bot.db import repo
from bot.db.engine import session_factory


class RememberClient(BaseMiddleware):
    """Сохраняет каждого, кто пишет боту или жмёт кнопки, — для рассылки.

    В базу пишем один раз за запуск бота на человека, чтобы не дёргать её на каждое нажатие.
    """

    def __init__(self) -> None:
        self.seen: set[int] = set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user and not user.is_bot and user.id not in self.seen:
            async with session_factory() as session, session.begin():
                await repo.upsert_client(session, user.id, user.full_name, user.username)
            self.seen.add(user.id)
        return await handler(event, data)
