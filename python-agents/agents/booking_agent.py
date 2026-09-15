import re
from datetime import datetime, timedelta
from calendar_service import get_available_slots, book_appointment, find_appointments_by_name, cancel_appointment, DOCTORS
from clinic_hours import is_clinic_open, hours_message


def extract_date(query: str):
    today = datetime.now()

    if re.search(r"\btomorrow\b", query, re.IGNORECASE):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    if re.search(r"\btoday\b", query, re.IGNORECASE):
        return today.strftime("%Y-%m-%d")

    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", query)
    if date_match:
        return date_match.group(1)

    return None


def extract_time(query: str):
    time_match = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)", query)
    if not time_match:
        time_match = re.search(r"\b(\d{1,2})\s*(AM|PM|am|pm|A\.M\.|P\.M\.|a\.m\.|p\.m\.)", query)
        if time_match:
            hour = time_match.group(1)
            period = time_match.group(2).replace(".", "").upper()
            raw = hour + ":00 " + period
        else:
            return None
    else:
        raw = time_match.group(1) + ":" + time_match.group(2) + " " + time_match.group(3).upper()

    try:
        parsed = datetime.strptime(raw, "%I:%M %p")
        return parsed.strftime("%I:%M %p")
    except ValueError:
        return None


def extract_name(query: str):
    name_match = re.search(r"(?:my name is|i.?m|this is)\s+([a-zA-Z]+(?:\s[a-zA-Z]+)?)", query, re.IGNORECASE)
    if name_match:
        return name_match.group(1).strip()
    return None


def extract_doctor(query: str):
    for doc in DOCTORS:
        last_name = doc.split(" ")[-1]
        if re.search(r"\b" + re.escape(last_name) + r"\b", query, re.IGNORECASE):
            return doc
    return None


def handle_booking(query: str, session: dict) -> dict:
    is_lookup = re.search(r"(when is|what time is|do i have)", query, re.IGNORECASE)
    is_cancel = re.search(r"\bcancel\b", query, re.IGNORECASE)
    is_reschedule = re.search(r"\breschedule\b", query, re.IGNORECASE)

    if is_lookup or is_cancel or is_reschedule:
        pending_lookup = session.get("lookup_pending")

        if pending_lookup:
            name = extract_name(query) or query.strip()
        else:
            name = extract_name(query)

        if not name:
            session["lookup_pending"] = "cancel" if is_cancel else ("reschedule" if is_reschedule else "lookup")
            return {
                "response": "Sure, could you tell me the name the appointment is booked under?",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        try:
            matches = find_appointments_by_name(name)
        except Exception:
            return {
                "response": "I am having trouble checking the calendar right now. Please call reception directly.",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        if not matches:
            session["lookup_pending"] = None
            return {
                "response": "I could not find an upcoming appointment under the name " + name + ". Please call reception if you believe this is a mistake.",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        appt = matches[0]
        appt_time = datetime.fromisoformat(appt["start"])
        readable = appt_time.strftime("%A, %B %d at %I:%M %p")

        if pending_lookup == "cancel" or is_cancel:
            try:
                cancel_appointment(appt["id"])
            except Exception:
                return {
                    "response": "I found the appointment, but could not cancel it just now. Please call reception directly.",
                    "guardrailTriggered": False,
                    "agent": "booking"
                }
            session["lookup_pending"] = None
            return {
                "response": "Your appointment on " + readable + " has been cancelled. Let me know if you would like to book a new one.",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        if pending_lookup == "reschedule" or is_reschedule:
            session["lookup_pending"] = None
            return {
                "response": "I found your appointment on " + readable + ". To reschedule, please tell me the new date you would like, and I will cancel the old one once the new slot is confirmed.",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        session["lookup_pending"] = None
        return {
            "response": "Your appointment is on " + readable + ".",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    session["booking_in_progress"] = True

    pending = session.get("booking")
    requested_time = extract_time(query)
    doctor = extract_doctor(query) or (pending.get("doctor") if pending else None)

    if pending and requested_time and requested_time in pending["slots"]:
        patient_name = extract_name(query) or "Patient"
        try:
            event_id = book_appointment(pending["date"], requested_time, patient_name, doctor=doctor)
        except Exception:
            return {
                "response": "I am having trouble confirming that booking right now. Please call reception to book directly.",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        session["booking"] = None
        session["booking_in_progress"] = False
        doctor_text = " with " + doctor if doctor else ""
        return {
            "response": "You are all set! I have booked your appointment" + doctor_text + " for " + pending["date"] + " at " + requested_time + ". We look forward to seeing you.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    date_str = extract_date(query)

    if not date_str:
        prefix = ""
        if not is_clinic_open():
            prefix = hours_message() + " We are currently closed, but I can still help you book for a future date. "
        return {
            "response": prefix + "I would be happy to check availability. Could you tell me what date you would like to come in? For example, tomorrow, or a specific date.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    try:
        slots = get_available_slots(date_str, doctor=doctor)
    except Exception:
        return {
            "response": "I am having trouble checking the calendar right now. Please call reception to book directly.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    if not slots:
        doctor_text = " with " + doctor if doctor else ""
        return {
            "response": "I am sorry, there are no available slots" + doctor_text + " on " + date_str + ". Please try another date or call reception.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    session["booking"] = {"date": date_str, "slots": slots, "doctor": doctor}
    session["booking_in_progress"] = True

    slots_text = ", ".join(slots[:5])
    doctor_text = " with " + doctor if doctor else ""
    return {
        "response": "On " + date_str + doctor_text + ", we have availability at " + slots_text + ". Would you like me to book one of these for you?",
        "guardrailTriggered": False,
        "agent": "booking"
    }
