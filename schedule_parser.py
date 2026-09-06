"""Разбор сырых данных таблицы в список пар для конкретной группы и диапазона дат."""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sheets_client import SheetTab

DAY_LABELS = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
DAY_NAMES_FULL = {
    "ПН": "Понедельник",
    "ВТ": "Вторник",
    "СР": "Среда",
    "ЧТ": "Четверг",
    "ПТ": "Пятница",
    "СБ": "Суббота",
    "ВС": "Воскресенье",
}

TYPE_RE = re.compile(r"^\[(Л|С|ПЗ)\]\s*(.*)$")
ROOM_RE = re.compile(r"\b([А-ЯA-Z]{1,2}-?\d{3})\b")
URL_RE = re.compile(r"https?://[^\s)\]]+")

# Пометки про даты внутри ячейки пары (после предмета и преподавателя):
NOT_STARTED_RE = re.compile(r"2-?[ег]?о?\s*модул", re.IGNORECASE)  # "со 2 модуля" / "с 2-го модуля"
SKIP_SLOT_RE = re.compile(r"НЕ\s+ВЫБИРАТЬ", re.IGNORECASE)
START_DATE_RE = re.compile(r"^[CС]\s*(\d{1,2})\.(\d{2})\.?$")
ONLY_DATES_LINE_RE = re.compile(r"^\d{1,2}\.\d{2}(\s*,\s*\d{1,2}\.\d{2})*\.?$")
DATE_TOKEN_RE = re.compile(r"(\d{1,2})\.(\d{2})")
RESCHEDULE_RE = re.compile(
    r"(\d{1,2})\.(\d{2})\s+перенос(?:[^\d(){}\[\]]*)(\d{1,2})[.:](\d{2})", re.IGNORECASE
)

TYPE_NAMES = {"Л": "Лекция", "С": "Семинар", "ПЗ": "Практика"}


class GroupNotFoundError(Exception):
    pass


ONLINE_MARK_RE = re.compile(r"^ОНЛАЙН$", re.IGNORECASE)


@dataclass
class Lesson:
    day_label: str
    time_label: str
    start_minutes: int
    duration_minutes: int
    time_display: str
    lesson_type: str
    subject: str
    teacher: str
    room: Optional[str]
    url: Optional[str]
    is_online: bool = False


@dataclass
class _LessonTemplate:
    """Пара как она задана в строке таблицы, ещё без привязки к конкретной дате."""

    time_label: str
    time_display: str
    start_minutes: int
    duration_minutes: int
    lesson_type: str
    subject: str
    teacher: str
    room: Optional[str]
    url: Optional[str]
    is_online: bool = False
    # ограничения по датам:
    excluded: bool = False  # не выбирать / ещё не началось (другой модуль)
    start_date: Optional[tuple] = None  # (month, day) — пара идёт с этой даты и далее
    only_dates: Optional[frozenset] = None  # набор (month, day) — пара только в эти даты
    reschedule: dict = field(default_factory=dict)  # (month, day) -> (hour, minute)

    def instance_for(self, d: date) -> Optional[tuple]:
        """Возвращает (time_display, start_minutes) если пара идёт в дату d, иначе None."""
        if self.excluded:
            return None
        key = (d.month, d.day)
        if self.only_dates is not None:
            if key not in self.only_dates:
                return None
        elif self.start_date is not None:
            if key < self.start_date:
                return None

        if key in self.reschedule:
            h, m = self.reschedule[key]
            new_start = h * 60 + m
            new_end = new_start + self.duration_minutes
            display = f"{h}:{m:02d}–{new_end // 60}:{new_end % 60:02d}"
            return display, new_start

        return self.time_display, self.start_minutes


def _parse_time_range(label: str) -> tuple[str, int, int]:
    """'9.30-10.50' -> ('9:30–10:50', 570, 80)"""
    m = re.match(r"(\d{1,2})[.:](\d{2})\s*-\s*(\d{1,2})[.:](\d{2})", label.strip())
    if not m:
        return label.strip(), 0, 90
    h1, m1, h2, m2 = m.groups()
    start_minutes = int(h1) * 60 + int(m1)
    end_minutes = int(h2) * 60 + int(m2)
    display = f"{int(h1)}:{m1}–{int(h2)}:{m2}"
    return display, start_minutes, max(end_minutes - start_minutes, 0)


def _resolve_cell(tab: SheetTab, row: int, col: int) -> str:
    val = tab.value(row, col)
    if val:
        return val
    merge = tab.merge_at(row, col)
    if merge:
        sr, _er, sc, _ec = merge
        return tab.value(sr, sc)
    return ""


def _parse_date_constraints(rest: str) -> dict:
    lines = [ln.strip() for ln in rest.split("\n") if ln.strip()]

    excluded = False
    start_date = None
    only_dates = None
    reschedule = {}

    for line in lines:
        if NOT_STARTED_RE.search(line) or SKIP_SLOT_RE.search(line):
            excluded = True

        m = START_DATE_RE.match(line)
        if m:
            day, month = m.group(1), m.group(2)
            start_date = (int(month), int(day))
            continue

        if ONLY_DATES_LINE_RE.match(line):
            dates = {(int(mo), int(da)) for da, mo in DATE_TOKEN_RE.findall(line)}
            if dates:
                only_dates = frozenset(dates)
            continue

        for rm in RESCHEDULE_RE.finditer(line):
            day, month, hour, minute = rm.groups()
            reschedule[(int(month), int(day))] = (int(hour), int(minute))

    return {
        "excluded": excluded,
        "start_date": start_date,
        "only_dates": only_dates,
        "reschedule": reschedule,
    }


def _parse_cell_text(text: str) -> Optional[dict]:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip() != ""]
    if not lines:
        return None
    m = TYPE_RE.match(lines[0])
    if not m:
        return None
    lesson_type, subject = m.group(1), m.group(2).strip()
    teacher = lines[1].strip() if len(lines) > 1 else ""
    is_online = bool(ONLINE_MARK_RE.match(teacher))
    if is_online:
        teacher = ""
    elif any(ONLINE_MARK_RE.match(ln) for ln in lines[2:]):
        # "Онлайн" отдельной строкой после имени преподавателя (а не вместо него).
        is_online = True
    rest = "\n".join(lines[2:])
    room_match = ROOM_RE.search(rest)
    url_match = URL_RE.search(rest)
    constraints = _parse_date_constraints(rest)
    return {
        "type": lesson_type,
        "subject": subject,
        "teacher": teacher,
        "room": room_match.group(1) if room_match else None,
        "url": url_match.group(0) if url_match else None,
        "is_online": is_online,
        **constraints,
    }


def _find_group_columns(tabs: list[SheetTab], group: str) -> tuple[SheetTab, int, int]:
    """Возвращает (tab, header_row, target_col) для искомой подгруппы."""
    group = group.strip()
    if "-" not in group:
        raise GroupNotFoundError(
            f"Не удалось разобрать номер группы «{group}». Нужен формат вроде 2615-2."
        )

    for tab in tabs:
        for row_idx, row in enumerate(tab.grid):
            for col_idx, val in enumerate(row):
                if val and val.strip() == group:
                    return tab, row_idx, col_idx

    raise GroupNotFoundError(
        f"Группа «{group}» не найдена в таблице. Проверьте номер в настройках бота."
    )


def _templates_by_day(tabs: list[SheetTab], group: str) -> dict[str, list[_LessonTemplate]]:
    tab, header_row, target_col = _find_group_columns(tabs, group)

    result: dict[str, list[_LessonTemplate]] = {d: [] for d in DAY_LABELS}

    for r in range(header_row + 1, tab.row_count()):
        day_label = _resolve_cell(tab, r, 0).strip().upper()
        time_label = tab.value(r, 1).strip()
        if day_label not in DAY_LABELS or not time_label:
            continue

        time_display, start_minutes, duration = _parse_time_range(time_label)

        cell_text = tab.value(r, target_col)
        merge = tab.merge_at(r, target_col)

        if not cell_text:
            if merge:
                sr, _er, sc, _ec = merge
                cell_text = tab.value(sr, sc)
            if not cell_text:
                continue

        parsed = _parse_cell_text(cell_text)
        if not parsed:
            continue

        result[day_label].append(
            _LessonTemplate(
                time_label=time_label,
                time_display=time_display,
                start_minutes=start_minutes,
                duration_minutes=duration,
                lesson_type=parsed["type"],
                subject=parsed["subject"],
                teacher=parsed["teacher"],
                room=parsed["room"],
                url=parsed["url"],
                is_online=parsed["is_online"],
                excluded=parsed["excluded"],
                start_date=parsed["start_date"],
                only_dates=parsed["only_dates"],
                reschedule=parsed["reschedule"],
            )
        )

    return result


@dataclass
class DaySchedule:
    date: date
    day_label: str
    day_name: str
    lessons: list[Lesson]


def build_schedule(
    tabs: list[SheetTab], group: str, days: int = 7, start: Optional[date] = None
) -> list[DaySchedule]:
    """Расписание на `days` дней подряд (без воскресений), начиная с `start`
    (по умолчанию сегодня). Воскресенье пропускается совсем, поэтому итоговый
    диапазон календарных дат может быть немного шире `days`.

    Учитывает пометки в ячейках о том, что пара идёт не каждую неделю: "С DD.MM"
    (с этой даты и далее), список конкретных дат ("DD.MM, DD.MM"), "со 2 модуля"
    (ещё не началась) и разовый перенос времени ("DD.MM перенос на HH:MM").
    """
    start = start or date.today()
    by_day = _templates_by_day(tabs, group)

    schedule = []
    d = start
    while len(schedule) < days:
        label = DAY_LABELS[d.weekday()]
        if label == "ВС":
            d += timedelta(days=1)
            continue

        lessons = []
        for tpl in by_day.get(label, []):
            instance = tpl.instance_for(d)
            if instance is None:
                continue
            time_display, start_minutes = instance
            lessons.append(
                Lesson(
                    day_label=label,
                    time_label=tpl.time_label,
                    start_minutes=start_minutes,
                    duration_minutes=tpl.duration_minutes,
                    time_display=time_display,
                    lesson_type=tpl.lesson_type,
                    subject=tpl.subject,
                    teacher=tpl.teacher,
                    room=tpl.room,
                    url=tpl.url,
                    is_online=tpl.is_online,
                )
            )
        lessons.sort(key=lambda l: l.start_minutes)

        schedule.append(
            DaySchedule(date=d, day_label=label, day_name=DAY_NAMES_FULL[label], lessons=lessons)
        )
        d += timedelta(days=1)
    return schedule
