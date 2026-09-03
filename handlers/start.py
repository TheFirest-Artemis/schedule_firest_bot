import re

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import storage
from auth import check_password, is_authenticated, set_authenticated
from config import DEFAULT_GROUP
from keyboards import BTN_SCHEDULE_WEEK, main_menu, schedule_button_text
from states import AuthGate, GroupSetup
from utils import GROUP_RE_SOURCE

router = Router()
GROUP_RE = re.compile(GROUP_RE_SOURCE)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    # Пароль запрашивается заново при каждом /start, независимо от прошлых сессий.
    await state.set_data({"authenticated": False})
    await state.set_state(AuthGate.waiting_for_password)
    await message.answer("🔒 Введите пароль для доступа к боту:")


@router.message(AuthGate.waiting_for_password, F.text)
async def process_password(message: Message, state: FSMContext):
    if not check_password(message.text):
        await message.answer("Неверный пароль. Попробуйте ещё раз.")
        return

    await set_authenticated(state)
    await _greet(message, state)


async def _greet(message: Message, state: FSMContext):
    group = await storage.get_group(message.chat.id)
    if group:
        await state.set_state(None)
        days = await storage.get_default_days(message.chat.id)
        await message.answer(
            f"С возвращением! Ваша группа: <b>{group}</b>.\n"
            f"«{schedule_button_text(days)}» — на ближайшие {days} дн., "
            f"«{BTN_SCHEDULE_WEEK}» — на 7 дней вперёд.",
            reply_markup=main_menu(days),
            parse_mode="HTML",
        )
        return

    await state.set_state(GroupSetup.waiting_for_group)
    await message.answer(
        "Привет! Я бот-расписание.\n\n"
        f"Для начала укажите номер вашей группы в формате <b>{DEFAULT_GROUP}</b> "
        "(как указано в таблице расписания РУЗ).",
        parse_mode="HTML",
    )


@router.message(GroupSetup.waiting_for_group, F.text)
async def process_group_input(message: Message, state: FSMContext):
    if not await is_authenticated(state):
        await message.answer("Сначала введите пароль: отправьте /start.")
        return

    group = message.text.strip().replace(" ", "")
    if not GROUP_RE.match(group):
        await message.answer(
            f"Не похоже на номер группы. Введите в формате <b>{DEFAULT_GROUP}</b>.",
            parse_mode="HTML",
        )
        return

    await storage.set_group(message.chat.id, group)
    await state.set_state(None)
    days = await storage.get_default_days(message.chat.id)
    await message.answer(
        f"Готово! Группа сохранена: <b>{group}</b>.\n"
        "Изменить её в любой момент можно в «⚙️ Настройки».",
        reply_markup=main_menu(days),
        parse_mode="HTML",
    )
