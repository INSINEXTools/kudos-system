"""Database layer for the Kudos System using SQLite."""

import html
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

MAX_MESSAGE_LENGTH = 500
DUPLICATE_WINDOW_MINUTES = 5


def get_connection(db_path: str = "kudos.db") -> sqlite3.Connection:
    """Create and return a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = "kudos.db", seed: bool = True) -> None:
    """Initialize database tables and optionally seed sample employees."""
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                department TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('employee', 'admin')) DEFAULT 'employee',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kudos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_visible BOOLEAN NOT NULL DEFAULT 1,
                moderated_by INTEGER,
                moderated_at TEXT,
                reason_for_moderation TEXT,
                FOREIGN KEY (sender_id) REFERENCES users(id),
                FOREIGN KEY (recipient_id) REFERENCES users(id),
                FOREIGN KEY (moderated_by) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_kudos_visible_created
                ON kudos(is_visible, created_at DESC);
            """
        )

        if seed:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count == 0:
                now = datetime.now(timezone.utc).isoformat()
                sample_users = [
                    ("Alex Rivera", "alex.rivera@datacom.com", "Engineering", "employee", now),
                    ("Priya Patel", "priya.patel@datacom.com", "Engineering", "employee", now),
                    ("Liam Chen", "liam.chen@datacom.com", "Product", "employee", now),
                    ("Sofia Morales", "sofia.morales@datacom.com", "Design", "employee", now),
                    ("Jordan Taylor", "jordan.taylor@datacom.com", "People & Culture", "admin", now),
                ]
                conn.executemany(
                    """
                    INSERT INTO users (name, email, department, role, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    sample_users,
                )
                sample_kudos = [
                    (
                        1,
                        2,
                        "Huge thanks for staying late to help debug the nightly data pipeline!",
                        now,
                        1,
                    ),
                    (
                        3,
                        4,
                        "The new onboarding mockups look super clean and intuitive. Great work!",
                        now,
                        1,
                    ),
                ]
                conn.executemany(
                    """
                    INSERT INTO kudos (sender_id, recipient_id, message, created_at, is_visible)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    sample_kudos,
                )


def list_users(db_path: str = "kudos.db") -> List[Dict[str, Any]]:
    """Return all users sorted alphabetically by name."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, name, email, department, role FROM users ORDER BY name ASC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_user_by_id(user_id: int, db_path: str = "kudos.db") -> Optional[Dict[str, Any]]:
    """Fetch a single user by ID."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT id, name, email, department, role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def create_kudos(
    sender_id: int,
    recipient_id: int,
    message: str,
    db_path: str = "kudos.db",
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validate and insert a new kudos record. Returns (kudos_dict, error_message)."""
    if sender_id == recipient_id:
        return None, "You cannot send kudos to yourself."

    cleaned_message = (message or "").strip()
    if not cleaned_message:
        return None, "Message cannot be empty."
    if len(cleaned_message) > MAX_MESSAGE_LENGTH:
        return None, f"Message cannot exceed {MAX_MESSAGE_LENGTH} characters."

    sanitized_message = html.escape(cleaned_message)

    with get_connection(db_path) as conn:
        sender = conn.execute("SELECT id FROM users WHERE id = ?", (sender_id,)).fetchone()
        recipient = conn.execute("SELECT id FROM users WHERE id = ?", (recipient_id,)).fetchone()
        if not sender or not recipient:
            return None, "Invalid sender or recipient."

        # Prevent duplicate submissions within DUPLICATE_WINDOW_MINUTES
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)).isoformat()
        duplicate = conn.execute(
            """
            SELECT id FROM kudos
            WHERE sender_id = ? AND recipient_id = ? AND message = ? AND created_at >= ?
            """,
            (sender_id, recipient_id, sanitized_message, cutoff),
        ).fetchone()
        if duplicate:
            return None, "Duplicate kudos detected. Please wait before sending the same message again."

        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO kudos (sender_id, recipient_id, message, created_at, is_visible)
            VALUES (?, ?, ?, ?, 1)
            """,
            (sender_id, recipient_id, sanitized_message, now),
        )
        kudos_id = cursor.lastrowid
        row = conn.execute(
            """
            SELECT k.id, k.sender_id, s.name AS sender_name,
                   k.recipient_id, r.name AS recipient_name, r.department AS recipient_department,
                   k.message, k.created_at, k.is_visible,
                   k.moderated_by, m.name AS moderated_by_name,
                   k.moderated_at, k.reason_for_moderation
            FROM kudos k
            JOIN users s ON k.sender_id = s.id
            JOIN users r ON k.recipient_id = r.id
            LEFT JOIN users m ON k.moderated_by = m.id
            WHERE k.id = ?
            """,
            (kudos_id,),
        ).fetchone()
        return dict(row), None


def list_kudos(
    include_hidden: bool = False,
    page: int = 1,
    per_page: int = 10,
    db_path: str = "kudos.db",
) -> Dict[str, Any]:
    """Return paginated kudos feed. Hidden items are only returned when include_hidden=True."""
    page = max(1, page)
    per_page = max(1, min(50, per_page))
    offset = (page - 1) * per_page

    where_clause = "" if include_hidden else "WHERE k.is_visible = 1"

    with get_connection(db_path) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM kudos k {where_clause}"
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT k.id, k.sender_id, s.name AS sender_name,
                   k.recipient_id, r.name AS recipient_name, r.department AS recipient_department,
                   k.message, k.created_at, k.is_visible,
                   k.moderated_by, m.name AS moderated_by_name,
                   k.moderated_at, k.reason_for_moderation
            FROM kudos k
            JOIN users s ON k.sender_id = s.id
            JOIN users r ON k.recipient_id = r.id
            LEFT JOIN users m ON k.moderated_by = m.id
            {where_clause}
            ORDER BY k.created_at DESC, k.id DESC
            LIMIT ? OFFSET ?
            """,
            (per_page, offset),
        ).fetchall()

        return {
            "items": [dict(row) for row in rows],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        }


def moderate_kudos(
    kudos_id: int,
    admin_id: int,
    is_visible: bool,
    reason: str = "",
    db_path: str = "kudos.db",
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Hide or restore a kudos message. Requires an admin user."""
    with get_connection(db_path) as conn:
        admin = conn.execute(
            "SELECT id, role FROM users WHERE id = ?", (admin_id,)
        ).fetchone()
        if not admin or admin["role"] != "admin":
            return None, "Forbidden: Administrator privileges required."

        existing = conn.execute(
            "SELECT id FROM kudos WHERE id = ?", (kudos_id,)
        ).fetchone()
        if not existing:
            return None, "Kudos message not found."

        cleaned_reason = html.escape((reason or "").strip())
        if not is_visible and not cleaned_reason:
            return None, "A moderation reason is required when hiding a message."

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE kudos
            SET is_visible = ?,
                moderated_by = ?,
                moderated_at = ?,
                reason_for_moderation = ?
            WHERE id = ?
            """,
            (1 if is_visible else 0, admin_id, now, cleaned_reason or None, kudos_id),
        )

        row = conn.execute(
            """
            SELECT k.id, k.sender_id, s.name AS sender_name,
                   k.recipient_id, r.name AS recipient_name, r.department AS recipient_department,
                   k.message, k.created_at, k.is_visible,
                   k.moderated_by, m.name AS moderated_by_name,
                   k.moderated_at, k.reason_for_moderation
            FROM kudos k
            JOIN users s ON k.sender_id = s.id
            JOIN users r ON k.recipient_id = r.id
            LEFT JOIN users m ON k.moderated_by = m.id
            WHERE k.id = ?
            """,
            (kudos_id,),
        ).fetchone()
        return dict(row), None


def delete_kudos(
    kudos_id: int,
    admin_id: int,
    db_path: str = "kudos.db",
) -> Tuple[bool, Optional[str]]:
    """Permanently delete a kudos message. Requires an admin user."""
    with get_connection(db_path) as conn:
        admin = conn.execute(
            "SELECT id, role FROM users WHERE id = ?", (admin_id,)
        ).fetchone()
        if not admin or admin["role"] != "admin":
            return False, "Forbidden: Administrator privileges required."

        cursor = conn.execute("DELETE FROM kudos WHERE id = ?", (kudos_id,))
        if cursor.rowcount == 0:
            return False, "Kudos message not found."
        return True, None
