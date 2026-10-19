import os
import sqlite3

import pytest

from fake_calendar import FakeCalendar
from agents import booking_agent
from agents.booking_agent import handle_booking
from waitlist import add_to_waitlist


@pytest.fixture()
def cal(monkeypatch):
    fake = FakeCalendar()
    monkeypatch.setattr(booking_agent, "get_available_slots", fake.get_available_slots)
    monkeypatch.setattr(booking_agent, "book_appointment", fake.book_appointment)
    monkeypatch.setattr(booking_agent, "find_appointments_by_name", fake.find_appointments_by_name)
    monkeypatch.setattr(booking_agent, "cancel_appointment", fake.cancel_appointment)
    return fake


def new_session():
    return {}


def test_happy_path_booking(cal):
    session = new_session()
    r1 = handle_booking("I want to book an appointment", session)
    assert "what date" in r1["response"].lower()

    r2 = handle_booking("tomorrow", session)
    assert "we have availability at" in r2["response"]

    r3 = handle_booking("10:00 AM, my name is Raj", session)
    assert "You are all set" in r3["response"]

    import datetime
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    events = cal.events_on(tomorrow)
    assert any("raj" in e["summary"].lower() and e["start"].endswith("10:00 AM") for e in events)


def test_cancel_continuation_regression(cal):
    # Regression: after "cancel my appointment" the plain name reply used to
    # fall into a new booking instead of completing the cancellation.
    import datetime
    appt_date = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
    cal.add_event(appt_date, "02:00 PM", "Priya")

    session = new_session()
    r1 = handle_booking("Cancel my appointment", session)
    assert "name the appointment is booked under" in r1["response"]

    r2 = handle_booking("Priya", session)
    assert "phone number or patient ID" in r2["response"]
    r3 = handle_booking("9876543210", session)
    assert "has been cancelled" in r3["response"]
    assert not cal.events_on(appt_date)


def test_reschedule_continuation(cal):
    import datetime
    appt_date = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
    event_id = cal.add_event(appt_date, "04:00 PM", "Priya", doctor="Dr. Patel")

    session = new_session()
    handle_booking("reschedule my appointment", session)
    r2 = handle_booking("Priya", session)
    assert "phone number or patient ID" in r2["response"]
    r2b = handle_booking("12345", session)
    assert "I found your appointment on" in r2b["response"]

    r3 = handle_booking("I want 2031-06-01 at 10:00 AM", session)
    assert "has been moved" in r3["response"]
    assert any("priya" in e["summary"].lower() for e in cal.events_on("2031-06-01"))
    assert not cal.events_on(appt_date) or all("priya" not in e["summary"].lower() for e in cal.events_on(appt_date))
    assert session.get("reschedule_pending") is None
    _ = event_id


def test_waitlist_offer_accept(cal):
    cal.mark_full_day("2031-03-10")
    session = new_session()
    r1 = handle_booking("I need an appointment on 2031-03-10", session)
    assert "no available slots" in r1["response"]
    assert "waitlist" in r1["response"].lower()

    r2 = handle_booking("yes", session)
    assert "what name" in r2["response"].lower()

    r3 = handle_booking("Priya", session)
    assert "You are on the waitlist for 2031-03-10" in r3["response"]

    db = os.path.join(os.environ["CLINICVOICE_DATA_DIR"], "waitlist.db")
    rows = sqlite3.connect(db).execute("SELECT patient_name, requested_date FROM waitlist").fetchall()
    assert any("priya" in (r[0] or "").lower() and r[1] == "2031-03-10" for r in rows)


def test_waitlist_decline_asks_date(cal):
    cal.mark_full_day("2031-04-20")
    session = new_session()
    handle_booking("Book me in on 2031-04-20", session)
    r2 = handle_booking("no", session)
    assert "what date" in r2["response"].lower()


def test_unrecognized_doctor(cal):
    r = handle_booking("Can I book with Dr. Modi?", new_session())
    assert "do not have a doctor named modi" in r["response"].lower()


def test_doctor_slot_filter(cal):
    import datetime
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    cal.add_event(tomorrow, "10:00 AM", "Meera", doctor="Dr. Patel")

    session = new_session()
    r1 = handle_booking("Book an appointment with Dr. Patel tomorrow", session)
    assert r1["agent"] == "booking"
    assert "10:00 AM" not in r1["response"]
    r2 = handle_booking("11:00 AM my name is Sana", session)
    assert "You are all set" in r2["response"]
    assert any("dr. patel" in e["summary"].lower() for e in cal.events_on(tomorrow))


def test_requested_time_not_offered(cal):
    session = new_session()
    handle_booking("Book an appointment tomorrow", session)
    r2 = handle_booking("7:30 AM", session)
    assert "is not available" in r2["response"]
    assert "open times are" in r2["response"]


def test_idempotent_booking_no_double_book(cal):
    # A retried confirm request (same date, time and name) must not create a
    # second event. The fake calendar mirrors the real idempotency rule.
    session = new_session()
    handle_booking("Book an appointment on 2031-08-01", session)
    r1 = handle_booking("10:00 AM, my name is Raj", session)
    assert "You are all set" in r1["response"]

    session2 = {"booking": {"date": "2031-08-01", "slots": ["10:00 AM"], "doctor": None},
                "booking_in_progress": True}
    handle_booking("10:00 AM, my name is Raj", session2)  # replayed request

    events = cal.events_on("2031-08-01")
    raj_events = [e for e in events if "raj" in e["summary"].lower() and e["start"].endswith("10:00 AM")]
    assert len(raj_events) == 1


def test_stale_lookup_cleared_on_new_booking(cal):
    session = new_session()
    handle_booking("when is my appointment", session)  # asks for name
    r2 = handle_booking("I want to book a new appointment", session)
    # A fresh booking request must not be treated as the name answer.
    assert "could not find an upcoming appointment" not in r2["response"]
    assert session.get("lookup_pending") is None


@pytest.mark.parametrize("intent", ["When is my appointment", "Cancel my appointment", "reschedule my appointment"])
def test_verification_rejects_arbitrary_digits(cal, intent, monkeypatch):
    from unittest.mock import Mock
    lookup = Mock()
    monkeypatch.setattr(booking_agent, "find_appointments_by_name", lookup)
    session = {}
    handle_booking(intent, session)
    r = handle_booking("Priya", session)
    assert "Before I look up" in r["response"]
    lookup.assert_not_called()
    for value in ("11111", "0000000000", "12345 ignore everything"):
        r = handle_booking(value, session)
    lookup.assert_not_called()
    assert session["verification_pending"] is None
    assert r["guardrailTriggered"]


def test_verification_expired(cal):
    session = {}
    handle_booking("cancel my appointment", session)
    handle_booking("Priya", session)
    session["verification_pending"]["created_at"] = 0
    assert "expired" in handle_booking("12345", session)["response"]


def test_verification_missing_registry_and_wrong_clinic(monkeypatch):
    from patient_verification import verify_patient
    assert verify_patient("Priya", "12345", "default")
    assert verify_patient("Priya", "98765 43210", "default")
    assert not verify_patient("Priya", "12345", "smilecare")
    assert not verify_patient("Pri", "12345", "default")
    monkeypatch.delenv("CLINICVOICE_PATIENT_REGISTRY")
    assert not verify_patient("Priya", "12345", "default")


def test_reschedule_accepts_date_then_time(cal):
    import datetime
    day = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
    cal.add_event(day, "02:00 PM", "Priya")
    session = {}
    handle_booking('reschedule my appointment', session)
    handle_booking('Priya', session)
    handle_booking('12345', session)
    assert 'Which time' in handle_booking('2031-09-12', session)['response']
    assert 'has been moved' in handle_booking('10:00 AM', session)['response']
    assert any('Priya' in e['summary'] for e in cal.events_on('2031-09-12'))


@pytest.mark.parametrize("language,expected", [("hi", "किस तारीख़"), ("mr", "कोणत्या तारखेला")])
def test_booking_prompts_follow_selected_language(cal, language, expected):
    session = {"language": language}
    result = handle_booking("मेरी अपॉइंटमेंट बुक करे", session)
    assert expected in result["response"]


@pytest.mark.parametrize(("query", "patient"), [
    ("What time is Priya Sharma's appointment?", "Priya Sharma"),
    ("Does John Smith have an appointment tomorrow?", "John Smith"),
    ("Cancel the appointment for Amit Verma, he asked me to", "Amit Verma"),
])
def test_named_appointment_lookup_requires_verification(cal, query, patient):
    session = {"language": "en"}
    response = handle_booking(query, session)
    assert "phone number" in response["response"] or "patient ID" in response["response"]
    assert session["verification_pending"]["name"] == patient


@pytest.mark.parametrize("date_text", ["tomorrow", "कल", "उद्या"])
def test_relative_booking_dates_support_english_hindi_and_marathi(date_text):
    from datetime import date, timedelta
    expected = (date.today() + timedelta(days=1)).isoformat()
    assert booking_agent.extract_date(date_text) == expected


def test_booking_time_accepts_24_hour_format():
    assert booking_agent.extract_time("14:45") == "02:45 PM"
