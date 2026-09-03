"""Проверка пароля доступа к боту. Требуется заново после каждого /start."""

from aiogram.fsm.context import FSMContext

from config import BOT_PASSWORD


async def is_authenticated(state: FSMContext) -> bool:
    data = await state.get_data()
    return bool(data.get("authenticated"))


async def set_authenticated(state: FSMContext) -> None:
    await state.update_data(authenticated=True)


def check_password(text: str) -> bool:
    return text.strip() == BOT_PASSWORD
