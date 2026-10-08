"""SQLite backed session store.

Replaces the in-memory SESSIONS dict so a service restart no longer erases a
booking or refill that is halfway through. State is a JSON blob per session id.
"""

import json
import os
import sqlite3
import time

_DATA_DIR = os.environ.get("CLINICVOICE_DATA_DIR") or os.path.dirname(__file__)
DB_PATH = os.path.join(_DATA_DIR, "sessions.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            updated REAL
        )
    """)
    conn.commit()
    conn.close()


def get_session(session_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT state FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row[0])
        except (ValueError, TypeError):
            return {}
    return {}


def save_session(session_id, state):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO sessions (session_id, state, updated) VALUES (?, ?, ?)",
        (session_id, json.dumps(state), time.time()),
    )
    conn.commit()
    conn.close()


init_db()
