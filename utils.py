import time
from typing import Optional


def humanize_ago(ts: Optional[float]) -> str:
    if not ts:
        return "только что"
    seconds = int(time.time() - ts)
    if seconds < 60:
        return "только что"
    minutes = seconds // 60
    if minutes == 1:
        return "1 минуту назад"
    if 2 <= minutes <= 4:
        return f"{minutes} минуты назад"
    return f"{minutes} минут назад"


GROUP_RE_SOURCE = r"^\d{3,4}-\d{1,2}$"
