import sqlite3
from dataclasses import dataclass

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    title   TEXT
);
CREATE TABLE IF NOT EXISTS users (
    user_id   INTEGER PRIMARY KEY,
    full_name TEXT,
    username  TEXT
);
CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    created_at  INTEGER NOT NULL,
    answered_by INTEGER,
    answered_at INTEGER,
    UNIQUE (chat_id, message_id)
);
CREATE TABLE IF NOT EXISTS replies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    admin_id    INTEGER NOT NULL,
    question_id INTEGER,
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_q_chat_created ON questions (chat_id, created_at);
CREATE INDEX IF NOT EXISTS ix_q_chat_answered ON questions (chat_id, answered_at);
CREATE INDEX IF NOT EXISTS ix_r_chat_created ON replies (chat_id, created_at);
"""

_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.executescript(SCHEMA)
# Eski bazaga matn ustunlarini qo'shish
for _table in ("questions", "replies"):
    _cols = {r["name"] for r in _conn.execute(f"PRAGMA table_info({_table})")}
    if "text" not in _cols:
        _conn.execute(f"ALTER TABLE {_table} ADD COLUMN text TEXT")
_conn.commit()


def save_chat(chat_id: int, title: str) -> None:
    _conn.execute(
        "INSERT INTO chats (chat_id, title) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title",
        (chat_id, title),
    )
    _conn.commit()


def save_user(user_id: int, full_name: str, username: str | None) -> None:
    _conn.execute(
        "INSERT INTO users (user_id, full_name, username) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET full_name = excluded.full_name, username = excluded.username",
        (user_id, full_name, username),
    )
    _conn.commit()


def add_question(chat_id: int, message_id: int, user_id: int, ts: int, text: str) -> None:
    _conn.execute(
        "INSERT OR IGNORE INTO questions (chat_id, message_id, user_id, created_at, text) VALUES (?, ?, ?, ?, ?)",
        (chat_id, message_id, user_id, ts, text),
    )
    _conn.commit()


def add_reply(chat_id: int, message_id: int, admin_id: int, reply_to_id: int, ts: int, text: str) -> None:
    """Admin javobini yozadi. Savolga birinchi javob bergan admin savolni "yopgan" hisoblanadi."""
    row = _conn.execute(
        "SELECT id, answered_by FROM questions WHERE chat_id = ? AND message_id = ?",
        (chat_id, reply_to_id),
    ).fetchone()
    question_id = row["id"] if row else None
    _conn.execute(
        "INSERT INTO replies (chat_id, message_id, admin_id, question_id, created_at, text) VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, message_id, admin_id, question_id, ts, text),
    )
    if row and row["answered_by"] is None:
        _conn.execute(
            "UPDATE questions SET answered_by = ?, answered_at = ? WHERE id = ?",
            (admin_id, ts, question_id),
        )
    _conn.commit()


def list_chats() -> list[sqlite3.Row]:
    return _conn.execute("SELECT chat_id, title FROM chats ORDER BY title").fetchall()


def chat_title(chat_id: int) -> str:
    row = _conn.execute("SELECT title FROM chats WHERE chat_id = ?", (chat_id,)).fetchone()
    return row["title"] if row else str(chat_id)


@dataclass
class AdminStat:
    admin_id: int
    name: str
    username: str | None
    answered: int  # yopilgan (birinchi bo'lib javob berilgan) savollar
    replies: int  # jami javob xabarlari
    avg_response: float | None  # soniyalarda


@dataclass
class Stats:
    total_questions: int
    answered: int
    unanswered: int
    avg_response: float | None
    admins: list[AdminStat]


def get_stats(chat_id: int, start: int, end: int) -> Stats:
    q = _conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(answered_by IS NOT NULL) AS answered,
               AVG(CASE WHEN answered_by IS NOT NULL THEN answered_at - created_at END) AS avg_resp
        FROM questions WHERE chat_id = ? AND created_at >= ? AND created_at < ?
        """,
        (chat_id, start, end),
    ).fetchone()
    total = q["total"] or 0
    answered = q["answered"] or 0

    rows = _conn.execute(
        """
        WITH a AS (
            SELECT answered_by AS admin_id, COUNT(*) AS answered,
                   AVG(answered_at - created_at) AS avg_resp
            FROM questions
            WHERE chat_id = ? AND answered_at >= ? AND answered_at < ?
            GROUP BY answered_by
        ), r AS (
            SELECT admin_id, COUNT(*) AS replies
            FROM replies
            WHERE chat_id = ? AND created_at >= ? AND created_at < ?
            GROUP BY admin_id
        ), ids AS (
            SELECT admin_id FROM a UNION SELECT admin_id FROM r
        )
        SELECT ids.admin_id, COALESCE(a.answered, 0) AS answered, COALESCE(r.replies, 0) AS replies,
               a.avg_resp, u.full_name, u.username
        FROM ids
        LEFT JOIN a ON a.admin_id = ids.admin_id
        LEFT JOIN r ON r.admin_id = ids.admin_id
        LEFT JOIN users u ON u.user_id = ids.admin_id
        ORDER BY answered DESC, replies DESC
        """,
        (chat_id, start, end, chat_id, start, end),
    ).fetchall()

    admins = [
        AdminStat(
            admin_id=r["admin_id"],
            name=r["full_name"] or str(r["admin_id"]),
            username=r["username"],
            answered=r["answered"],
            replies=r["replies"],
            avg_response=r["avg_resp"],
        )
        for r in rows
    ]
    return Stats(total, answered, total - answered, q["avg_resp"], admins)


def get_questions(chat_id: int, start: int, end: int) -> list[sqlite3.Row]:
    """Davrda kelgan savollar: kim so'ragan, qaysi admin birinchi javob bergan va javob matni."""
    return _conn.execute(
        """
        SELECT q.message_id, q.created_at, q.text, q.answered_at, q.answered_by,
               au.full_name AS asker_name, au.username AS asker_username,
               ad.full_name AS admin_name, ad.username AS admin_username,
               (SELECT r.text FROM replies r
                 WHERE r.question_id = q.id AND r.admin_id = q.answered_by
                 ORDER BY r.created_at, r.id LIMIT 1) AS answer_text,
               (SELECT COUNT(*) FROM replies r WHERE r.question_id = q.id) AS reply_count
        FROM questions q
        LEFT JOIN users au ON au.user_id = q.user_id
        LEFT JOIN users ad ON ad.user_id = q.answered_by
        WHERE q.chat_id = ? AND q.created_at >= ? AND q.created_at < ?
        ORDER BY q.created_at
        """,
        (chat_id, start, end),
    ).fetchall()


def get_replies(chat_id: int, start: int, end: int) -> list[sqlite3.Row]:
    """Davrdagi barcha admin javoblari va ular qaysi savolga yozilgani."""
    return _conn.execute(
        """
        SELECT r.message_id, r.created_at, r.text, r.admin_id,
               ad.full_name AS admin_name, ad.username AS admin_username,
               q.created_at AS q_created_at, q.text AS q_text,
               au.full_name AS asker_name, au.username AS asker_username
        FROM replies r
        LEFT JOIN users ad ON ad.user_id = r.admin_id
        LEFT JOIN questions q ON q.id = r.question_id
        LEFT JOIN users au ON au.user_id = q.user_id
        WHERE r.chat_id = ? AND r.created_at >= ? AND r.created_at < ?
        ORDER BY ad.full_name, r.created_at
        """,
        (chat_id, start, end),
    ).fetchall()
