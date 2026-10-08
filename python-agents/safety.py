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
    # Hindi and Marathi unsafe phrases, kept in sync with llm-cloud.js.
    # Deliberately no bare "दवा" or "औषध" (medicine): the refill flow needs it.
    r"खुराक|डोस", r"निदान",
    r"कौन स[ीा] दवा|कोणत[ेी] औषध|कोणत्या औषध",
    r"कितन[ीा] दवा|कितनी खुराक",
    r"क्या बीमारी|कौन सी बीमारी|मेरी बीमारी|काय आजार|माझा आजार",
    r"मुझे क्या हुआ",
    r"दूसरे मरीज़|दुसऱ्या रुग्णाचा|मरीज़ का डेटा|रुग्णाची माहिती",
    r"मरीज़ों की लिस्ट|रुग्णांची यादी",
]

INPUT_REGEX = re.compile("|".join(BLOCKED_PATTERNS_INPUT), re.IGNORECASE)

EMERGENCY_PATTERNS = [
    r"chest pain", r"can.?t breathe|cannot breathe", r"heart attack",
    r"\bstroke\b", r"severe bleeding", r"unconscious", r"\bsuicid",
    r"kill myself", r"end my life", r"overdos",
    r"छाती में दर्द|छातीत दुखत", r"सांस (नहीं|लेने में)|सांस घेता येत नाही|दम बांधत नाही",
    r"हृदयाचा झटका|हार्ट अटैक", r"खूप रक्तस्राव|बहुत खून",
]

EMERGENCY_REGEX = re.compile("|".join(EMERGENCY_PATTERNS), re.IGNORECASE)

BLOCKED_RESPONSE = "I am not able to answer clinical or medical questions like that. Please contact the clinic directly or, if this is an emergency, call your local emergency number."

EMERGENCY_RESPONSE = (
    "This sounds like it could be a medical emergency. Please hang up and call "
    "your local emergency number, or go to the nearest emergency room right away. "
    "I have flagged this call for our team to review."
)

HINDI_BLOCKED_RESPONSE = "मैं इस तरह के नैदानिक या चिकित्सकीय सवालों के जवाब नहीं दे सकती। कृपया क्लिनिक को सीधे संपर्क करें, और यदि यह आपातकाल है तो अपनी स्थानीय आपातकालीन सेवा को कॉल करें।"

MARATHI_BLOCKED_RESPONSE = "मी अशा वैद्यकीय प्रश्नांची उत्तरे देऊ शकत नाही. कृपया क्लिनिकशी थेट संपर्क करा, आणि ही आपत्कालीन परिस्थिती असल्यास तुमच्या स्थानिक आपत्कालीन सेवेला कॉल करा."

HINDI_EMERGENCY_RESPONSE = "हा एक वैद्यकीय आपातकाल हो सकता है। कृपया अभी कॉल काटें और अपनी स्थानीय आपातकालीन सेवा को कॉल करें या नज़दीकी अस्पताल जाएँ। मैंने इस कॉल को टीम के लिए चिह्नित किया है।"

MARATHI_EMERGENCY_RESPONSE = "ही वैद्यकीय आपत्कालीन परिस्थिती असू शकते. कृपया आत्ताच कॉल बंद करून तुमच्या स्थानिक आपत्कालीन सेवेला कॉल करा किंवा जवळच्या रुग्णालयात जा. मी हा कॉल टीमसाठी चिन्हांकित केला आहे."

DEVANAGARI = re.compile(r"[\u0900-\u097F]")
# Marathi leans on these; otherwise Devanagari is answered in Hindi.
MARATHI_HINTS = re.compile(r"मला|तुम्ही|क्लिनिकचे|करायची|करावा|सांगा|आहे का|देऊ|घेता येत")


def response_language(query):
    if not DEVANAGARI.search(query):
        return "en"
    if MARATHI_HINTS.search(query):
        return "mr"
    return "hi"


def blocked_response_for(query):
    language = response_language(query)
    if language == "mr":
        return MARATHI_BLOCKED_RESPONSE
    if language == "hi":
        return HINDI_BLOCKED_RESPONSE
    return BLOCKED_RESPONSE


def emergency_response_for(query):
    language = response_language(query)
    if language == "mr":
        return MARATHI_EMERGENCY_RESPONSE
    if language == "hi":
        return HINDI_EMERGENCY_RESPONSE
    return EMERGENCY_RESPONSE


def check_input_safety(query):
    return bool(INPUT_REGEX.search(query))


def check_emergency(query):
    return bool(EMERGENCY_REGEX.search(query))
