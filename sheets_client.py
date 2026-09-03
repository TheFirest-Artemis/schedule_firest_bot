"""Загрузка и кэширование сырых данных Google-таблицы с расписанием."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from config import GOOGLE_API_KEY, SHEET_CACHE_TTL_SECONDS, SPREADSHEET_ID

logger = logging.getLogger(__name__)

SHEETS_API_URL = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
FIELDS_MASK = "sheets(properties(sheetId,title,index),merges,data.rowData.values.formattedValue)"


@dataclass
class SheetTab:
    title: str
    sheet_id: int
    grid: list  # list[list[str]]
    merges: list  # list[tuple[int,int,int,int]] start_row,end_row,start_col,end_col (end excl.)

    def value(self, row: int, col: int) -> str:
        if 0 <= row < len(self.grid):
            r = self.grid[row]
            if 0 <= col < len(r):
                return r[col] or ""
        return ""

    def merge_at(self, row: int, col: int) -> Optional[tuple]:
        for m in self.merges:
            sr, er, sc, ec = m
            if sr <= row < er and sc <= col < ec:
                return m
        return None

    def row_count(self) -> int:
        return len(self.grid)


class SheetCache:
    def __init__(self):
        self._tabs: list[SheetTab] = []
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    def age(self) -> float:
        if self._fetched_at == 0.0:
            return float("inf")
        return time.time() - self._fetched_at

    def is_stale(self) -> bool:
        return self.age() >= SHEET_CACHE_TTL_SECONDS

    async def get_tabs(self, force: bool = False) -> list[SheetTab]:
        async with self._lock:
            if not force and self._tabs and not self.is_stale():
                return self._tabs
            try:
                tabs = await asyncio.get_running_loop().run_in_executor(None, self._fetch)
                self._tabs = tabs
                self._fetched_at = time.time()
            except Exception:
                logger.exception("Не удалось обновить расписание из Google Sheets")
                if self._tabs:
                    return self._tabs
                raise
            return self._tabs

    def last_updated(self) -> Optional[float]:
        return self._fetched_at or None

    def _fetch(self) -> list:
        if not GOOGLE_API_KEY:
            raise RuntimeError(
                "GOOGLE_API_KEY не задан в .env — без него бот не может обращаться "
                "к Google Sheets API. См. README."
            )
        resp = requests.get(
            SHEETS_API_URL,
            params={"key": GOOGLE_API_KEY, "fields": FIELDS_MASK},
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()

        tabs = []
        for sheet in payload.get("sheets", []):
            props = sheet.get("properties", {})
            title = props.get("title", "")
            sheet_id = props.get("sheetId", 0)

            grid = []
            data_blocks = sheet.get("data", [])
            row_data = data_blocks[0].get("rowData", []) if data_blocks else []
            for row in row_data:
                values = row.get("values", [])
                grid.append([v.get("formattedValue", "") for v in values])

            merges = []
            for m in sheet.get("merges", []):
                merges.append(
                    (
                        m.get("startRowIndex", 0),
                        m.get("endRowIndex", 0),
                        m.get("startColumnIndex", 0),
                        m.get("endColumnIndex", 0),
                    )
                )

            tabs.append(SheetTab(title=title, sheet_id=sheet_id, grid=grid, merges=merges))
        return tabs


cache = SheetCache()
