import os

import obs
from rate_limit import SlidingWindowLimiter
import sessions


def test_redact_announced_names():
    assert obs.redact("my name is Priya Sharma and I need help") == "my name is [REDACTED] and I need help"
    assert obs.redact("This is Raj") == "This is [REDACTED]"
    assert obs.redact("I'm Sana") == "I'm [REDACTED]"
    assert obs.redact("booked under Priya") == "booked under [REDACTED]"


def test_redact_leaves_normal_text():
    text = "I would be happy to check availability. Could you tell me what date you would like?"
    assert obs.redact(text) == text
    assert obs.redact("We are open Monday to Friday") == "We are open Monday to Friday"


def test_request_id_roundtrip(capsys):
    obs.set_request_id("abc123def456")
    assert obs.get_request_id() == "abc123def456"
    obs.log_event("test_event", route="/x", status=200)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    import json

    record = json.loads(line)
    assert record["request_id"] == "abc123def456"
    assert record["event"] == "test_event"
    assert record["route"] == "/x"


def test_rate_limiter_window():
    limiter = SlidingWindowLimiter(max_requests=2, window_seconds=60)
    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is True  # independent key


def test_sessions_survive_reload():
    sessions.save_session("sess-1", {"booking_in_progress": True, "booking": {"date": "2031-01-01"}})
    # A fresh import must read the same state from SQLite, not memory.
    import importlib

    importlib.reload(sessions)
    state = sessions.get_session("sess-1")
    assert state["booking_in_progress"] is True
    assert state["booking"]["date"] == "2031-01-01"
    assert sessions.get_session("never-seen") == {}
