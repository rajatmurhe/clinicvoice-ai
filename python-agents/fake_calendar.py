"""Deterministic SQLite backed fake calendar.

Same four operations the Google Calendar implementation exposes, plus test
helpers (mark_full_day, add_event, events_on, reset). Backed by SQLite in
CLINICVOICE_DATA_DIR so separate processes (for example an MCP tool server
subprocess and the eval harness) share one calendar state.
"""

import datetime
import os
import sqlite3
import threading
import uuid

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _default_db_path():
    data_dir = os.environ.get("CLINICVOICE_DATA_DIR") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    return os.path.join(data_dir, "fake-calendar.db")


class FakeCalendar:
    def __init__(self, db_path=None):
        self.db_path = db_path or _default_db_path()
        self._lock = threading.Lock()
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS events ("
                "id TEXT PRIMARY KEY, summary TEXT, start TEXT, end TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS full_days (day TEXT PRIMARY KEY)"
            )
            conn.commit()
            conn.close()

    def reset(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM full_days")
            conn.commit()
            conn.close()

    def mark_full_day(self, date_str):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO full_days (day) VALUES (?)", (date_str,)
            )
            conn.commit()
            conn.close()

    def _parse_slot(self, date_str, time_str):
        return datetime.datetime.strptime(
            date_str + " " + time_str, "%Y-%m-%d %I:%M %p"
        ).replace(tzinfo=IST)

    def _summary_for(self, patient_name, doctor):
        summary = "Appointment - " + patient_name
        if doctor:
            summary = summary + " (" + doctor + ")"
        return summary

    def add_event(self, date_str, time_str, patient_name, doctor=None):
        return self.book_appointment(date_str, time_str, patient_name, doctor=doctor)

    def _rows(self, where="1=1", params=()):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM events WHERE " + where, params
        ).fetchall()
        conn.close()
        return rows

    def get_available_slots(self, date_str, duration_minutes=30, doctor=None, clinic_id=None):
        day_start = datetime.datetime.fromisoformat(date_str + "T09:00:00+05:30")
        day_end = datetime.datetime.fromisoformat(date_str + "T18:00:00+05:30")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if conn.execute("SELECT 1 FROM full_days WHERE day = ?", (date_str,)).fetchone():
            conn.close()
            return []
        busy = [
            (
                datetime.datetime.fromisoformat(r["start"]),
                datetime.datetime.fromisoformat(r["end"]),
                r["summary"],
            )
            for r in conn.execute("SELECT summary, start, end FROM events")
            if datetime.datetime.fromisoformat(r["start"]).date() == day_start.date()
        ]
        conn.close()

        available = []
        current = day_start
        slot_delta = datetime.timedelta(minutes=duration_minutes)
        while current + slot_delta <= day_end:
            slot_end = current + slot_delta
            overlaps = any(
                current < b_end and slot_end > b_start and (not doctor or doctor in summary)
                for b_start, b_end, summary in busy
            )
            if not overlaps:
                available.append(current.strftime("%I:%M %p"))
            current += slot_delta
        return available

    def book_appointment(self, date_str, time_str, patient_name, duration_minutes=30, doctor=None, clinic_id=None):
        start = self._parse_slot(date_str, time_str)
        end = start + datetime.timedelta(minutes=duration_minutes)
        summary = self._summary_for(patient_name, doctor)
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            existing = conn.execute(
                "SELECT id FROM events WHERE summary = ? AND start = ?",
                (summary, start.isoformat()),
            ).fetchone()
            if existing:
                event_id = existing[0]
                conn.close()
                return event_id
            event_id = uuid.uuid4().hex[:12]
            conn.execute(
                "INSERT INTO events (id, summary, start, end) VALUES (?, ?, ?, ?)",
                (event_id, summary, start.isoformat(), end.isoformat()),
            )
            conn.commit()
            conn.close()
            return event_id

    def find_appointments_by_name(self, patient_name, days_ahead=30, clinic_id=None):
        now = datetime.datetime.now(IST)
        time_max = now + datetime.timedelta(days=days_ahead)
        matches = []
        for r in self._rows():
            if patient_name.lower() in (r["summary"] or "").lower():
                start = datetime.datetime.fromisoformat(r["start"])
                if now <= start <= time_max:
                    matches.append(
                        {"id": r["id"], "summary": r["summary"], "start": r["start"]}
                    )
        matches.sort(key=lambda m: m["start"])
        return matches

    def cancel_appointment(self, event_id, clinic_id=None):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute("DELETE FROM events WHERE id = ?", (str(event_id),))
            conn.commit()
            deleted = cur.rowcount
            conn.close()
            return deleted > 0

    def ping(self):
        try:
            self._rows()
            return True
        except Exception:
            return False

    def events_on(self, date_str):
        return [
            {
                "summary": r["summary"],
                "start": datetime.datetime.fromisoformat(r["start"]).strftime(
                    "%Y-%m-%d %I:%M %p"
                ),
            }
            for r in self._rows()
            if datetime.datetime.fromisoformat(r["start"]).strftime("%Y-%m-%d") == date_str
        ]
