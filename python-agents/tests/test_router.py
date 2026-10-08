from agents.router import classify_intent


def test_booking_phrases():
    assert classify_intent("I want to book an appointment") == "booking"
    assert classify_intent("cancel my appointment") == "booking"
    assert classify_intent("reschedule my appointment") == "booking"
    assert classify_intent("when is my appointment") == "booking"
    assert classify_intent("Are there any available slots tomorrow?") == "booking"


def test_refill_and_insurance_and_escalation():
    assert classify_intent("I need a refill for metformin") == "refill"
    assert classify_intent("Do you accept Aetna?") == "insurance"
    assert classify_intent("Is United Healthcare covered?") == "insurance"
    assert classify_intent("Is HDFC Ergo accepted here?") == "insurance"
    assert classify_intent("I want to speak to a manager") == "escalation"
    assert classify_intent("This is an emergency!") == "escalation"


def test_walk_ins_is_not_insurance():
    # Regression: "do you (take|accept)" used to catch walk-in questions and
    # route them to the insurance agent, which answered about providers.
    assert classify_intent("Do you accept walk-ins?") == "faq"
    assert classify_intent("Do you accept card?") == "faq"


def test_faq_fallback():
    assert classify_intent("What are your opening hours?") == "faq"
    assert classify_intent("Where can I park?") == "faq"
    assert classify_intent("hello") == "faq"
