import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture()
def client():
    return TestClient(main.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_emergency_gets_dedicated_response(client):
    r = client.post("/api/agent-query", json={"query": "I have chest pain", "session_id": "t-emg"})
    data = r.json()
    assert data["guardrailTriggered"] is True
    assert "emergency number" in data["response"].lower()
    assert data["intent"] == "emergency"


def test_unsafe_input_blocked(client):
    r = client.post("/api/agent-query", json={"query": "What is my NHS number?", "session_id": "t-blk"})
    data = r.json()
    assert data["guardrailTriggered"] is True
    assert "not able to answer clinical" in data["response"]


def test_blocked_input_clears_pending_refill(client):
    # Regression (stuck pending flows): a blocked message mid-flow must clear
    # the pending flow so the next message is not silently swallowed.
    sid = "t-stuck-refill"
    r1 = client.post("/api/agent-query", json={"query": "I need a refill", "session_id": sid})
    assert "your name" in r1.json()["response"].lower()

    client.post("/api/agent-query", json={"query": "What is my NHS number?", "session_id": sid})

    r3 = client.post("/api/agent-query", json={"query": "Raj", "session_id": sid})
    data = r3.json()
    assert data["guardrailTriggered"] is False
    assert data["intent"] != "refill"


def test_escalation_clears_pending_booking(client):
    sid = "t-stuck-booking"
    r1 = client.post("/api/agent-query", json={"query": "I want to book an appointment", "session_id": sid})
    assert r1.json()["intent"] == "booking"

    r2 = client.post("/api/agent-query", json={"query": "this is urgent and I am frustrated", "session_id": sid})
    assert r2.json()["agent"] == "escalation"

    r3 = client.post("/api/agent-query", json={"query": "tomorrow", "session_id": sid})
    data = r3.json()
    assert data["intent"] != "booking"


def test_repeat_returns_last_response(client):
    sid = "t-repeat"
    r1 = client.post("/api/agent-query", json={"query": "hello there", "session_id": sid})
    r2 = client.post("/api/agent-query", json={"query": "sorry what did you say?", "session_id": sid})
    assert r2.json()["agent"] == "repeat"
    assert r2.json()["response"] == r1.json()["response"]


def test_cancel_flow_completes_with_bare_name(client):
    # End to end regression for the dropped name answer in the cancel flow.
    sid = "t-cancel-flow"
    r1 = client.post("/api/agent-query", json={"query": "cancel my appointment", "session_id": sid})
    assert "name the appointment is booked under" in r1.json()["response"].lower()

    r2 = client.post("/api/agent-query", json={"query": "Zebra", "session_id": sid})
    data = r2.json()
    assert data["intent"] == "booking"
    assert "could not find an upcoming appointment under the name Zebra" in data["response"]
