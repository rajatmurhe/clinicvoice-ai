import re
from tools_backend import log_intake
from agents.extract import extract_person_name
from agents.language import localized

REASON_CATEGORIES = {
    "test results": ["test result", "blood test", "results", "जाँच", "जांच", "रिपोर्ट", "चाचणी", "तपासणी", "निकाल"],
    "ongoing symptom": ["symptom", "pain", "not feeling well", "unwell", "दर्द", "दुख", "लक्षण", "तकलीफ", "वेदना", "त्रास", "बरे वाटत नाही"],
    "prescription": ["prescription", "medication", "refill", "दवा", "औषध", "गोळ्या"],
    "admin": ["admin", "form", "letter", "certificate"],
}

BODY_AREAS = ["back", "chest", "head", "stomach", "leg", "arm", "throat", "ear"]


def classify_reason(text):
    text_lower = text.lower()
    for category, keywords in REASON_CATEGORIES.items():
        for kw in keywords:
            if kw in text_lower:
                return category
    return None


def extract_body_area(text):
    text_lower = text.lower()
    for area in BODY_AREAS:
        # Word boundaries only: "heart" must not read as the area "ear" and
        # "alarm" must not read as "arm".
        if re.search(r"\b" + re.escape(area) + r"\b", text_lower):
            return area
    return None


def extract_name(query):
    return extract_person_name(query)


def handle_intake(query, session):
    pending = session.get("intake_pending")

    if not pending:
        reason = classify_reason(query)
        if not reason:
            session["intake_pending"] = {"stage": "reason"}
            return {
                "response": localized(session, "I can note that down for the clinician. Is this about test results, an ongoing symptom, a prescription, or an admin request?", "मैं यह जानकारी चिकित्सक तक पहुँचा सकता हूँ। क्या यह जाँच के नतीजों, लगातार लक्षण, दवा या किसी प्रशासनिक अनुरोध के बारे में है?", "ही माहिती मी डॉक्टरांपर्यंत पोहोचवू शकतो. हा तपासणीचे निकाल, सततची लक्षणे, औषध किंवा प्रशासकीय विनंती यापैकी कशाबद्दल आहे?"),
                "guardrailTriggered": False,
                "agent": "intake"
            }
        session["intake_pending"] = {"stage": "reason", "reason": reason}
        pending = session["intake_pending"]

    if pending["stage"] == "reason" and "reason" not in pending:
        reason = classify_reason(query)
        if not reason:
            return {
                "response": localized(session, "Sorry, could you tell me if this is about test results, an ongoing symptom, a prescription, or an admin request?", "माफ़ कीजिए, क्या यह जाँच के नतीजों, लगातार लक्षण, दवा या प्रशासनिक अनुरोध के बारे में है?", "माफ करा, हा तपासणीचे निकाल, सततची लक्षणे, औषध किंवा प्रशासकीय विनंती यापैकी कशाबद्दल आहे?"),
                "guardrailTriggered": False,
                "agent": "intake"
            }
        pending["reason"] = reason

    if pending["reason"] == "ongoing symptom" and "body_area" not in pending:
        body_area = extract_body_area(query)
        if not body_area and pending["stage"] != "body_area":
            pending["stage"] = "body_area"
            return {
                "response": localized(session, "Thank you. Which general area is this affecting, for example your back, chest, head, or stomach?", "धन्यवाद। यह शरीर के किस हिस्से को प्रभावित कर रहा है—जैसे पीठ, छाती, सिर या पेट?", "धन्यवाद. शरीराच्या कोणत्या भागात त्रास होतो—उदा. पाठ, छाती, डोके किंवा पोट?"),
                "guardrailTriggered": False,
                "agent": "intake"
            }
        pending["body_area"] = body_area or "unspecified"

    name = extract_name(query) or pending.get("name")
    if not name:
        pending["stage"] = "name"
        session["intake_pending"] = pending
        return {
            "response": localized(session, "Thanks for sharing that. Could I take your name so the clinician can review this?", "यह बताने के लिए धन्यवाद। चिकित्सक इसकी समीक्षा कर सकें, इसलिए आपका नाम बता सकते हैं?", "ही माहिती दिल्याबद्दल धन्यवाद. डॉक्टरांना पाहता यावे म्हणून तुमचे नाव सांगाल का?"),
            "guardrailTriggered": False,
            "agent": "intake"
        }

    try:
        log_intake(name, pending["reason"], pending.get("body_area"))
    except Exception:
        return {
            "response": localized(session, "I have noted your details, but had trouble saving this. Please mention it again to reception when you call.", "मैंने जानकारी नोट कर ली है, लेकिन इसे सहेजने में समस्या हुई। कॉल करते समय रिसेप्शन को फिर से बता दें।", "तुमची माहिती नोंदवली आहे, पण ती जतन करताना अडचण आली. फोन करताना रिसेप्शनला पुन्हा सांगा."),
            "guardrailTriggered": False,
            "agent": "intake"
        }

    session["intake_pending"] = None
    return {
        "response": localized(session, "Thank you, I have passed this on to the clinical team for review. Would you like me to help you book an appointment as well?", "धन्यवाद, मैंने यह जानकारी चिकित्सकीय टीम को समीक्षा के लिए भेज दी है। क्या आप अपॉइंटमेंट बुक करना चाहेंगे?", "धन्यवाद, ही माहिती मी वैद्यकीय टीमकडे तपासणीसाठी पाठवली आहे. अपॉइंटमेंट बुक करण्यात मदत करू का?"),
        "guardrailTriggered": False,
        "agent": "intake"
    }
