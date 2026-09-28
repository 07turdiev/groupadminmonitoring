import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _int_list(value: str) -> list[int]:
    return [int(x) for x in value.replace(" ", "").split(",") if x]


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))
DB_PATH = os.getenv("DB_PATH", "data.db")

# Hisobotni ko'ra oladigan va shaxsiy chatda barcha guruhlar hisobotini oladigan foydalanuvchilar
SUPER_ADMINS = _int_list(os.getenv("SUPER_ADMINS", ""))

# Avtomatik hisobotlar yuboriladigan chat. Bo'sh bo'lsa — SUPER_ADMINS ga shaxsiy xabar sifatida
REPORT_CHAT_ID = int(os.getenv("REPORT_CHAT_ID") or 0)

# Avtomatik hisobot vaqti (mahalliy vaqt), masalan "09:00"
REPORT_TIME = os.getenv("REPORT_TIME", "09:00")

# all  — adminmas foydalanuvchining har bir xabari savol hisoblanadi
# mark — faqat "?" belgisi bor xabarlar savol hisoblanadi
QUESTION_MODE = os.getenv("QUESTION_MODE", "all").lower()

# Faqat shu guruhlar kuzatiladi. Bo'sh bo'lsa — bot qo'shilgan barcha guruhlar
ALLOWED_CHATS = _int_list(os.getenv("ALLOWED_CHATS", ""))
