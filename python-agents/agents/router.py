import re

BOOKING_PATTERNS = [
    r"book (an|a) appointment",
    r"schedule (an|a) appointment",
    r"cancel (my|an|the) appointment",
    r"reschedule",
    r"(appointment|slot)s? (available|availability)",
    r"any (available|free) (slots?|times?|appointments?)",
    r"(am i booked|do i have an appointment)",
    r"when is my appointment",
    r"what time is my appointment",
    r"\bcancel\b",
    r"(get|book) (me )?an? appointment",
    r"book me in",
    r"(can|could) i (get|come in|book)",
    r"see (a|the) doctor",
    r"i.?d like to come in",
]

ESCALATION_PATTERNS = [
    r"speak (to|with) (a|the) (manager|human|person|someone)",
    r"complaint",
    r"not happy",
    r"unhappy",
    r"frustrated",
    r"angry",
    r"this is (urgent|an emergency)",
]

REFILL_PATTERNS = [
    r"refill",
    r"prescription refill",
    r"need more (medication|medicine)",
]

INSURANCE_PATTERNS = [
    r"insurance",
    r"do you (take|accept) .*insurance",
    r"is .*covered",
    r"do you (take|accept)",
]

INTAKE_PATTERNS = [
    r"calling about (a|my) (symptom|pain|test result)",
    r"(test results|blood test)",
    r"(ongoing|new) (symptom|pain)",
    r"not feeling well",
    r"i.?m unwell",
    r"i have a (pain|symptom)",
]

BOOKING_REGEX = re.compile("|".join(BOOKING_PATTERNS), re.IGNORECASE)
ESCALATION_REGEX = re.compile("|".join(ESCALATION_PATTERNS), re.IGNORECASE)
REFILL_REGEX = re.compile("|".join(REFILL_PATTERNS), re.IGNORECASE)
INSURANCE_REGEX = re.compile("|".join(INSURANCE_PATTERNS), re.IGNORECASE)
INTAKE_REGEX = re.compile("|".join(INTAKE_PATTERNS), re.IGNORECASE)


def classify_intent(query: str) -> str:
    if ESCALATION_REGEX.search(query):
        return "escalation"
    if INTAKE_REGEX.search(query):
        return "intake"
    if REFILL_REGEX.search(query):
        return "refill"
    if INSURANCE_REGEX.search(query):
        return "insurance"
    if BOOKING_REGEX.search(query):
        return "booking"
    return "faq"
