import re
from datetime import datetime, timedelta
from calendar_service import get_available_slots, book_appointment


def extract_date(query: str):
    today = datetime.now()

    if re.search(r'\btomorrow\b', query, re.IGNORECASE):
        return (today + timedelta(days=1)).strftime('%Y-%m-%d')

    if re.search(r'\btoday\b', query, re.IGNORECASE):
        return today.strftime('%Y-%m-%d')

    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', query)
    if date_match:
        return date_match.group(1)

    return None


def extract_time(query: str):
    time_match = re.search(r'(\d{1,2}[:.]?\d{2}\s*(?:AM|PM|am|pm))', query)
    if time_match:
        raw = time_match.group(1).replace('.', ':').upper()
        raw = re.sub(r'\s+', ' ', raw)
        try:
            parsed = datetime.strptime(raw, '%I:%M %p')
            return parsed.strftime('%I:%M %p')
        except ValueError:
            return None
    return None


def extract_name(query: str):
    name_match = re.search(r"(?:my name is|i'?m|this is)\s+([a-zA-Z]+(?:\s[a-zA-Z]+)?)", query, re.IGNORECASE)
    if name_match:
        return name_match.group(1).strip()
    return "Patient"


def handle_booking(query: str, session: dict) -> dict:
    if re.search(r'(cancel|reschedule)', query, re.IGNORECASE):
        return {
            "response": "To cancel or reschedule an appointment, please call our reception team directly so they can update your booking.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    pending = session.get("booking")
    requested_time = extract_time(query)

    if pending and requested_time and requested_time in pending["slots"]:
        patient_name = extract_name(query)
        try:
            event_id = book_appointment(pending["date"], requested_time, patient_name)
        except Exception:
            return {
                "response": "I'm having trouble confirming that booking right now. Please call reception to book directly.",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        session["booking"] = None
        return {
            "response": f"You're all set! I've booked your appointment for {pending['date']} at {requested_time}. We look forward to seeing you.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    date_str = extract_date(query)

    if not date_str:
        return {
            "response": "I'd be happy to check availability. Could you tell me what date you'd like to come in? For example, tomorrow, or a specific date.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    try:
        slots = get_available_slots(date_str)
    except Exception:
        return {
            "response": "I'm having trouble checking the calendar right now. Please call reception to book directly.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    if not slots:
        return {
            "response": f"I'm sorry, there are no available slots on {date_str}. Please try another date or call reception.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    session["booking"] = {"date": date_str, "slots": slots}

    slots_text = ", ".join(slots[:5])
    return {
        "response": f"On {date_str}, we have availability at {slots_text}. Would you like me to book one of these for you?",
        "guardrailTriggered": False,
        "agent": "booking"
    }
