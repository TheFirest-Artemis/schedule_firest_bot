import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "")

DATA_DIR = BASE_DIR / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
FONTS_DIR = BASE_DIR / "assets" / "fonts"
FONT_REGULAR = FONTS_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONTS_DIR / "DejaVuSans-Bold.ttf"

# Не запрашивать таблицу у Google чаще, чем раз в это количество секунд.
SHEET_CACHE_TTL_SECONDS = 5 * 60

SCHEDULE_DAYS_SHORT = 3  # период по умолчанию для кнопки "Получить расписание"
SCHEDULE_DAYS_WEEK = 7  # период для кнопки "Расписание на неделю"
SCHEDULE_DAYS_MIN = 1
SCHEDULE_DAYS_MAX = 14

DEFAULT_GROUP = "2615-2"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан. Заполните файл .env (см. .env.example).")
if not SPREADSHEET_ID:
    raise RuntimeError("SPREADSHEET_ID не задан. Заполните файл .env.")
if not BOT_PASSWORD:
    raise RuntimeError("BOT_PASSWORD не задан. Заполните файл .env.")
