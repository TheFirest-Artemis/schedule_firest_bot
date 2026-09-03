from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_SCHEDULE_PREFIX = "🗓 Получить расписание"
BTN_SCHEDULE_WEEK = "🗓 Расписание на неделю"
BTN_SETTINGS = "⚙️ Настройки"
BTN_CHANGE_GROUP = "✏️ Изменить группу"
BTN_CHANGE_DAYS = "🔢 Изменить число дней по умолчанию"
BTN_IMAGE = "🖼 Сохранить как изображение"


def schedule_button_text(days: int) -> str:
    return f"{BTN_SCHEDULE_PREFIX} ({days} дн.)"


def main_menu(days: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=schedule_button_text(days))],
            [KeyboardButton(text=BTN_SCHEDULE_WEEK)],
            [KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
    )


def image_inline_kb(days: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=BTN_IMAGE, callback_data=f"image:{days}")]]
    )


def settings_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=BTN_CHANGE_GROUP, callback_data="change_group")],
            [InlineKeyboardButton(text=BTN_CHANGE_DAYS, callback_data="change_days")],
        ]
    )
