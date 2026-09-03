import logging
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import storage
from auth import is_authenticated
from config import SCHEDULE_DAYS_SHORT, SCHEDULE_DAYS_WEEK
from formatting import build_messages
from image_render import render_schedule_image
from keyboards import BTN_SCHEDULE_PREFIX, BTN_SCHEDULE_WEEK, image_inline_kb
from schedule_parser import GroupNotFoundError, build_schedule
from sheets_client import cache
from utils import humanize_ago

logger = logging.getLogger(__name__)
router = Router()

NOT_AUTHENTICATED_TEXT = "Сначала введите пароль: отправьте /start."


async def _require_group(message: Message) -> Optional[str]:
    group = await storage.get_group(message.chat.id)
    if not group:
        await message.answer(
            "Сначала укажите номер вашей группы: отправьте /start."
        )
        return None
    return group


async def _send_schedule(message: Message, days: int):
    group = await _require_group(message)
    if not group:
        return

    status = await message.answer("Загружаю расписание…")

    try:
        tabs = await cache.get_tabs()
        schedule = build_schedule(tabs, group, days=days)
    except GroupNotFoundError as e:
        await status.edit_text(str(e))
        return
    except Exception:
        logger.exception("Ошибка при получении расписания")
        await status.edit_text(
            "Не удалось получить данные из таблицы. Попробуйте ещё раз чуть позже."
        )
        return

    updated_ago = humanize_ago(cache.last_updated())
    messages = build_messages(schedule, group, updated_ago)

    await status.delete()
    for i, text in enumerate(messages):
        is_last = i == len(messages) - 1
        await message.answer(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=image_inline_kb(days) if is_last else None,
        )


@router.message(F.text.startswith(BTN_SCHEDULE_PREFIX))
async def send_schedule_short(message: Message, state: FSMContext):
    if not await is_authenticated(state):
        await message.answer(NOT_AUTHENTICATED_TEXT)
        return
    days = await storage.get_default_days(message.chat.id)
    await _send_schedule(message, days)


@router.message(F.text == BTN_SCHEDULE_WEEK)
async def send_schedule_week(message: Message, state: FSMContext):
    if not await is_authenticated(state):
        await message.answer(NOT_AUTHENTICATED_TEXT)
        return
    await _send_schedule(message, SCHEDULE_DAYS_WEEK)


@router.callback_query(F.data.startswith("image:"))
async def send_schedule_image(callback: CallbackQuery, state: FSMContext):
    if not await is_authenticated(state):
        await callback.answer(NOT_AUTHENTICATED_TEXT, show_alert=True)
        return

    group = await storage.get_group(callback.message.chat.id)
    if not group:
        await callback.answer("Сначала укажите группу через /start", show_alert=True)
        return

    try:
        days = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        days = SCHEDULE_DAYS_SHORT

    await callback.answer("Готовлю картинку…")

    try:
        tabs = await cache.get_tabs()
        schedule = build_schedule(tabs, group, days=days)
    except GroupNotFoundError as e:
        await callback.message.answer(str(e))
        return
    except Exception:
        logger.exception("Ошибка при получении расписания для картинки")
        await callback.message.answer(
            "Не удалось получить данные из таблицы. Попробуйте ещё раз чуть позже."
        )
        return

    png_bytes = render_schedule_image(schedule, group)

    start_date = schedule[0].date.strftime("%m-%d")
    filename = f"schedule_{group}_{start_date}_{days}.png"

    await callback.message.answer_document(
        BufferedInputFile(png_bytes, filename=filename),
        caption=f"Расписание {group}",
    )
