import sqlite3
import time
import os

_DATA_DIR = os.environ.get("CLINICVOICE_DATA_DIR") or os.path.dirname(__file__)
DB_PATH = os.path.join(_DATA_DIR, 'refills.db')


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS refill_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            patient_name TEXT,
            medication_mentioned TEXT,
            status TEXT DEFAULT 'pending'
        )
    ''')
    conn.commit()
    conn.close()


def log_refill_request(patient_name, medication_mentioned):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO refill_requests (timestamp, patient_name, medication_mentioned, status) VALUES (?, ?, ?, ?)',
        (time.time(), patient_name, medication_mentioned, 'pending')
    )
    conn.commit()
    conn.close()


init_db()
