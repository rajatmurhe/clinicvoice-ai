import re
from datetime import datetime, timedelta
from tools_backend import get_available_slots, book_appointment, find_appointments_by_name, cancel_appointment
from clinic_hours import is_clinic_open, hours_message
from clinic_config import load_clinic
import webhooks
from waitlist import add_to_waitlist, notify_waitlist
from agents.extract import extract_person_name


def extract_date(query: str):
    today = datetime.now()

    if re.search(r"\btomorrow\b", query, re.IGNORECASE):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    if re.search(r"\btoday\b", query, re.IGNORECASE):
        return today.strftime("%Y-%m-%d")

    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", query)
    if date_match:
        return date_match.group(1)

    month_names = "january|february|march|april|may|june|july|august|september|october|november|december"

    day_first_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + month_names + r")\b", query, re.IGNORECASE)
    month_first_match = re.search(r"\b(" + month_names + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", query, re.IGNORECASE)

    day = None
    month_name = None
    if day_first_match:
        day = int(day_first_match.group(1))
        month_name = day_first_match.group(2)
    elif month_first_match:
        month_name = month_first_match.group(1)
        day = int(month_first_match.group(2))

    if day and month_name:
        try:
            candidate = datetime.strptime(str(today.year) + " " + month_name + " " + str(day), "%Y %B %d")
        except ValueError:
            return None
        if candidate.date() < today.date():
            candidate = candidate.replace(year=today.year + 1)
        return candidate.strftime("%Y-%m-%d")

    return None


def extract_time(query: str):
    normalized_query = re.sub(r"\b(a|A)\.\s*(m|M)\.", "AM", query)
    normalized_query = re.sub(r"\b(p|P)\.\s*(m|M)\.", "PM", normalized_query)

    time_match = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)", normalized_query)
    if time_match:
        raw = time_match.group(1) + ":" + time_match.group(2) + " " + time_match.group(3).upper()
        try:
            parsed = datetime.strptime(raw, "%I:%M %p")
            return parsed.strftime("%I:%M %p")
        except ValueError:
            return None

    four_digit_match = re.search(r"\b(\d{3,4})\s*(AM|PM|am|pm|A\.M\.|P\.M\.|a\.m\.|p\.m\.)", normalized_query)
    if four_digit_match:
        digits = four_digit_match.group(1)
        period = four_digit_match.group(2).replace(".", "").upper()
        if len(digits) == 3:
            hour = digits[0]
            minute = digits[1:]
        else:
            hour = digits[:2]
            minute = digits[2:]
        raw = hour + ":" + minute + " " + period
        try:
            parsed = datetime.strptime(raw, "%I:%M %p")
            return parsed.strftime("%I:%M %p")
        except ValueError:
            pass

    bare_hour_match = re.search(r"\b(\d{1,2})\s*(AM|PM|am|pm|A\.M\.|P\.M\.|a\.m\.|p\.m\.)", normalized_query)
    if bare_hour_match:
        hour = bare_hour_match.group(1)
        period = bare_hour_match.group(2).replace(".", "").upper()
        raw = hour + ":00 " + period
        try:
            parsed = datetime.strptime(raw, "%I:%M %p")
            return parsed.strftime("%I:%M %p")
        except ValueError:
            return None

    return None


def extract_name(query: str):
    return extract_person_name(query)


NON_NAME_WORDS = ("for", "a", "the", "an", "here", "please", "available", "tomorrow", "today")


def extract_doctor(query: str, clinic_id=None):
    for doc in load_clinic(clinic_id).get("doctors", []):
        last_name = doc.split(" ")[-1]
        if re.search(r"\b(?:dr\.?|doctor)\s+" + re.escape(last_name) + r"\b", query, re.IGNORECASE):
            return doc
    return None


def mentions_unrecognized_doctor(query: str, clinic_id=None):
    mention = re.search(r"\b(?:dr\.?|doctor)\s+([a-zA-Z]+)", query, re.IGNORECASE)
    if not mention:
        return None
    word = mention.group(1)
    if word.lower() in NON_NAME_WORDS:
        return None
    if extract_doctor(query, clinic_id):
        return None
    return word


def is_affirmative(query: str):
    return bool(re.search(r"\b(yes|yeah|yep|sure|please|add me)\b", query, re.IGNORECASE))


def handle_reschedule_continuation(query: str, session: dict, reschedule_pending: dict) -> dict:
    """Continues a reschedule after the appointment was found: takes the new
    date (and optionally time), confirms the new slot, then cancels the old one."""
    clinic_id = reschedule_pending.get("clinic_id")
    new_date = extract_date(query)
    new_time = extract_time(query)

    if not new_date:
        return {
            "response": "Sure, which new date would you like? For example, tomorrow or a specific date.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    shown_slots = reschedule_pending.get("slots")
    if not new_time:
        try:
            slots = get_available_slots(new_date, doctor=reschedule_pending.get("doctor"), clinic_id=clinic_id)
        except Exception:
            return {
                "response": "I am having trouble checking the calendar right now. Please call reception to reschedule.",
                "guardrailTriggered": False,
                "agent": "booking"
            }
        if not slots:
            return {
                "response": "I am sorry, there are no available slots on " + new_date + ". Which other date would you like?",
                "guardrailTriggered": False,
                "agent": "booking"
            }
        reschedule_pending["new_date"] = new_date
        reschedule_pending["slots"] = slots
        return {
            "response": "On " + new_date + ", we have availability at " + ", ".join(slots[:5]) + ". Which time works for you?",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    if shown_slots and new_time not in shown_slots:
        return {
            "response": "I am sorry, " + new_time + " is not available. The open times are " + ", ".join(shown_slots[:5]) + ". Which of these would you like?",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    try:
        book_appointment(
            new_date, new_time, reschedule_pending["name"],
            doctor=reschedule_pending.get("doctor"), clinic_id=clinic_id
        )
        cancel_appointment(reschedule_pending["event_id"], clinic_id=clinic_id)
    except Exception:
        return {
            "response": "I found the new slot but could not move the appointment just now. Please call reception to reschedule.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    session["reschedule_pending"] = None
    session["booking_in_progress"] = False
    old_readable = reschedule_pending.get("old_readable", "")
    return {
        "response": "Done! Your appointment has been moved to " + new_date + " at " + new_time + ". The old slot on " + old_readable + " has been released.",
        "guardrailTriggered": False,
        "agent": "booking"
    }


def handle_booking(query: str, session: dict) -> dict:
    clinic_id = session.get("clinic_id")
    waitlist_offer = session.get("waitlist_offer")
    if waitlist_offer and is_affirmative(query):
        name = extract_name(query) or waitlist_offer.get("name")
        if not name:
            session["waitlist_offer"]["awaiting_name"] = True
            return {
                "response": "Sure, what name should I add to the waitlist?",
                "guardrailTriggered": False,
                "agent": "booking"
            }
        try:
            add_to_waitlist(name, waitlist_offer["date"], waitlist_offer.get("doctor"))
        except Exception:
            return {
                "response": "I am having trouble adding you to the waitlist right now. Please call reception directly.",
                "guardrailTriggered": False,
                "agent": "booking"
            }
        session["waitlist_offer"] = None
        return {
            "response": "You are on the waitlist for " + waitlist_offer["date"] + ". We will contact you right away if a slot opens up.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    if waitlist_offer and waitlist_offer.get("awaiting_name"):
        name = extract_name(query) or query.strip()
        try:
            add_to_waitlist(name, waitlist_offer["date"], waitlist_offer.get("doctor"))
        except Exception:
            return {
                "response": "I am having trouble adding you to the waitlist right now. Please call reception directly.",
                "guardrailTriggered": False,
                "agent": "booking"
            }
        session["waitlist_offer"] = None
        return {
            "response": "You are on the waitlist for " + waitlist_offer["date"] + ". We will contact you right away if a slot opens up.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    is_lookup = re.search(r"(when is|what time is|do i have)", query, re.IGNORECASE)
    is_cancel = re.search(r"\bcancel\b", query, re.IGNORECASE)
    is_reschedule = re.search(r"\breschedule\b", query, re.IGNORECASE)
    pending_lookup = session.get("lookup_pending")

    # A reply to "could you tell me the name the appointment is booked under?"
    # is usually just the name ("Priya"), with no cancel/lookup keyword in it.
    # Treat any message that carries the keywords, or answers a pending lookup
    # without starting a fresh booking, as part of the lookup flow.
    fresh_booking_start = re.search(
        r"book|schedule|appointment|slot|see (a|the) doctor|come in", query, re.IGNORECASE
    )
    in_lookup_flow = bool(
        is_lookup or is_cancel or is_reschedule
        or (pending_lookup and not fresh_booking_start)
    )

    if in_lookup_flow:
        if is_cancel:
            pending_lookup = "cancel"
        elif is_reschedule:
            pending_lookup = "reschedule"
        elif is_lookup:
            pending_lookup = "lookup"
        else:
            pending_lookup = pending_lookup or "lookup"

        answering_pending = bool(pending_lookup) and not (
            is_lookup or is_cancel or is_reschedule
        )

        if answering_pending:
            name = extract_name(query) or query.strip()
        else:
            name = extract_name(query)

        if not name:
            session["lookup_pending"] = pending_lookup
            return {
                "response": "Sure, could you tell me the name the appointment is booked under?",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        try:
            matches = find_appointments_by_name(name, clinic_id=clinic_id)
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
        appt_date = appt_time.strftime("%Y-%m-%d")

        if pending_lookup == "cancel" or is_cancel:
            try:
                cancel_appointment(appt["id"], clinic_id=clinic_id)
            except Exception:
                return {
                    "response": "I found the appointment, but could not cancel it just now. Please call reception directly.",
                    "guardrailTriggered": False,
                    "agent": "booking"
                }
            session["lookup_pending"] = None
            webhooks.dispatch(clinic_id, "booking_cancelled", {
                "clinic_id": clinic_id, "patient_name": name,
                "date": appt_date, "time": readable,
            })
            notified = notify_waitlist(appt_date)
            waitlist_note = " I have also notified " + str(notified) + " waitlisted patient(s) for that date." if notified else ""
            return {
                "response": "Your appointment on " + readable + " has been cancelled." + waitlist_note + " Let me know if you would like to book a new one.",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        if pending_lookup == "reschedule" or is_reschedule:
            session["lookup_pending"] = None
            session["reschedule_pending"] = {
                "event_id": appt["id"],
                "name": name,
                "old_readable": readable,
                "doctor": extract_doctor(appt.get("summary", ""), clinic_id),
                "clinic_id": clinic_id,
            }
            return {
                "response": "I found your appointment on " + readable + ". What new date and time would you like? I will move it once the new slot is confirmed.",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        session["lookup_pending"] = None
        return {
            "response": "Your appointment is on " + readable + ".",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    reschedule_pending = session.get("reschedule_pending")
    if reschedule_pending:
        return handle_reschedule_continuation(query, session, reschedule_pending)

    session["lookup_pending"] = None
    session["booking_in_progress"] = True

    pending = session.get("booking")
    requested_time = extract_time(query)
    unrecognized = mentions_unrecognized_doctor(query, clinic_id)
    if unrecognized:
        doctor_names = ", ".join(load_clinic(clinic_id).get("doctors", []))
        return {
            "response": "I am sorry, I do not have a doctor named " + unrecognized + ". Our available doctors are " + doctor_names + ". Would you like to book with one of them, or with no preference?",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    doctor = extract_doctor(query, clinic_id) or (pending.get("doctor") if pending else None)

    if pending and requested_time and requested_time not in pending["slots"]:
        slots_text = ", ".join(pending["slots"][:5])
        return {
            "response": "I am sorry, " + requested_time + " is not available. The open times are " + slots_text + ". Which of these would you like?",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    if pending and requested_time and requested_time in pending["slots"]:
        patient_name = extract_name(query) or "Patient"
        try:
            event_id = book_appointment(pending["date"], requested_time, patient_name, doctor=doctor, clinic_id=clinic_id)
        except Exception:
            return {
                "response": "I am having trouble confirming that booking right now. Please call reception to book directly.",
                "guardrailTriggered": False,
                "agent": "booking"
            }

        session["booking"] = None
        session["booking_in_progress"] = False
        webhooks.dispatch(clinic_id, "booking_created", {
            "clinic_id": clinic_id, "patient_name": patient_name,
            "date": pending["date"], "time": requested_time, "doctor": doctor,
        })
        doctor_text = " with " + doctor if doctor else ""
        return {
            "response": "You are all set! I have booked your appointment" + doctor_text + " for " + pending["date"] + " at " + requested_time + ". We look forward to seeing you.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    date_str = extract_date(query)

    if not date_str:
        prefix = ""
        if not is_clinic_open(clinic_id):
            prefix = hours_message(clinic_id) + " We are currently closed, but I can still help you book for a future date. "
        return {
            "response": prefix + "I would be happy to check availability. Could you tell me what date you would like to come in? For example, tomorrow, or a specific date.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    try:
        slots = get_available_slots(date_str, doctor=doctor, clinic_id=clinic_id)
    except Exception:
        return {
            "response": "I am having trouble checking the calendar right now. Please call reception to book directly.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

    if not slots:
        doctor_text = " with " + doctor if doctor else ""
        session["waitlist_offer"] = {"date": date_str, "doctor": doctor}
        return {
            "response": "I am sorry, there are no available slots" + doctor_text + " on " + date_str + ". Would you like me to add you to the waitlist so we can contact you if a slot opens up?",
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
