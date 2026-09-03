import asyncio
import json
from typing import Optional

from config import DATA_DIR, SCHEDULE_DAYS_SHORT, SETTINGS_FILE

_lock = asyncio.Lock()


def _read() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_file = SETTINGS_FILE.with_suffix(".tmp")
    with tmp_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_file.replace(SETTINGS_FILE)


async def get_group(chat_id: int) -> Optional[str]:
    async with _lock:
        data = _read()
        user = data.get(str(chat_id))
        if user:
            return user.get("group")
        return None


async def set_group(chat_id: int, group: str) -> None:
    async with _lock:
        data = _read()
        data.setdefault(str(chat_id), {})["group"] = group
        _write(data)


async def has_group(chat_id: int) -> bool:
    return (await get_group(chat_id)) is not None


async def get_default_days(chat_id: int) -> int:
    async with _lock:
        data = _read()
        user = data.get(str(chat_id))
        if user and user.get("default_days"):
            return user["default_days"]
        return SCHEDULE_DAYS_SHORT


async def set_default_days(chat_id: int, days: int) -> None:
    async with _lock:
        data = _read()
        data.setdefault(str(chat_id), {})["default_days"] = days
        _write(data)
