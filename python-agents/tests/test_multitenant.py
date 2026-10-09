import datetime
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

os.environ.setdefault("CLINICVOICE_DATA_DIR", tempfile.mkdtemp(prefix="mt-"))
os.environ.setdefault("VOICE_CLONING_ENABLED", "false")
os.environ.setdefault("FAQ_BACKEND_URL", "http://127.0.0.1:1/unreachable")
os.environ.setdefault("CLINICVOICE_RATE_LIMIT", "100000")
os.environ.setdefault("CLINICVOICE_CALENDAR_MODE", "fake")

import sys  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.booking_agent import handle_booking  # noqa: E402
from agents.insurance_agent import handle_insurance  # noqa: E402
from clinic_config import load_clinic  # noqa: E402
import clinic_config  # noqa: E402
import webhooks  # noqa: E402


def test_two_clinics_side_by_side():
    default_session = {"clinic_id": "default"}
    smile_session = {"clinic_id": "smilecare"}

    # Insurance lists differ per clinic.
    assert "Yes" in handle_insurance("Do you accept Star Health?", default_session)["response"]
    assert "do not have that specific provider" in handle_insurance("Do you accept Star Health?", smile_session)["response"]
    assert "Yes" in handle_insurance("Do you accept Delta Dental?", smile_session)["response"]

    # Doctor lists differ per clinic.
    r = handle_booking("Book an appointment with Dr. Mehta on 2031-09-09", smile_session)
    assert r["agent"] == "booking"
    r2 = handle_booking("Book an appointment with Dr. Mehta on 2031-09-09", default_session)
    assert "do not have a doctor named mehta" in r2["response"].lower()

    # Hours messages differ per clinic.
    from clinic_hours import hours_message

    assert "9am to 6pm" in hours_message("default")
    assert "10am to 7pm" in hours_message("smilecare")


def test_clinic_data_is_isolated():
    default_session = {"clinic_id": "default"}
    smile_session = {"clinic_id": "smilecare"}

    r = handle_booking("Book an appointment on 2031-07-07", smile_session)
    assert "we have availability" in r["response"]
    r2 = handle_booking("10:00 AM, my name is Sana", smile_session)
    assert "You are all set" in r2["response"]

    # The same slot at the default clinic must still be free: separate calendar
    # state per clinic.
    r3 = handle_booking("Book an appointment on 2031-07-07", default_session)
    assert "10:00 AM" in r3["response"]


def test_second_clinic_onboards_with_config_only():
    config = load_clinic("smilecare")
    assert config["doctors"] == ["Dr. Mehta", "Dr. Iyer"]
    assert config["scheduling"]["adapter"] == "fake"
    assert config["faqs"]


def test_default_config_reproduces_original_behavior():
    config = load_clinic("default")
    assert config["doctors"] == ["Dr. Sharma", "Dr. Patel", "Dr. Khan"]
    assert "united healthcare" in config["insurance_providers"]
    assert config["hours"]["monday_friday"] == {"open": "09:00", "close": "18:00"}


class _WebhookServer(HTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.requests = []


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        server = self.server
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        server.requests.append({
            "body": body,
            "signature": self.headers.get("X-ClinicVoice-Signature", ""),
            "event": self.headers.get("X-ClinicVoice-Event", ""),
        })
        if server.fail_first > 0 and len(server.requests) <= server.fail_first:
            self.send_response(500)
        else:
            self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_webhook_signed_and_retried():
    server = _WebhookServer()
    server.fail_first = 2
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = "http://127.0.0.1:%d/hook" % server.server_address[1]

    try:
        secret = "test-secret"
        webhooks._deliver(url, secret, "booking_created", {"clinic_id": "smilecare", "date": "2031-01-01"})
    finally:
        server.shutdown()

    assert len(server.requests) == 3  # two failures then success
    first = server.requests[0]
    expected = hmac.new(secret.encode(), first["body"], hashlib.sha256).hexdigest()
    assert first["signature"] == expected
    assert first["event"] == "booking_created"
    payload = json.loads(first["body"])
    assert payload["event"] == "booking_created"
    assert payload["clinic_id"] == "smilecare"
    server.server_close()


def test_clinic_hours_logic():
    from datetime import datetime

    # Wednesday 3pm IST: default clinic open, per its 9-18 window.
    wednesday = datetime(2031, 1, 8, 15, 0)
    assert clinic_config.is_clinic_open("default", now=wednesday) is True
    # Sunday: closed at both clinics.
    sunday = datetime(2031, 1, 12, 12, 0)
    assert clinic_config.is_clinic_open("default", now=sunday) is False
