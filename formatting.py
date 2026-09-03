"""Форматирование расписания в текст для Telegram (HTML parse mode)."""

from html import escape

from schedule_parser import TYPE_NAMES, DaySchedule, Lesson

TELEGRAM_MSG_LIMIT = 3500  # с запасом от лимита в 4096 символов


def _format_lesson(lesson: Lesson) -> str:
    head = lesson.time_display
    if lesson.room:
        head += f" · {lesson.room}"
    lines = [f"<b>{escape(head)}</b>"]

    type_line = TYPE_NAMES.get(lesson.lesson_type, lesson.lesson_type)
    if lesson.is_online:
        type_line += " · Онлайн"
    lines.append(type_line)

    lines.append(f"<b>{escape(lesson.subject)}</b>")

    teacher_line = escape(lesson.teacher) if lesson.teacher else "—"
    if lesson.url:
        teacher_line += f' · <a href="{escape(lesson.url)}">трансляция</a>'
    lines.append(teacher_line)

    return "\n".join(lines)


def _format_day(day: DaySchedule) -> str:
    header = f"📅 <b>{day.day_name}, {day.date.strftime('%d.%m')}</b>"
    if not day.lessons:
        return f"{header}\n<i>Занятий нет</i>"
    body = "\n\n".join(_format_lesson(l) for l in day.lessons)
    return f"{header}\n\n{body}"


def build_messages(schedule: list[DaySchedule], group: str, updated_ago: str) -> list[str]:
    """Возвращает список сообщений (HTML), уже разбитых по лимиту длины Telegram."""
    intro = f"🗓 Расписание для группы <b>{escape(group)}</b>\n<i>Данные обновлены: {updated_ago}</i>"

    day_blocks = [_format_day(d) for d in schedule]

    messages: list[str] = []
    current = intro
    for block in day_blocks:
        candidate = f"{current}\n\n{block}"
        if len(candidate) > TELEGRAM_MSG_LIMIT and current:
            messages.append(current)
            current = block
        else:
            current = candidate

    messages.append(current)
    return messages
