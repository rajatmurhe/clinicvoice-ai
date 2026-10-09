"""Scheduling adapter interface.

One interface, several backends. A clinic's config selects the adapter
(scheduling.adapter in clinics/<id>.json): google (the real Google Calendar
integration), fake (SQLite backed, for tests and demos) or fhir (a public FHIR
sandbox, Appointment resources). The adapter interface is what a second
scheduling system onboards through.
"""

from abc import ABC, abstractmethod

import os


class SchedulingAdapter(ABC):
    @abstractmethod
    def get_available_slots(self, date_str, duration_minutes=30, doctor=None):
        """Return free 30 minute slot strings ('09:00 AM') for a date."""

    @abstractmethod
    def book_appointment(self, date_str, time_str, patient_name, duration_minutes=30, doctor=None):
        """Create an appointment, idempotent for the same slot and patient. Returns the event id."""

    @abstractmethod
    def find_appointments_by_name(self, patient_name, days_ahead=30):
        """Upcoming appointments (next N days) for a patient name, sorted by start."""

    @abstractmethod
    def cancel_appointment(self, event_id):
        """Cancel an appointment by id."""


class GoogleCalendarAdapter(SchedulingAdapter):
    """The original Google Calendar implementation, unchanged behind the interface."""

    def get_available_slots(self, date_str, duration_minutes=30, doctor=None):
        import calendar_service

        return calendar_service._google_get_available_slots(date_str, duration_minutes, doctor)

    def book_appointment(self, date_str, time_str, patient_name, duration_minutes=30, doctor=None):
        import calendar_service

        return calendar_service._google_book_appointment(date_str, time_str, patient_name, duration_minutes, doctor)

    def find_appointments_by_name(self, patient_name, days_ahead=30):
        import calendar_service

        return calendar_service._google_find_appointments_by_name(patient_name, days_ahead)

    def cancel_appointment(self, event_id):
        import calendar_service

        return calendar_service._google_cancel_appointment(event_id)


class FakeSqliteAdapter(SchedulingAdapter):
    """SQLite backed calendar sharing one state across processes."""

    def __init__(self, db_path=None):
        from fake_calendar import FakeCalendar

        self._calendar = FakeCalendar(db_path)

    def get_available_slots(self, date_str, duration_minutes=30, doctor=None):
        return self._calendar.get_available_slots(date_str, duration_minutes=duration_minutes, doctor=doctor)

    def book_appointment(self, date_str, time_str, patient_name, duration_minutes=30, doctor=None):
        return self._calendar.book_appointment(date_str, time_str, patient_name, duration_minutes=duration_minutes, doctor=doctor)

    def find_appointments_by_name(self, patient_name, days_ahead=30):
        return self._calendar.find_appointments_by_name(patient_name, days_ahead=days_ahead)

    def cancel_appointment(self, event_id):
        return self._calendar.cancel_appointment(event_id)


FHIR_BASE = "https://hapi.fhir.org/baseR4"


class FhirSandboxAdapter(SchedulingAdapter):
    """Appointments on a public FHIR R4 sandbox (HAPI), as a second real
    integration. Summaries carry the patient name so the find by name
    behavior matches the other adapters."""

    def __init__(self, base_url=None):
        import requests

        self._requests = requests
        self.base_url = base_url or FHIR_BASE

    def _headers(self):
        return {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}

    def get_available_slots(self, date_str, duration_minutes=30, doctor=None):
        day_start = date_str + "T00:00:00+00:00"
        day_end = date_str + "T23:59:59+00:00"
        bundle = self._requests.get(
            self.base_url + "/Appointment",
            params={"date": ["ge" + day_start, "le" + day_end], "_count": 200},
            headers=self._headers(),
            timeout=15,
        )
        bundle.raise_for_status()
        busy = []
        for entry in bundle.json().get("entry", []):
            appt = entry.get("resource", {})
            if appt.get("status") not in ("booked", "arrived", "fulfilled"):
                continue
            if doctor and doctor.lower() not in json_dumps(appt).lower():
                continue
            start = appt.get("start")
            end = appt.get("end")
            if start and end:
                busy.append((start, end))
        import datetime

        slots = []
        current = datetime.datetime.fromisoformat(date_str + "T09:00:00+05:30")
        day_close = datetime.datetime.fromisoformat(date_str + "T18:00:00+05:30")
        while current + datetime.timedelta(minutes=duration_minutes) <= day_close:
            iso_start = current.isoformat()
            overlaps = any(iso_start < e and (current + datetime.timedelta(minutes=duration_minutes)).isoformat() > s for s, e in busy)
            if not overlaps:
                slots.append(current.strftime("%I:%M %p"))
            current += datetime.timedelta(minutes=duration_minutes)
        return slots

    def book_appointment(self, date_str, time_str, patient_name, duration_minutes=30, doctor=None):
        import datetime

        start = datetime.datetime.strptime(date_str + " " + time_str, "%Y-%m-%d %I:%M %p").replace(
            tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        )
        end = start + datetime.timedelta(minutes=duration_minutes)
        summary = "Appointment - " + patient_name
        if doctor:
            summary = summary + " (" + doctor + ")"
        appointment = {
            "resourceType": "Appointment",
            "status": "booked",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "comment": summary,
            "participant": [{"actor": {"display": patient_name}, "status": "accepted"}],
        }
        created = self._requests.post(
            self.base_url + "/Appointment", json=appointment, headers=self._headers(), timeout=15
        )
        created.raise_for_status()
        return created.json().get("id", "")

    def find_appointments_by_name(self, patient_name, days_ahead=30):
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc)
        time_max = now + datetime.timedelta(days=days_ahead)
        bundle = self._requests.get(
            self.base_url + "/Appointment",
            params={
                "status": "booked",
                "date": ["ge" + now.strftime("%Y-%m-%d"), "le" + time_max.strftime("%Y-%m-%d")],
                "_count": 200,
            },
            headers=self._headers(),
            timeout=15,
        )
        bundle.raise_for_status()
        matches = []
        for entry in bundle.json().get("entry", []):
            appt = entry.get("resource", {})
            comment = appt.get("comment", "") or ""
            if patient_name.lower() not in comment.lower():
                continue
            start = appt.get("start", "")
            try:
                start_dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
            except ValueError:
                continue
            if now <= start_dt <= time_max:
                matches.append({"id": appt.get("id", ""), "summary": comment, "start": start})
        matches.sort(key=lambda m: m["start"])
        return matches

    def cancel_appointment(self, event_id):
        got = self._requests.get(
            self.base_url + "/Appointment/" + str(event_id), headers=self._headers(), timeout=15
        )
        got.raise_for_status()
        appt = got.json()
        appt["status"] = "cancelled"
        updated = self._requests.put(
            self.base_url + "/Appointment/" + str(event_id), json=appt, headers=self._headers(), timeout=15
        )
        updated.raise_for_status()
        return True


def json_dumps(obj):
    import json

    return json.dumps(obj)


_ADAPTER_CACHE = {}


def get_adapter(clinic_id=None):
    from clinic_config import load_clinic

    cid = clinic_id or "default"
    if cid in _ADAPTER_CACHE:
        return _ADAPTER_CACHE[cid]
    settings = load_clinic(cid).get("scheduling", {})
    kind = settings.get("adapter", "google")
    # Test and CI override: force the SQLite fake for every clinic.
    if os.environ.get("CLINICVOICE_CALENDAR_MODE") == "fake":
        kind = "fake"
    if kind == "google":
        adapter = GoogleCalendarAdapter()
    elif kind == "fake":
        if cid == "default":
            db_path = None  # default path for continuity with earlier runs
        else:
            data_dir = os.environ.get("CLINICVOICE_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(data_dir, "fake-calendar-%s.db" % cid)
        adapter = FakeSqliteAdapter(db_path)
    elif kind == "fhir":
        adapter = FhirSandboxAdapter(settings.get("base_url"))
    else:
        raise ValueError("Unknown scheduling adapter: " + kind)
    _ADAPTER_CACHE[cid] = adapter
    return adapter
