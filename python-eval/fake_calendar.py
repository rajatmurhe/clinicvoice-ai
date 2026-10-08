"""Deterministic in-memory calendar used by the offline eval harness.

Mimics the four calendar_service functions the booking agent imports
(get_available_slots, book_appointment, find_appointments_by_name,
cancel_appointment) with no Google Calendar access and no network.
Runs 09:00 to 17:30 in 30 minute slots, Indian Standard Time, matching
the real calendar_service window.
"""

import datetime
import threading

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

DAY_START_HOUR = 9
DAY_END_HOUR = 18


class FakeCalendar:
    def __init__(self):
        self._lock = threading.Lock()
        self._events = {}
        self._next_id = 1
        self.full_days = set()

    def reset(self):
        with self._lock:
            self._events = {}
            self._next_id = 1
            self.full_days = set()

    def mark_full_day(self, date_str):
        with self._lock:
            self.full_days.add(date_str)

    def add_event(self, date_str, time_str, patient_name, doctor=None):
        start = datetime.datetime.strptime(
            date_str + " " + time_str, "%Y-%m-%d %I:%M %p"
        ).replace(tzinfo=IST)
        return self._insert(start, patient_name, doctor)

    def _insert(self, start_dt, patient_name, doctor=None):
        end_dt = start_dt + datetime.timedelta(minutes=30)
        with self._lock:
            event_id = str(self._next_id)
            self._next_id += 1
            summary = "Appointment - " + patient_name
            if doctor:
                summary = summary + " (" + doctor + ")"
            self._events[event_id] = {
                "id": event_id,
                "summary": summary,
                "start": start_dt,
                "end": end_dt,
            }
            return event_id

    def get_available_slots(self, date_str, duration_minutes=30, doctor=None):
        day_start = datetime.datetime.fromisoformat(
            date_str + "T09:00:00+05:30"
        )
        day_end = datetime.datetime.fromisoformat(date_str + "T18:00:00+05:30")

        with self._lock:
            if date_str in self.full_days:
                return []
            busy = [
                (e["start"], e["end"], e["summary"])
                for e in self._events.values()
                if day_start.date() == e["start"].date()
            ]

        available = []
        current = day_start
        slot_delta = datetime.timedelta(minutes=duration_minutes)
        while current + slot_delta <= day_end:
            slot_end = current + slot_delta
            overlaps = any(
                current < b_end and slot_end > b_start
                for b_start, b_end, _summary in busy
            )
            if overlaps and doctor:
                overlaps = any(
                    current < b_end and slot_end > b_start and doctor in summary
                    for b_start, b_end, summary in busy
                )
            if not overlaps:
                available.append(current.strftime("%I:%M %p"))
            current += slot_delta
        return available

    def book_appointment(self, date_str, time_str, patient_name, duration_minutes=30, doctor=None):
        start = datetime.datetime.strptime(
            date_str + " " + time_str, "%Y-%m-%d %I:%M %p"
        ).replace(tzinfo=IST)
        return self._insert(start, patient_name, doctor)

    def find_appointments_by_name(self, patient_name, days_ahead=30):
        now = datetime.datetime.now(IST)
        time_max = now + datetime.timedelta(days=days_ahead)
        matches = []
        with self._lock:
            for e in self._events.values():
                if patient_name.lower() in e["summary"].lower():
                    if now <= e["start"] <= time_max:
                        matches.append({
                            "id": e["id"],
                            "summary": e["summary"],
                            "start": e["start"].isoformat(),
                        })
        matches.sort(key=lambda m: m["start"])
        return matches

    def cancel_appointment(self, event_id):
        with self._lock:
            if event_id in self._events:
                del self._events[event_id]
                return True
            return False

    def events_on(self, date_str):
        with self._lock:
            return [
                {
                    "summary": e["summary"],
                    "start": e["start"].strftime("%Y-%m-%d %I:%M %p"),
                }
                for e in self._events.values()
                if e["start"].strftime("%Y-%m-%d") == date_str
            ]
