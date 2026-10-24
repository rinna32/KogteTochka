import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.handlers import client, master
from bot.middlewares import RememberClient


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    remember = RememberClient()
    dp.message.outer_middleware(remember)
    dp.callback_query.outer_middleware(remember)
    # мастер первым: её текст — это расписание; /start и кнопки обрабатывает client
    dp.include_router(master.router)
    dp.include_router(client.router)

    me = await bot.get_me()
    logging.info("Bot started: @%s", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
