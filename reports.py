from datetime import datetime, timedelta
from html import escape

import config
import db

MONTHS = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
]


def _midnight(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def period_bounds(kind: str, previous: bool = False, now: datetime | None = None) -> tuple[datetime, datetime, str]:
    """(boshlanish, tugash, sarlavha). previous=True — oldingi to'liq davr, aks holda joriy davr (hozirgacha)."""
    now = now or datetime.now(config.TZ)
    today = _midnight(now)

    if kind == "day":
        start = today - timedelta(days=1) if previous else today
        end = start + timedelta(days=1)
        label = f"Kunlik hisobot — {start:%d.%m.%Y}"
    elif kind == "week":
        start = today - timedelta(days=today.weekday())
        if previous:
            start -= timedelta(days=7)
        end = start + timedelta(days=7)
        label = f"Haftalik hisobot — {start:%d.%m} – {end - timedelta(days=1):%d.%m.%Y}"
    elif kind == "month":
        start = today.replace(day=1)
        if previous:
            start = (start - timedelta(days=1)).replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        label = f"Oylik hisobot — {MONTHS[start.month - 1]} {start.year}"
    else:
        raise ValueError(kind)

    if not previous:
        end = min(end, now)
    return start, end, label


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} son"
    if seconds < 3600:
        return f"{seconds // 60} daq"
    return f"{seconds // 3600} soat {seconds % 3600 // 60} daq"


def build_report(chat_id: int, kind: str, previous: bool = False) -> str:
    start, end, label = period_bounds(kind, previous)
    s = db.get_stats(chat_id, int(start.timestamp()), int(end.timestamp()))

    pct = f" ({s.answered * 100 // s.total_questions}%)" if s.total_questions else ""
    lines = [
        f"📊 <b>{label}</b>",
        f"👥 {escape(db.chat_title(chat_id))}",
        "",
        f"❓ Jami savollar: <b>{s.total_questions}</b>",
        f"✅ Javob berilgan: <b>{s.answered}</b>{pct}",
        f"⏳ Javobsiz: <b>{s.unanswered}</b>",
        f"⏱ O'rtacha javob vaqti: <b>{_fmt_duration(s.avg_response)}</b>",
        "",
    ]

    if not s.admins:
        lines.append("👮 Bu davrda adminlar javob bermagan.")
    else:
        lines.append("👮 <b>Adminlar reytingi:</b>")
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        for i, a in enumerate(s.admins):
            name = escape(a.name) + (f" (@{a.username})" if a.username else "")
            lines.append(
                f"{medals.get(i, f'{i + 1}.')} {name}\n"
                f"     savollar: <b>{a.answered}</b> · javoblar: <b>{a.replies}</b> · "
                f"o'rt. vaqt: {_fmt_duration(a.avg_response)}"
            )

    lines += ["", "<i>Savollar — javob berilgan (birinchi bo'lib reply qilingan) savollar soni; "
                  "javoblar — admin yozgan barcha reply xabarlar.</i>"]
    return "\n".join(lines)
