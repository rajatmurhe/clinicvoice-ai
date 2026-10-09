from compliance_reviewer import review_reply


def test_blocks_clinical_advice_in_reply():
    review = review_reply("You should take 500mg twice a day.")
    assert review["verdict"] == "blocked"
    assert review["violation"] == "clinical_advice"
    assert "contact the clinic directly" in review["response"]


def test_blocks_identity_fishing():
    review = review_reply("First, what is your date of birth?")
    assert review["verdict"] == "blocked"


def test_passes_normal_replies():
    for reply in [
        "You are all set! I have booked your appointment for tomorrow at 10:00 AM.",
        "We are open Monday to Friday, 9am to 6pm.",
        "I have logged a refill request for metformin under Raj.",
    ]:
        assert review_reply(reply)["verdict"] == "pass"


def test_no_false_block_on_slot_lists():
    slots = ", ".join("%d:00 PM" % h for h in range(9, 17))
    assert review_reply("On 2031-01-01, we have availability at " + slots + ".")["verdict"] == "pass"
