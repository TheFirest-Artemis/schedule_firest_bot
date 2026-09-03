"""Рендер расписания в виде картинки (PNG) через Pillow."""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from config import FONT_BOLD, FONT_REGULAR
from schedule_parser import TYPE_NAMES, DaySchedule

WIDTH = 1000
MARGIN = 36

BG_COLOR = (244, 245, 247)
CARD_COLOR = (255, 255, 255)
CARD_BORDER = (231, 234, 238)
TEXT_MAIN = (27, 31, 39)
TEXT_SECONDARY = (107, 114, 128)
BANNER_COLOR = (37, 47, 74)
BANNER_TEXT = (255, 255, 255)
DAY_PILL_COLOR = (231, 234, 245)
DAY_PILL_TEXT = (37, 47, 74)
EMPTY_DAY_TEXT = (150, 155, 165)
GAP_TEXT_COLOR = (150, 155, 165)

TYPE_COLORS = {
    "Л": (76, 111, 255),
    "С": (34, 165, 89),
    "ПЗ": (242, 153, 74),
}


def _font(path, size):
    return ImageFont.truetype(str(path), size)


F_TITLE = lambda: _font(FONT_BOLD, 34)
F_SUBTITLE = lambda: _font(FONT_REGULAR, 20)
F_DAY = lambda: _font(FONT_BOLD, 24)
F_TIME = lambda: _font(FONT_BOLD, 26)
F_BADGE = lambda: _font(FONT_BOLD, 17)
F_SUBJECT = lambda: _font(FONT_BOLD, 23)
F_TEACHER = lambda: _font(FONT_REGULAR, 19)
F_EMPTY = lambda: _font(FONT_REGULAR, 19)
F_GAP = lambda: _font(FONT_REGULAR, 15)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not text:
        return [""]
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _format_gap(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"Перерыв {h}:{m:02d}"


GAP_ROW_HEIGHT = 30


def render_schedule_image(schedule: list[DaySchedule], group: str) -> bytes:
    scratch = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(scratch)

    content_width = WIDTH - 2 * MARGIN
    card_inner_pad = 20
    left_bar_w = 8
    text_left_offset = left_bar_w + card_inner_pad * 2
    text_width = content_width - text_left_offset - card_inner_pad

    banner_height = 158
    day_gap = 22
    card_gap = 12
    day_pill_h = 46

    # --- первый проход: считаем высоту ---
    total_height = banner_height + MARGIN
    day_layouts = []  # (day, [ ('lesson', lesson, h, subject_lines, teacher_lines) | ('gap', text) ])
    for day in schedule:
        total_height += day_pill_h + 14
        items = []
        if not day.lessons:
            total_height += 40 + card_gap
        else:
            prev_end = None
            for lesson in day.lessons:
                if prev_end is not None:
                    gap = lesson.start_minutes - prev_end
                    if gap > 0:
                        items.append(("gap", _format_gap(gap)))
                        total_height += GAP_ROW_HEIGHT
                prev_end = lesson.start_minutes + lesson.duration_minutes

                subject_lines = _wrap(draw, lesson.subject, F_SUBJECT(), text_width)
                teacher_text = lesson.teacher or "—"
                if lesson.url:
                    teacher_text += "   ▸ трансляция"
                teacher_lines = _wrap(draw, teacher_text, F_TEACHER(), text_width)
                h = card_inner_pad * 2 + 32 + 6 + 24 + 8 + len(subject_lines) * 28 + 6 + len(teacher_lines) * 24
                items.append(("lesson", lesson, h, subject_lines, teacher_lines))
                total_height += h + card_gap
        day_layouts.append((day, items))
        total_height += day_gap - card_gap

    total_height += MARGIN

    # --- второй проход: рисуем ---
    img = Image.new("RGB", (WIDTH, int(total_height)), BG_COLOR)
    draw = ImageDraw.Draw(img)

    first_date, last_date = schedule[0].date, schedule[-1].date
    if first_date == last_date:
        date_range = first_date.strftime("%d.%m")
    else:
        date_range = f"{first_date:%d.%m} – {last_date:%d.%m}"

    draw.rectangle([0, 0, WIDTH, banner_height], fill=BANNER_COLOR)
    draw.text((MARGIN, 26), "Расписание пар", font=F_TITLE(), fill=BANNER_TEXT)
    draw.text((MARGIN, 74), date_range, font=F_SUBTITLE(), fill=(210, 215, 230))
    draw.text(
        (MARGIN, 104),
        f"Группа {group}",
        font=F_SUBTITLE(),
        fill=(210, 215, 230),
    )

    y = banner_height + MARGIN

    for day, items in day_layouts:
        pill_text = f"{day.day_name}, {day.date.strftime('%d.%m')}"
        pill_w = draw.textlength(pill_text, font=F_DAY()) + 36
        draw.rounded_rectangle(
            [MARGIN, y, MARGIN + pill_w, y + day_pill_h], radius=day_pill_h // 2, fill=DAY_PILL_COLOR
        )
        draw.text(
            (MARGIN + 18, y + day_pill_h / 2),
            pill_text,
            font=F_DAY(),
            fill=DAY_PILL_TEXT,
            anchor="lm",
        )
        y += day_pill_h + 14

        if not items:
            draw.text((MARGIN + 4, y), "Занятий нет", font=F_EMPTY(), fill=EMPTY_DAY_TEXT)
            y += 40 + card_gap
            continue

        for item in items:
            if item[0] == "gap":
                _, gap_text = item
                draw.text((MARGIN + 4, y + 6), gap_text, font=F_GAP(), fill=GAP_TEXT_COLOR)
                y += GAP_ROW_HEIGHT
                continue

            _, lesson, h, subject_lines, teacher_lines = item
            x0, y0, x1, y1 = MARGIN, y, WIDTH - MARGIN, y + h
            draw.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=CARD_COLOR, outline=CARD_BORDER, width=1)
            color = TYPE_COLORS.get(lesson.lesson_type, (100, 100, 100))
            draw.rounded_rectangle(
                [x0, y0, x0 + left_bar_w, y1], radius=4, fill=color
            )

            tx = x0 + text_left_offset
            ty = y0 + card_inner_pad

            head = lesson.time_display
            if lesson.room:
                head += f"   ·   {lesson.room}"
            draw.text((tx, ty), head, font=F_TIME(), fill=TEXT_MAIN)
            ty += 32 + 6

            badge = TYPE_NAMES.get(lesson.lesson_type, lesson.lesson_type)
            if lesson.is_online:
                badge += "   ·   Онлайн"
            draw.text((tx, ty), badge, font=F_BADGE(), fill=color)
            ty += 24 + 8

            for line in subject_lines:
                draw.text((tx, ty), line, font=F_SUBJECT(), fill=TEXT_MAIN)
                ty += 28
            ty += 6

            for line in teacher_lines:
                draw.text((tx, ty), line, font=F_TEACHER(), fill=TEXT_SECONDARY)
                ty += 24

            y = y1 + card_gap

        y += day_gap - card_gap

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()
