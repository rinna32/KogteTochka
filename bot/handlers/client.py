from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="client")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"Привет, {message.from_user.first_name}! 💅\n"
        "Я помогу записаться на маникюр. Скоро здесь появится меню записи."
    )
