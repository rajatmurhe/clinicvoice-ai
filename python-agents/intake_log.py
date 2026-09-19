import sqlite3
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "intake.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intake_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            patient_name TEXT,
            reason_category TEXT,
            body_area TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_intake(patient_name, reason_category, body_area=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO intake_records (timestamp, patient_name, reason_category, body_area) VALUES (?, ?, ?, ?)",
        (time.time(), patient_name, reason_category, body_area)
    )
    conn.commit()
    conn.close()


init_db()
