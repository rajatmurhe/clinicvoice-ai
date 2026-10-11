"""Regression tests for defects found in the QA cycle of 11 Oct 2026.

Each test names its defect so the origin stays traceable. The defect list and
verdicts are also recorded in EDGE_CASES.md.
"""

import datetime
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

import main
from agents.extract import is_yes_no_answer
from safety import check_input_safety, check_emergency


@pytest.fixture()
def client():
    return TestClient(main.app)


def data_dir():
    return os.environ["CLINICVOICE_DATA_DIR"]


def rows(db_file, table):
    path = os.path.join(data_dir(), db_file)
    if not os.path.exists(path):
        return []
    return sqlite3.connect(path).execute("SELECT * FROM " + table).fetchall()


# D2: blocklist evasion via invisible characters and letter spacing


@pytest.mark.parametrize("query", [
    "d i a g n o s e my stomach please",
    "diag\u200bnose my rash",
    "diag\u00adnose my rash",
    "what dease do I have d o s a g e advice",
    "c h e s t   p a i n",
])
def test_squeezed_safety_evasion_blocked(client, query):
    r = client.post("/api/agent-query", json={"query": query, "session_id": "d2"})
    data = r.json()
    assert data["guardrailTriggered"] is True


@pytest.mark.parametrize("query", [
    "how much does it cost to take the bus",
    "I want to book an appointment tomorrow",
    "what is your wifi password",
    "How much is a first visit?",
])
def test_squeeze_does_not_false_block(client, query):
    assert check_input_safety(query) is False


def test_how_much_take_still_blocks_real_dosing():
    assert check_input_safety("How much paracetamol should I take?") is True


def test_squeezed_emergency_detected():
    assert check_emergency("I cant b r e a t h e") is True
    assert check_emergency("where can I park") is False


# D1: unknown clinic id must not 500


def test_unknown_clinic_falls_back_to_default(client):
    r = client.post("/api/agent-query", json={"query": "hello", "session_id": "d1", "clinic_id": "does-not-exist"})
    assert r.status_code == 200
    assert r.json()["agent"] in ("faq", "booking")


# D8: session state must not bleed across tenants


def test_session_namespaced_per_clinic(client):
    sid = "shared-d8"
    r1 = client.post("/api/agent-query", json={"query": "I want to book an appointment", "session_id": sid, "clinic_id": "default"})
    assert r1.json()["intent"] == "booking"
    r2 = client.post("/api/agent-query", json={"query": "tomorrow", "session_id": sid, "clinic_id": "smilecare"})
    data = r2.json()
    assert data["intent"] != "booking", "default clinic flow leaked into smilecare session"


# D3: shape-valid but impossible dates must be rejected before the calendar


def test_invalid_calendar_dates_ask_again(client):
    for bad in ("2031-13-45", "2031-02-30"):
        r = client.post("/api/agent-query", json={"query": "book an appointment on " + bad, "session_id": "d3"})
        response = r.json()["response"]
        assert "having trouble checking the calendar" not in response
        assert "what date" in response.lower()


# D6: rescheduling must not double book an occupied slot


def test_reschedule_rejects_taken_slot(client):
    from fake_calendar import FakeCalendar

    cal = FakeCalendar(os.path.join(data_dir(), "d6-cal.db"))
    day = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
    cal.add_event(day, "10:00 AM", "Ali")
    cal.add_event(day, "11:00 AM", "Priya")

    from agents import booking_agent

    original = {
        "get_available_slots": booking_agent.get_available_slots,
        "book_appointment": booking_agent.book_appointment,
        "find_appointments_by_name": booking_agent.find_appointments_by_name,
        "cancel_appointment": booking_agent.cancel_appointment,
    }
    booking_agent.get_available_slots = cal.get_available_slots
    booking_agent.book_appointment = cal.book_appointment
    booking_agent.find_appointments_by_name = cal.find_appointments_by_name
    booking_agent.cancel_appointment = cal.cancel_appointment
    try:
        session = {}
        booking_agent.handle_booking("reschedule my appointment", session)
        booking_agent.handle_booking("Ali", session)
        r = booking_agent.handle_booking("I want " + day + " at 11:00 AM", session)
        assert "is not available" in r["response"]
        eleven = [e for e in cal.events_on(day) if "11:00 AM" in e["start"]]
        assert len(eleven) == 1, "reschedule double booked Priya's slot"
    finally:
        booking_agent.get_available_slots = original["get_available_slots"]
        booking_agent.book_appointment = original["book_appointment"]
        booking_agent.find_appointments_by_name = original["find_appointments_by_name"]
        booking_agent.cancel_appointment = original["cancel_appointment"]


# D7 / D10: yes/no words are never patient names


def test_yes_no_words_recognised():
    assert is_yes_no_answer("no") is True
    assert is_yes_no_answer("Nope.") is True
    assert is_yes_no_answer("Priya") is False
    assert is_yes_no_answer("my name is Priya") is False


def test_waitlist_declines_no_answer(client):
    sid = "d7"
    from calendar_service import _get_fake

    _get_fake().mark_full_day("2031-04-02")
    client.post("/api/agent-query", json={"query": "Book me in on 2031-04-02", "session_id": sid})
    client.post("/api/agent-query", json={"query": "yes", "session_id": sid})
    r = client.post("/api/agent-query", json={"query": "no", "session_id": sid})
    assert "not added you to the waitlist" in r.json()["response"]
    assert rows("waitlist.db", "waitlist") == []


def test_refill_declines_no_answer(client):
    sid = "d10"
    client.post("/api/agent-query", json={"query": "I need a refill", "session_id": sid})
    r = client.post("/api/agent-query", json={"query": "no", "session_id": sid})
    assert "cancel that refill request" in r.json()["response"].lower()
    assert rows("refills.db", "refill_requests") == []


def test_lookup_declines_no_answer(client):
    sid = "d7-lookup"
    client.post("/api/agent-query", json={"query": "cancel my appointment", "session_id": sid})
    r = client.post("/api/agent-query", json={"query": "no", "session_id": sid})
    assert "left that" in r.json()["response"]


# D9: intake body areas need word boundaries


def test_intake_body_area_word_boundaries(client):
    sid = "d9"
    client.post("/api/agent-query", json={"query": "I have ongoing symptoms", "session_id": sid})
    client.post("/api/agent-query", json={"query": "my heart hurts", "session_id": sid})
    client.post("/api/agent-query", json={"query": "my name is QATester", "session_id": sid})
    recorded = [r for r in rows("intake.db", "intake_records") if "QATester" in str(r[2])]
    assert recorded, "intake did not complete"
    assert recorded[-1][4] == "unspecified", "heart was read as the body area ear"


def test_intake_still_finds_real_areas(client):
    sid = "d9b"
    client.post("/api/agent-query", json={"query": "I have ongoing symptoms", "session_id": sid})
    client.post("/api/agent-query", json={"query": "pain in my lower back", "session_id": sid})
    client.post("/api/agent-query", json={"query": "my name is QATester2", "session_id": sid})
    recorded = [r for r in rows("intake.db", "intake_records") if "QATester2" in str(r[2])]
    assert recorded[-1][4] == "back"


# D-obs: /ready URL derivation (was /api/api/health)


def test_ready_url_derivation():
    import importlib

    os.environ["FAQ_BACKEND_URL"] = "http://faq-api:5050/api/text-query"
    import main as main_module

    importlib.reload(main_module)
    assert main_module.faq_base_url() == "http://faq-api:5050"
