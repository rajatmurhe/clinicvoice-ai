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
    r"what time is .*appointment",
    r"does .* have an appointment",
    r"(appointment|booking) (time|details|status)",
    r"(whose|who has) (appointment|booking)",
    r"(look up|find|check) .*appointment",
    r"appointment for .*",
    r"\bcancel\b",
    r"(get|book) (me )?an? appointment",
    r"book me in",
    r"(can|could) i (get|come in|book)",
    r"see (a|the) doctor",
    r"see dr\.?|book with|appointment with",
    r"(need|would like|want) (an?|to book an?) appointment",
    r"i.?d like to come in",
]

ESCALATION_PATTERNS = [
    r"speak (to|with) (a|the) (manager|human|person|someone)",
    r"(talk to|speak to|speak with) (a|the)? ?(real )?(human|person|someone)",
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
    # "Do you accept Aetna?" is insurance, but "Do you accept walk-ins?" and
    # "do you accept card?" are not, so exclude common non-insurance objects.
    r"do you (take|accept) (?!walk.?ins?\b|cash\b|credit|debit|card\b)",
    r"accept(ed)? here",
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

# Cross-lingual keyword table. The regex router is the fast path for English;
# these keywords let Hindi and Marathi messages reach the right agent too.
# Order matters and mirrors the regex router order.
HI_MR_INTENT_KEYWORDS = [
    ("escalation", [r"शिकायत", r"तक्रार", r"प्रबंधक", r"व्यवस्थापक", r"नाराज", r"माणसाशी बोल", r"व्यक्तीशी बोल"]),
    ("intake", [r"लक्षण", r"रिपोर्ट", r"तपासणी", r"रक्त तपासणी", r"दर्द", r"दुखत", r"वेदना", r"बरे वाटत नाही", r"तब्येत ठीक नाही", r"चाचणीचे निकाल"]),
    ("refill", [r"रिफिल", r"रिफील", r"औषध.*(पुन्हा|परत|रिफिल)", r"गोळ्या संप", r"दवा.*(फिर से|दोबारा|खत्म)", r"दवाई.*(फिर से|दोबारा)"]),
    ("insurance", [r"बीमा(?!री)", r"विमा", r"इन्शुरन्स", r"इंश्योरेंस"]),
    ("booking", [r"अपॉइंटमेंट", r"अपॉईंटमेंट", r"भेट.*(ठरव|बुक|हवी)", r"डॉक्टर.*(भेट|दाखवायचं|दाखवायचे)", r"डॉक्टर से मिल", r"डॉक्टर को दिख", r"बुक", r"रद्द", r"कॅन्सल", r"पुढे ढकल", r"तारीख बदल", r"वेळ बदल", r"मुलाकात", r"नियुक्ति", r"समय.*(मिल|चाहिए)"]),
]

HI_MR_KEYWORD_REGEXES = [
    (intent, re.compile("|".join(keywords)))
    for intent, keywords in HI_MR_INTENT_KEYWORDS
]


def classify_intent_with_confidence(query: str):
    """Returns (intent, confidence). Confidence is high when a pattern matched.
    A faq answer with no match at all is low confidence, which is what the
    optional LLM classifier (see CLINICVOICE_HYBRID_ROUTER) acts on."""
    if ESCALATION_REGEX.search(query):
        return "escalation", 1.0
    if INTAKE_REGEX.search(query):
        return "intake", 1.0
    if REFILL_REGEX.search(query):
        return "refill", 1.0
    if INSURANCE_REGEX.search(query):
        return "insurance", 1.0
    if BOOKING_REGEX.search(query):
        return "booking", 1.0
    for intent, keyword_regex in HI_MR_KEYWORD_REGEXES:
        if keyword_regex.search(query):
            return intent, 0.9
    return "faq", 0.3


def classify_intent(query: str) -> str:
    return classify_intent_with_confidence(query)[0]
