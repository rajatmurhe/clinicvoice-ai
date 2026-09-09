import re

BOOKING_PATTERNS = [
    r"book (an|a) appointment",
    r"schedule (an|a) appointment",
    r"cancel (my|an|the) appointment",
    r"reschedule",
    r"(available|availability|free slot)",
    r"(am i booked|do i have an appointment)",
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

BOOKING_REGEX = re.compile("|".join(BOOKING_PATTERNS), re.IGNORECASE)
ESCALATION_REGEX = re.compile("|".join(ESCALATION_PATTERNS), re.IGNORECASE)


def classify_intent(query: str) -> str:
    if ESCALATION_REGEX.search(query):
        return "escalation"
    if BOOKING_REGEX.search(query):
        return "booking"
    return "faq"
