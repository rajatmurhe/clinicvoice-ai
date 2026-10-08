import re

BLOCKED_PATTERNS_INPUT = [
    r"diagnos", r"\bprescrib", r"medication", r"dose", r"dosage",
    r"how much .* (take|dose)", r"is it (cancer|serious|an emergency)",
    r"chest pain", r"cant breathe", r"symptoms of", r"what disease",
    r"am i dying", r"nhs number", r"date of birth", r"social security",
    r"verify your identity",
    r"\bmedicine\b", r"\bsurgery\b", r"sore throat|throat is sore",
    r"\bantibiotic", r"side effects", r"\bdizzy\b", r"\bfever\b", r"\brash\b",
    r"what (could it be|is wrong with me)",
    r"how (do|to) i (treat|cure)", r"is it safe to",
    r"\d+\s?mg\b",
    r"ignore (all|your|the|previous|my) (previous )?(instructions|rules|guidelines|safety)",
    r"forget your (rules|instructions)", r"new instructions",
    r"system prompt|you are now", r"pretend (you are|to be)|act as",
    r"(patient|appointment|booking) list",
    r"appointment details|patient details|patient data|patient records",
    r"medical records (of|for)",
    r"(phone number|address|date of birth) of (the )?patient",
    r"(show|read|give|tell) me (the )?waitlist",
    r"today'?s bookings", r"share the clinic schedule|clinic schedule with me",
    r"skip (the )?(verification|questions)",
    r"look me up by (name|phone)|look up (my|the) records",
    r"(do not|don.?t) need to verify",
    r"allowed to give medical advice|give medical advice",
]

INPUT_REGEX = re.compile("|".join(BLOCKED_PATTERNS_INPUT), re.IGNORECASE)

EMERGENCY_PATTERNS = [
    r"chest pain", r"can.?t breathe|cannot breathe", r"heart attack",
    r"\bstroke\b", r"severe bleeding", r"unconscious", r"\bsuicid",
    r"kill myself", r"end my life", r"overdos",
]

EMERGENCY_REGEX = re.compile("|".join(EMERGENCY_PATTERNS), re.IGNORECASE)

BLOCKED_RESPONSE = "I am not able to answer clinical or medical questions like that. Please contact the clinic directly or, if this is an emergency, call your local emergency number."

EMERGENCY_RESPONSE = (
    "This sounds like it could be a medical emergency. Please hang up and call "
    "your local emergency number, or go to the nearest emergency room right away. "
    "I have flagged this call for our team to review."
)


def check_input_safety(query):
    return bool(INPUT_REGEX.search(query))


def check_emergency(query):
    return bool(EMERGENCY_REGEX.search(query))
