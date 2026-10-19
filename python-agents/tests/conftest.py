import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)

sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(REPO, "python-eval"))

# Must be set before any agent module is imported: the log modules build their
# DB paths from it at import time, and main.py reads VOICE_CLONING_ENABLED.
os.environ["CLINICVOICE_DATA_DIR"] = tempfile.mkdtemp(prefix="clinicvoice-test-")
os.environ["VOICE_CLONING_ENABLED"] = "false"
# Deterministic FAQ failures in pipeline tests: instant connection refused.
os.environ["FAQ_BACKEND_URL"] = "http://127.0.0.1:1/unreachable"
os.environ["CLINICVOICE_RATE_LIMIT"] = "100000"
# Tests run against the shared SQLite fake calendar, not Google.
os.environ["CLINICVOICE_CALENDAR_MODE"] = "fake"

# main.py mounts ./static relative to the cwd at import time.
os.chdir(ROOT)


import sqlite3

import pytest


@pytest.fixture(autouse=True)
def clean_log_tables():
    """Tests share one temp data dir; give each test empty log tables."""
    for table, db_file in (
        ("refill_requests", "refills.db"),
        ("intake_records", "intake.db"),
        ("waitlist", "waitlist.db"),
    ):
        path = os.path.join(os.environ["CLINICVOICE_DATA_DIR"], db_file)
        if os.path.exists(path):
            conn = sqlite3.connect(path)
            conn.execute("DELETE FROM " + table)
            conn.commit()
            conn.close()
    yield

import json
from pathlib import Path
_registry = Path(os.environ["CLINICVOICE_DATA_DIR"]) / "patients.json"
_registry.write_text(json.dumps([
    {"clinic_id": "default", "name": "Priya", "phone": "9876543210", "patient_id": "12345"},
    {"clinic_id": "default", "name": "Ali", "patient_id": "12345"}
]))
os.environ["CLINICVOICE_PATIENT_REGISTRY"] = str(_registry)
