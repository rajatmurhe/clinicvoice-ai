import re
from intake_log import log_intake

REASON_CATEGORIES = {
    "test results": ["test result", "blood test", "results"],
    "ongoing symptom": ["symptom", "pain", "not feeling well", "unwell"],
    "prescription": ["prescription", "medication", "refill"],
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
        if area in text_lower:
            return area
    return None


def extract_name(query):
    name_match = re.search(r"(?:my name is|i.?m|this is)\s+([a-zA-Z]+(?:\s[a-zA-Z]+)?)", query, re.IGNORECASE)
    if name_match:
        return name_match.group(1).strip()
    return None


def handle_intake(query, session):
    pending = session.get("intake_pending")

    if not pending:
        reason = classify_reason(query)
        if not reason:
            session["intake_pending"] = {"stage": "reason"}
            return {
                "response": "I can note that down for the clinician. Is this about test results, an ongoing symptom, a prescription, or an admin request?",
                "guardrailTriggered": False,
                "agent": "intake"
            }
        session["intake_pending"] = {"stage": "reason", "reason": reason}
        pending = session["intake_pending"]

    if pending["stage"] == "reason" and "reason" not in pending:
        reason = classify_reason(query)
        if not reason:
            return {
                "response": "Sorry, could you tell me if this is about test results, an ongoing symptom, a prescription, or an admin request?",
                "guardrailTriggered": False,
                "agent": "intake"
            }
        pending["reason"] = reason

    if pending["reason"] == "ongoing symptom" and "body_area" not in pending:
        body_area = extract_body_area(query)
        if not body_area and pending["stage"] != "body_area":
            pending["stage"] = "body_area"
            return {
                "response": "Thank you. Which general area is this affecting, for example your back, chest, head, or stomach?",
                "guardrailTriggered": False,
                "agent": "intake"
            }
        pending["body_area"] = body_area or "unspecified"

    name = extract_name(query) or pending.get("name")
    if not name:
        pending["stage"] = "name"
        session["intake_pending"] = pending
        return {
            "response": "Thanks for sharing that. Could I take your name so the clinician can review this?",
            "guardrailTriggered": False,
            "agent": "intake"
        }

    try:
        log_intake(name, pending["reason"], pending.get("body_area"))
    except Exception:
        return {
            "response": "I have noted your details, but had trouble saving this. Please mention it again to reception when you call.",
            "guardrailTriggered": False,
            "agent": "intake"
        }

    session["intake_pending"] = None
    return {
        "response": "Thank you, I have passed this on to the clinical team for review. Would you like me to help you book an appointment as well?",
        "guardrailTriggered": False,
        "agent": "intake"
    }
