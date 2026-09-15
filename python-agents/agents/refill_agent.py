import re
from refill_log import log_refill_request


def extract_medication_name(query: str):
    match = re.search(r"refill (?:my |for )?(?:my )?([a-zA-Z]+)", query, re.IGNORECASE)
    if match:
        word = match.group(1).lower()
        if word not in ("my", "a", "the", "prescription", "medication"):
            return word
    return None


def extract_name(query: str):
    name_match = re.search(r"(?:my name is|i.?m|this is)\s+([a-zA-Z]+(?:\s[a-zA-Z]+)?)", query, re.IGNORECASE)
    if name_match:
        return name_match.group(1).strip()
    return None


def handle_refill(query: str, session: dict) -> dict:
    pending = session.get("refill_pending")

    name = extract_name(query)
    medication = extract_medication_name(query)

    if pending:
        name = name or pending.get("name")
        medication = medication or pending.get("medication") or query.strip()

    if not name:
        session["refill_pending"] = {"medication": medication}
        return {
            "response": "I can help log a refill request. Could you tell me your name?",
            "guardrailTriggered": False,
            "agent": "refill"
        }

    if not medication:
        session["refill_pending"] = {"name": name}
        return {
            "response": "Thanks. Which medication would you like refilled? Just the name is fine, no need to share dosage details.",
            "guardrailTriggered": False,
            "agent": "refill"
        }

    try:
        log_refill_request(name, medication)
    except Exception:
        return {
            "response": "I am having trouble logging that request right now. Please call reception to request a refill directly.",
            "guardrailTriggered": False,
            "agent": "refill"
        }

    session["refill_pending"] = None
    return {
        "response": "I have logged a refill request for " + medication + " under " + name + ". Our team will review it and get back to you within 48 hours.",
        "guardrailTriggered": False,
        "agent": "refill"
    }
