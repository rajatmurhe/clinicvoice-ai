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


def handle_booking(query: str) -> dict:
    if re.search(r'(cancel|reschedule)', query, re.IGNORECASE):
        return {
            "response": "To cancel or reschedule an appointment, please call our reception team directly so they can update your booking.",
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

    slots_text = ", ".join(slots[:5])
    return {
        "response": f"On {date_str}, we have availability at {slots_text}. Would you like me to book one of these for you?",
        "guardrailTriggered": False,
        "agent": "booking"
    }
