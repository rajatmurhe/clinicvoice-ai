import datetime

from agents.booking_agent import extract_date, extract_time, extract_doctor, mentions_unrecognized_doctor
from agents.extract import extract_person_name
from agents.refill_agent import extract_medication_name


def test_extract_date_relative():
    today = datetime.date.today()
    assert extract_date("book me in tomorrow please") == (today + datetime.timedelta(days=1)).isoformat()
    assert extract_date("can I come in today?") == today.isoformat()


def test_extract_date_iso():
    assert extract_date("I want an appointment on 2031-06-01") == "2031-06-01"


def test_extract_date_day_month():
    # "28 September" style. If the date already passed this year the agent
    # rolls it to next year, so compute the expectation the same way.
    today = datetime.date.today()
    parsed = datetime.datetime.strptime("28 September", "%d %B")
    expected = parsed.date().replace(year=today.year)
    if expected < today:
        expected = expected.replace(year=today.year + 1)
    assert extract_date("book me on 28 September") == expected.isoformat()
    assert extract_date("book me on September 28th") == expected.isoformat()


def test_extract_date_unknown():
    assert extract_date("sometime next week") is None


def test_extract_time_formats():
    assert extract_time("10:00 AM") == "10:00 AM"
    assert extract_time("2:30 pm") == "02:30 PM"
    # Regression (commit 04a2376): period punctuated meridiem used to fail.
    assert extract_time("9:00 a.m.") == "09:00 AM"
    assert extract_time("9:00 p.m.") == "09:00 PM"
    assert extract_time("930 PM") == "09:30 PM"
    assert extract_time("9 PM") == "09:00 PM"


def test_extract_time_none():
    assert extract_time("half past ten") is None
    assert extract_time("tomorrow morning") is None


def test_extract_person_name_forms():
    assert extract_person_name("my name is Raj") == "Raj"
    assert extract_person_name("This is Priya Sharma") == "Priya Sharma"
    assert extract_person_name("I'm Raj") == "Raj"
    assert extract_person_name("I am Raj") == "Raj"
    assert extract_person_name("my name is Raj12") == "Raj12"  # digits regression


def test_extract_person_name_rejects_sentences():
    assert extract_person_name("I am feeling unwell") is None
    assert extract_person_name("I'm calling about my test results") is None
    assert extract_person_name("I am not happy with the service") is None
    assert extract_person_name("book me in tomorrow") is None


def test_extract_doctor_matches_only_real_doctors():
    assert extract_doctor("I want to book with Dr. Patel tomorrow") == "Dr. Patel"
    assert extract_doctor("can I see doctor sharma?") == "Dr. Sharma"


def test_extract_doctor_surname_false_positive_regression():
    # Regression (commit 3691e77): the patient's own surname must not be read
    # as a doctor preference just because it matches a doctor's surname.
    assert extract_doctor("My name is Patel and I need an appointment") is None
    assert extract_doctor("This is Khan, book me in") is None


def test_mentions_unrecognized_doctor():
    assert mentions_unrecognized_doctor("Can I book with Dr. Modi?") == "Modi"
    assert mentions_unrecognized_doctor("see the doctor tomorrow") is None
    assert mentions_unrecognized_doctor("book with Dr. Patel") is None  # recognized


def test_extract_medication_name():
    assert extract_medication_name("refill my metformin") == "metformin"
    assert extract_medication_name("I need a refill for insulin") == "insulin"


def test_extract_medication_name_rejects_fillers():
    # Regression: "refill please" used to log the word "please" as medication.
    assert extract_medication_name("refill please") is None
    assert extract_medication_name("refill my medication") is None
