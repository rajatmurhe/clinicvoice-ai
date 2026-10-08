import os
import sqlite3

from agents.refill_agent import handle_refill


def refill_rows():
    db = os.path.join(os.environ["CLINICVOICE_DATA_DIR"], "refills.db")
    return sqlite3.connect(db).execute(
        "SELECT patient_name, medication_mentioned FROM refill_requests"
    ).fetchall()


def test_full_inline_request():
    session = {}
    r = handle_refill("I need a refill for metformin, my name is Raj", session)
    assert "logged a refill request for metformin under Raj" in r["response"]
    assert session.get("refill_pending") is None
    assert ("Raj", "metformin") in refill_rows()


def test_multi_turn_flow():
    session = {}
    r1 = handle_refill("I need a refill", session)
    assert "your name" in r1["response"].lower()

    r2 = handle_refill("my name is Raj", session)
    assert "Which medication" in r2["response"]

    r3 = handle_refill("metformin", session)
    assert "logged a refill request for metformin under Raj" in r3["response"]
    assert ("Raj", "metformin") in refill_rows()


def test_filler_medication_regression():
    # Regression: "refill please" used to store "please" as the medication and
    # silently log it once the name arrived.
    session = {}
    r1 = handle_refill("refill please", session)
    assert "your name" in r1["response"].lower()

    r2 = handle_refill("Amit", session)
    assert "Which medication" in r2["response"]
    assert refill_rows() == []

    r3 = handle_refill("metformin", session)
    assert ("Amit", "metformin") in refill_rows()


def test_i_am_name_form():
    session = {}
    r = handle_refill("please refill my metformin, I am Raj", session)
    assert "logged a refill request for metformin under Raj" in r["response"]


def test_name_with_digits_preserved():
    session = {}
    r = handle_refill("I need a refill for insulin, my name is Raj12", session)
    assert "under Raj12" in r["response"]
    assert ("Raj12", "insulin") in refill_rows()
