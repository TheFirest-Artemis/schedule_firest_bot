from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import storage
from auth import is_authenticated
from config import DEFAULT_GROUP, SCHEDULE_DAYS_MAX, SCHEDULE_DAYS_MIN
from keyboards import BTN_SETTINGS, main_menu, settings_inline_kb
from states import DaysSetup, GroupSetup

router = Router()

NOT_AUTHENTICATED_TEXT = "Сначала введите пароль: отправьте /start."


@router.message(F.text == BTN_SETTINGS)
async def show_settings(message: Message, state: FSMContext):
    if not await is_authenticated(state):
        await message.answer(NOT_AUTHENTICATED_TEXT)
        return

    group = await storage.get_group(message.chat.id)
    days = await storage.get_default_days(message.chat.id)
    current = group or "не задана"
    await message.answer(
        f"⚙️ Текущая группа: <b>{current}</b>\n"
        f"Число дней по умолчанию (кнопка «🗓 Получить расписание»): <b>{days}</b>",
        parse_mode="HTML",
        reply_markup=settings_inline_kb(),
    )


@router.callback_query(F.data == "change_group")
async def ask_new_group(callback: CallbackQuery, state: FSMContext):
    if not await is_authenticated(state):
        await callback.answer(NOT_AUTHENTICATED_TEXT, show_alert=True)
        return

    await state.set_state(GroupSetup.waiting_for_group)
    await callback.message.answer(
        f"Введите новый номер группы в формате <b>{DEFAULT_GROUP}</b>.", parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "change_days")
async def ask_new_days(callback: CallbackQuery, state: FSMContext):
    if not await is_authenticated(state):
        await callback.answer(NOT_AUTHENTICATED_TEXT, show_alert=True)
        return

    await state.set_state(DaysSetup.waiting_for_days)
    await callback.message.answer(
        f"Введите число дней по умолчанию для кнопки «🗓 Получить расписание» "
        f"(от {SCHEDULE_DAYS_MIN} до {SCHEDULE_DAYS_MAX})."
    )
    await callback.answer()


@router.message(DaysSetup.waiting_for_days, F.text)
async def process_new_days(message: Message, state: FSMContext):
    if not await is_authenticated(state):
        await message.answer(NOT_AUTHENTICATED_TEXT)
        return

    text = message.text.strip()
    if not text.isdigit() or not (SCHEDULE_DAYS_MIN <= int(text) <= SCHEDULE_DAYS_MAX):
        await message.answer(
            f"Нужно целое число от {SCHEDULE_DAYS_MIN} до {SCHEDULE_DAYS_MAX}. Попробуйте ещё раз."
        )
        return

    days = int(text)
    await storage.set_default_days(message.chat.id, days)
    await state.set_state(None)
    await message.answer(
        f"Готово! Кнопка «🗓 Получить расписание» теперь показывает {days} дн.",
        reply_markup=main_menu(days),
    )
