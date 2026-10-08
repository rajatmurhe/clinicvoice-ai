import os
import sqlite3

from agents.intake_agent import handle_intake, classify_reason, extract_body_area


def test_classify_reason():
    assert classify_reason("I got my blood test results") == "test results"
    assert classify_reason("I have an ongoing pain") == "ongoing symptom"
    assert classify_reason("I need a letter for work") == "admin"


def test_extract_body_area():
    assert extract_body_area("pain in my lower back") == "back"
    assert extract_body_area("head hurts") == "head"
    assert extract_body_area("not sure") is None


def test_full_intake_flow():
    session = {}
    r1 = handle_intake("I have an ongoing pain", session)
    assert "which general area" in r1["response"].lower()

    r2 = handle_intake("my lower back", session)
    assert "could i take your name" in r2["response"].lower()

    r3 = handle_intake("my name is Raj", session)
    assert "passed this on to the clinical team" in r3["response"]
    assert session.get("intake_pending") is None

    db = os.path.join(os.environ["CLINICVOICE_DATA_DIR"], "intake.db")
    rows = sqlite3.connect(db).execute(
        "SELECT patient_name, reason_category, body_area FROM intake_records"
    ).fetchall()
    assert any(
        "raj" in (r[0] or "").lower() and r[1] == "ongoing symptom" and r[2] == "back"
        for r in rows
    )


def test_area_stated_upfront_skips_area_question():
    session = {}
    r1 = handle_intake("I have a pain in my back", session)
    # The area is already known, so the agent must go straight to the name.
    assert "could i take your name" in r1["response"].lower()

    r2 = handle_intake("my name is Raj", session)
    assert "passed this on to the clinical team" in r2["response"]


def test_unwell_message_asks_reason_without_taking_name():
    # Regression: "I'm feeling unwell" used to be read as the name "feeling".
    session = {}
    r = handle_intake("I'm feeling unwell", session)
    assert r["agent"] == "intake"
    # It asks the next intake question; it must not treat the message as a name.
    assert "your name" not in r["response"].lower()
    assert session["intake_pending"].get("name") is None
