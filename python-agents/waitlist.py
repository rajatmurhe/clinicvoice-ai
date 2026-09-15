import sqlite3
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "waitlist.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            patient_name TEXT,
            requested_date TEXT,
            doctor TEXT,
            status TEXT DEFAULT "waiting"
        )
    """)
    conn.commit()
    conn.close()


def add_to_waitlist(patient_name, requested_date, doctor=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO waitlist (timestamp, patient_name, requested_date, doctor, status) VALUES (?, ?, ?, ?, ?)",
        (time.time(), patient_name, requested_date, doctor, "waiting")
    )
    conn.commit()
    conn.close()


def get_waitlist_for_date(requested_date):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM waitlist WHERE requested_date = ? AND status = \'waiting\'",
        (requested_date,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def notify_waitlist(requested_date):
    waiting = get_waitlist_for_date(requested_date)
    for entry in waiting:
        print("WAITLIST NOTIFICATION: A slot opened on " + requested_date + " for " + entry["patient_name"] + " (would send SMS/email here in production)")
    return len(waiting)


init_db()
