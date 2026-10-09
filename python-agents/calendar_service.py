import datetime
import os
import time

CALENDAR_MODE = os.environ.get("CLINICVOICE_CALENDAR_MODE", "google")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
_RENDER_SECRET_PATH = "/etc/secrets/service-account-key.json"
_LOCAL_PATH = os.path.join(os.path.dirname(__file__), "service-account-key.json")
SERVICE_ACCOUNT_FILE = _RENDER_SECRET_PATH if os.path.exists(_RENDER_SECRET_PATH) else _LOCAL_PATH
CALENDAR_ID = os.environ.get(
    "CLINICVOICE_CALENDAR_ID",
    "c7a96c6fe2ec8d04973de5e5f01444a92f8208e9c9d47ea7b7ea771be0695654@group.calendar.google.com",
)

DOCTORS = ["Dr. Sharma", "Dr. Patel", "Dr. Khan"]

_fake_calendar = None


def _get_fake():
    global _fake_calendar
    if _fake_calendar is None:
        from fake_calendar import FakeCalendar

        _fake_calendar = FakeCalendar()
    return _fake_calendar


def _with_retries(call, attempts=3):
    """Retries transient calendar API failures with backoff so a blip does not
    fail a booking. Raises the last exception after the final attempt."""
    last_error = None
    for attempt in range(attempts):
        try:
            return call()
        except Exception as e:
            last_error = e
            if attempt < attempts - 1:
                time.sleep(0.4 * (2 ** attempt))
    raise last_error


def get_calendar_service():
    # Imported lazily so test and CI environments without the Google client
    # libraries can still run everything except live calendar calls.
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=credentials)


def get_available_slots(date_str, duration_minutes=30, doctor=None):
    if CALENDAR_MODE == "fake":
        return _get_fake().get_available_slots(date_str, duration_minutes=duration_minutes, doctor=doctor)

    service = get_calendar_service()

    day_start = datetime.datetime.fromisoformat(date_str + "T09:00:00+05:30")
    day_end = datetime.datetime.fromisoformat(date_str + "T18:00:00+05:30")

    events_result = _with_retries(lambda: service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime"
    ).execute())

    events = events_result.get("items", [])
    busy_slots = []
    for event in events:
        summary = event.get("summary", "")
        if doctor and doctor.lower() not in summary.lower():
            continue
        start = event["start"].get("dateTime")
        end = event["end"].get("dateTime")
        if start and end:
            busy_slots.append((
                datetime.datetime.fromisoformat(start),
                datetime.datetime.fromisoformat(end)
            ))

    available = []
    current = day_start
    slot_delta = datetime.timedelta(minutes=duration_minutes)

    while current + slot_delta <= day_end:
        slot_end = current + slot_delta
        overlaps = any(current < b_end and slot_end > b_start for b_start, b_end in busy_slots)
        if not overlaps:
            available.append(current.strftime("%I:%M %p"))
        current += slot_delta

    return available


def book_appointment(date_str, time_str, patient_name, duration_minutes=30, doctor=None):
    if CALENDAR_MODE == "fake":
        return _get_fake().book_appointment(date_str, time_str, patient_name, duration_minutes=duration_minutes, doctor=doctor)

    service = get_calendar_service()

    start_dt = datetime.datetime.strptime(date_str + " " + time_str, "%Y-%m-%d %I:%M %p")
    start_dt = start_dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)

    summary = "Appointment - " + patient_name
    if doctor:
        summary = summary + " (" + doctor + ")"

    # Idempotency: a retried request must not double book. If an event with the
    # same summary already starts at this exact time, return it unchanged.
    day_start = start_dt.replace(hour=9, minute=0, second=0)
    day_end = start_dt.replace(hour=18, minute=0, second=0)
    existing = _with_retries(lambda: service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
    ).execute())
    for event in existing.get("items", []):
        if event.get("summary") == summary and event.get("start", {}).get("dateTime", "").startswith(start_dt.isoformat()[:16]):
            return event.get("id")

    event = {
        "summary": summary,
        "start": {"dateTime": start_dt.isoformat()},
        "end": {"dateTime": end_dt.isoformat()},
    }

    created_event = _with_retries(lambda: service.events().insert(calendarId=CALENDAR_ID, body=event).execute())
    return created_event.get("id")


def find_appointments_by_name(patient_name, days_ahead=30):
    if CALENDAR_MODE == "fake":
        return _get_fake().find_appointments_by_name(patient_name, days_ahead=days_ahead)

    service = get_calendar_service()
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    time_max = now + datetime.timedelta(days=days_ahead)

    events_result = _with_retries(lambda: service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=now.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        q=patient_name
    ).execute())

    events = events_result.get("items", [])
    matches = []
    for event in events:
        summary = event.get("summary", "")
        if patient_name.lower() in summary.lower():
            start = event["start"].get("dateTime")
            matches.append({
                "id": event["id"],
                "summary": summary,
                "start": start
            })

    return matches


def cancel_appointment(event_id):
    if CALENDAR_MODE == "fake":
        return _get_fake().cancel_appointment(event_id)

    service = get_calendar_service()
    _with_retries(lambda: service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute())
    return True
