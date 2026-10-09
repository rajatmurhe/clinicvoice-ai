import datetime
import os
import tempfile
import time as _time_mod

import pytest

os.environ.setdefault("CLINICVOICE_DATA_DIR", tempfile.mkdtemp(prefix="adapters-"))
os.environ.setdefault("VOICE_CLONING_ENABLED", "false")
os.environ.setdefault("FAQ_BACKEND_URL", "http://127.0.0.1:1/unreachable")
os.environ.setdefault("CLINICVOICE_CALENDAR_MODE", "fake")

import sys  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scheduling import FakeSqliteAdapter, get_adapter  # noqa: E402


def test_fake_adapter_conforms_to_interface():
    import datetime

    adapter = FakeSqliteAdapter(os.path.join(tempfile.mkdtemp(), "cal.db"))
    soon = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
    slots = adapter.get_available_slots(soon)
    assert "10:00 AM" in slots
    event_id = adapter.book_appointment(soon, "10:00 AM", "Raj")
    assert event_id
    # Idempotent: booking the same slot again returns the same event.
    assert adapter.book_appointment(soon, "10:00 AM", "Raj") == event_id
    found = adapter.find_appointments_by_name("Raj")
    assert any(m["id"] == event_id for m in found)
    assert adapter.cancel_appointment(event_id) is True
    assert adapter.find_appointments_by_name("Raj") == []


def test_get_adapter_respects_clinic_config():
    assert isinstance(get_adapter("smilecare"), FakeSqliteAdapter)


FHIR_LIVE = os.environ.get("CLINICVOICE_FHIR_LIVE") == "1"


@pytest.mark.skipif(not FHIR_LIVE, reason="live FHIR sandbox test disabled; set CLINICVOICE_FHIR_LIVE=1")
def test_fhir_sandbox_adapter_live():
    import time as _time

    from scheduling import FhirSandboxAdapter

    # Unique name per run: the sandbox rejects duplicate resources. The date
    # must be inside the 30 day find window, so use a near future date.
    patient = "EvalPatient%d" % (int(_time_mod.time()) % 100000)
    soon = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    adapter = FhirSandboxAdapter()
    event_id = adapter.book_appointment(soon, "10:00 AM", patient)
    assert event_id
    found = adapter.find_appointments_by_name(patient)
    assert any(m["id"] == event_id for m in found)
    assert adapter.cancel_appointment(event_id) is True
