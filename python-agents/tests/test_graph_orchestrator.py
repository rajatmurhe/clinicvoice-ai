import os
import tempfile

import pytest

os.environ.setdefault("CLINICVOICE_DATA_DIR", tempfile.mkdtemp(prefix="graph-test-"))
os.environ.setdefault("VOICE_CLONING_ENABLED", "false")
os.environ.setdefault("FAQ_BACKEND_URL", "http://127.0.0.1:1/unreachable")
os.environ.setdefault("CLINICVOICE_RATE_LIMIT", "100000")

pytest.importorskip("langgraph", reason="langgraph not installed")

import graph_orchestrator  # noqa: E402
from fake_calendar import FakeCalendar  # noqa: E402
from agents import booking_agent  # noqa: E402


@pytest.fixture()
def patched_calendar(monkeypatch):
    fake = FakeCalendar()
    monkeypatch.setattr(booking_agent, "get_available_slots", fake.get_available_slots)
    monkeypatch.setattr(booking_agent, "book_appointment", fake.book_appointment)
    monkeypatch.setattr(booking_agent, "find_appointments_by_name", fake.find_appointments_by_name)
    monkeypatch.setattr(booking_agent, "cancel_appointment", fake.cancel_appointment)
    yield fake
    graph_orchestrator._APP = None
    graph_orchestrator._CHECKPOINTER = None


def test_graph_blocks_unsafe(patched_calendar):
    r = graph_orchestrator.run_query("What is my NHS number?", "g1")
    assert r["guardrailTriggered"] is True
    assert r["intent"] == "faq"


def test_graph_emergency(patched_calendar):
    r = graph_orchestrator.run_query("I have chest pain", "g2")
    assert r["guardrailTriggered"] is True
    assert r["intent"] == "emergency"


def test_graph_multi_turn_booking(patched_calendar):
    r1 = graph_orchestrator.run_query("I want to book an appointment", "g3")
    assert "what date" in r1["response"].lower()
    r2 = graph_orchestrator.run_query("2031-09-09", "g3")
    assert "we have availability at" in r2["response"]
    r3 = graph_orchestrator.run_query("10:00 AM, my name is Raj", "g3")
    assert "You are all set" in r3["response"]


def test_graph_escalation_clears_flow(patched_calendar):
    graph_orchestrator.run_query("I want to book an appointment", "g4")
    r = graph_orchestrator.run_query("I am very frustrated with this", "g4")
    assert r["agent"] == "escalation"
    r2 = graph_orchestrator.run_query("tomorrow", "g4")
    assert r2["intent"] != "booking"


def test_graph_verification_and_clinic_isolation(patched_calendar):
    import datetime
    day = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
    patched_calendar.add_event(day, "02:00 PM", "Priya")
    sid = "graph-verify"
    graph_orchestrator.run_query("cancel my appointment", sid)
    result = graph_orchestrator.run_query("Priya", sid)
    assert "phone number or patient ID" in result["response"]
    wrong_clinic = graph_orchestrator.run_query("12345", sid, "smilecare")
    assert "cancelled" not in wrong_clinic["response"]
    result = graph_orchestrator.run_query("00000", sid)
    assert "couldn't verify" in result["response"]
    assert patched_calendar.events_on(day)
    result = graph_orchestrator.run_query("12345", sid)
    assert "has been cancelled" in result["response"]
    assert result["query"] == "[verification response redacted]"
