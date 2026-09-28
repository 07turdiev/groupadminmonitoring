import asyncio
import logging
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    User,
)

import config
import db
from excel import build_excel
from reports import build_report

log = logging.getLogger("monitor")
router = Router()

GROUP_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}
ADMIN_CACHE_TTL = 600


@dataclass
class Admins:
    ids: set[int]
    # Anonim adminlar unvoni bo'yicha: {"Elbek": [User], "": [unvonsizlar]}
    anonymous: dict[str, list[User]]


@dataclass
class Author:
    id: int
    name: str
    username: str | None
    is_admin: bool


_admin_cache: dict[int, tuple[float, Admins]] = {}


async def get_admins(bot: Bot, chat_id: int) -> Admins:
    cached = _admin_cache.get(chat_id)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        members = await bot.get_chat_administrators(chat_id)
    except Exception:
        log.exception("Adminlar ro'yxatini olib bo'lmadi: %s", chat_id)
        admins = cached[1] if cached else Admins(set(), {})
    else:
        admins = Admins({m.user.id for m in members if not m.user.is_bot}, {})
        for m in members:
            if getattr(m, "is_anonymous", False) and not m.user.is_bot:
                admins.anonymous.setdefault(getattr(m, "custom_title", None) or "", []).append(m.user)
    _admin_cache[chat_id] = (time.monotonic() + ADMIN_CACHE_TTL, admins)
    return admins


def chat_allowed(chat_id: int) -> bool:
    return not config.ALLOWED_CHATS or chat_id in config.ALLOWED_CHATS


def pseudo_id(title: str) -> int:
    """Akkaunti aniqlanmagan anonim admin uchun unvon bo'yicha doimiy ID (Telegram ID lari bilan to'qnashmaydi)."""
    return -10**15 - zlib.crc32(title.encode())


async def get_author(bot: Bot, message: Message) -> Author | None:
    """Xabar muallifi. Kanal nomidan va botlar yozgan xabarlar uchun None."""
    chat_id = message.chat.id
    if message.sender_chat:
        if message.sender_chat.id != chat_id:
            return None
        # Anonim admin: Telegram faqat uning unvonini (author_signature) beradi,
        # haqiqiy akkauntini adminlar ro'yxatidan shu unvon orqali topamiz
        title = message.author_signature or ""
        matches = (await get_admins(bot, chat_id)).anonymous.get(title, [])
        if len(matches) == 1:
            return Author(matches[0].id, matches[0].full_name, matches[0].username, True)
        log.info("Anonim admin aniqlanmadi: unvon=%r, mos adminlar=%d", title, len(matches))
        if title:
            return Author(pseudo_id(title), f"Anonim admin «{title}»", None, True)
        return Author(chat_id, "Anonim admin", None, True)
    user = message.from_user
    if not user or user.is_bot:
        return None
    return Author(user.id, user.full_name, user.username, user.id in (await get_admins(bot, chat_id)).ids)


def real_reply(message: Message) -> Message | None:
    """Forum-guruhlarda mavzudagi oddiy xabar ham mavzu boshiga "reply" bo'lib keladi — uni hisobga olmaymiz."""
    r = message.reply_to_message
    if not r or r.forum_topic_created or (message.is_topic_message and r.message_id == message.message_thread_id):
        return None
    return r


# ---------------------------------------------------------------- tugmalar (faqat SUPER_ADMINS, shaxsiy chatda)

REPORT_BUTTONS = {
    "📅 Bugun": ("day", False),
    "📅 Kecha": ("day", True),
    "🗓 Joriy hafta": ("week", False),
    "🗓 O'tgan hafta": ("week", True),
    "📆 Joriy oy": ("month", False),
    "📆 O'tgan oy": ("month", True),
}
ID_BUTTON = "🆔 Mening ID"

MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Bugun"), KeyboardButton(text="📅 Kecha")],
        [KeyboardButton(text="🗓 Joriy hafta"), KeyboardButton(text="🗓 O'tgan hafta")],
        [KeyboardButton(text="📆 Joriy oy"), KeyboardButton(text="📆 O'tgan oy")],
        [KeyboardButton(text=ID_BUTTON)],
    ],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Hisobot turini tanlang",
)

private = F.chat.type == ChatType.PRIVATE
report_admin = F.from_user.id.in_(set(config.SUPER_ADMINS))


@router.message(CommandStart(), private, report_admin)
async def cmd_start(message: Message) -> None:
    await message.answer(
        "🤖 <b>Guruh adminlari monitoringi</b>\n\n"
        "Bot guruhdagi savollarni va adminlar javoblarini (reply) hisoblab boradi.\n"
        "Kerakli hisobotni pastdagi tugmalardan tanlang.",
        reply_markup=MENU,
    )


@router.message(CommandStart(), private)
async def cmd_start_denied(message: Message) -> None:
    await message.answer(
        "⛔ Bu bot faqat belgilangan adminlar uchun.\n"
        f"Ruxsat olish uchun ID ingizni bot egasiga yuboring: <code>{message.from_user.id}</code>",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(F.text == ID_BUTTON, private, report_admin)
async def btn_id(message: Message) -> None:
    await message.answer(f"Sizning ID: <code>{message.from_user.id}</code>")


@router.message(Command("id"), F.chat.type.in_(GROUP_TYPES), report_admin)
async def cmd_group_id(message: Message) -> None:
    """Guruh ID sini bilish uchun (REPORT_CHAT_ID / ALLOWED_CHATS ga yozish uchun)."""
    await message.answer(f"Guruh ID: <code>{message.chat.id}</code>")


def excel_kb(chat_id: int, kind: str, previous: bool) -> InlineKeyboardMarkup:
    data = f"xl:{kind}:{int(previous)}:{chat_id}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Excel yuklab olish", callback_data=data)]])


@router.message(F.text.in_(REPORT_BUTTONS), private, report_admin)
async def btn_report(message: Message) -> None:
    kind, previous = REPORT_BUTTONS[message.text]
    chats = [c for c in db.list_chats() if chat_allowed(c["chat_id"])]
    if not chats:
        await message.answer("Hali birorta guruh ma'lumoti yo'q.", reply_markup=MENU)
    for c in chats:
        await message.answer(build_report(c["chat_id"], kind, previous), reply_markup=excel_kb(c["chat_id"], kind, previous))


@router.callback_query(F.data.startswith("xl:"))
async def cb_excel(call: CallbackQuery) -> None:
    if call.from_user.id not in config.SUPER_ADMINS:
        await call.answer("⛔ Ruxsat yo'q", show_alert=True)
        return
    _, kind, previous, chat_id = call.data.split(":")
    await call.answer("Excel tayyorlanmoqda...")
    content, filename = build_excel(int(chat_id), kind, previous == "1")
    # Guruhdagi avtomatik hisobotdan bosilsa ham fayl shaxsiy chatga boradi
    await call.bot.send_document(
        call.from_user.id,
        BufferedInputFile(content, filename),
        caption=f"👥 {escape(db.chat_title(int(chat_id)))}",
    )


# ---------------------------------------------------------------- kuzatuv

MEDIA_NAMES = {
    "photo": "rasm", "video": "video", "voice": "ovozli xabar", "video_note": "video xabar",
    "document": "fayl", "audio": "audio", "sticker": "stiker", "animation": "GIF",
    "location": "joylashuv", "contact": "kontakt", "poll": "so'rovnoma",
}


def message_text(message: Message) -> str:
    text = message.text or message.caption or ""
    if message.content_type != "text":
        media = MEDIA_NAMES.get(message.content_type, message.content_type)
        text = f"[{media}] {text}".strip()
    return text


@router.message(F.chat.type.in_(GROUP_TYPES))
async def track(message: Message, bot: Bot) -> None:
    if not chat_allowed(message.chat.id):
        return
    author = await get_author(bot, message)
    if author is None:
        return

    db.save_chat(message.chat.id, message.chat.title or str(message.chat.id))
    db.save_user(author.id, author.name, author.username)
    ts = int(message.date.timestamp())

    if author.is_admin:
        reply = real_reply(message)
        if reply is None:
            return
        asker = await get_author(bot, reply)
        if asker is None or asker.is_admin:
            return  # adminlar o'rtasidagi yozishma yoki bot xabariga javob
        db.add_reply(message.chat.id, message.message_id, author.id, reply.message_id, ts, message_text(message))
        return

    text = message.text or message.caption or ""
    if text.startswith("/"):
        return
    if config.QUESTION_MODE == "mark" and "?" not in text:
        return
    db.add_question(message.chat.id, message.message_id, author.id, ts, message_text(message))


# ---------------------------------------------------------------- avtomatik hisobotlar

async def send_scheduled(bot: Bot, kinds: list[str]) -> None:
    targets = [config.REPORT_CHAT_ID] if config.REPORT_CHAT_ID else config.SUPER_ADMINS
    for c in db.list_chats():
        if not chat_allowed(c["chat_id"]):
            continue
        for kind in kinds:
            text = build_report(c["chat_id"], kind, previous=True)
            for target in targets:
                try:
                    await bot.send_message(target, text, reply_markup=excel_kb(c["chat_id"], kind, True))
                except Exception:
                    log.exception("Hisobotni yuborib bo'lmadi: %s", target)


async def scheduler(bot: Bot) -> None:
    hour, minute = map(int, config.REPORT_TIME.split(":"))
    while True:
        now = datetime.now(config.TZ)
        run_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run_at <= now:
            run_at += timedelta(days=1)
        await asyncio.sleep((run_at - now).total_seconds())

        kinds = ["day"]
        if run_at.weekday() == 0:
            kinds.append("week")
        if run_at.day == 1:
            kinds.append("month")
        log.info("Avtomatik hisobot: %s", kinds)
        await send_scheduled(bot, kinds)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN .env faylida ko'rsatilmagan")

    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    # Eski buyruqlar menyusini tozalaymiz — endi hammasi tugmalar orqali
    for scope in (BotCommandScopeDefault(), BotCommandScopeAllGroupChats(), BotCommandScopeAllPrivateChats()):
        await bot.delete_my_commands(scope=scope)
    await bot.set_my_commands([BotCommand(command="start", description="Menyu")], scope=BotCommandScopeAllPrivateChats())
    if not config.SUPER_ADMINS:
        log.warning("SUPER_ADMINS bo'sh — hech kim hisobot ko'ra olmaydi. .env ga ID larni yozing.")

    asyncio.create_task(scheduler(bot))
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
