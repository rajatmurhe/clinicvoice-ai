import re
import time
from patient_verification import verify_patient
from datetime import datetime, timedelta
from tools_backend import get_available_slots, book_appointment, find_appointments_by_name, cancel_appointment
from clinic_hours import is_clinic_open, hours_message
from clinic_config import load_clinic
import webhooks
from waitlist import add_to_waitlist, notify_waitlist
from agents.extract import extract_person_name, is_yes_no_answer
from agents.language import localized


def extract_date(query: str):
    today = datetime.now()

    if re.search(r"\btomorrow\b|कल|उद्या", query, re.IGNORECASE):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    if re.search(r"\bday after tomorrow\b|परसों|परवा", query, re.IGNORECASE):
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")

    if re.search(r"\btoday\b|आज", query, re.IGNORECASE):
        return today.strftime("%Y-%m-%d")

    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", query)
    if date_match:
        candidate = date_match.group(1)
        try:
            datetime.strptime(candidate, "%Y-%m-%d")
        except ValueError:
            # 2031-13-45 style strings match the shape but are not real dates;
            # return None so the caller asks for a valid date instead of
            # failing inside the calendar call.
            return None
        return candidate

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
    # Accept 24-hour times commonly spoken in Hindi/Marathi (e.g. 14:45).
    time_24h = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b(?!\s*(?:a\.?m\.?|p\.?m\.?))", query, re.IGNORECASE)
    if time_24h:
        parsed = datetime.strptime(time_24h.group(0), "%H:%M")
        return parsed.strftime("%I:%M %p")

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


def extract_appointment_subject(query: str):
    """Get an explicitly named patient from a lookup request for verification.

    This never performs the lookup itself; callers still require the registered
    phone or patient ID before reading or changing appointment data.
    """
    patterns = (
        r"(?:appointment|booking) for ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        r"(?:time is|appointment for) ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)['’]s?\s+appointment",
        r"(?:does) ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?) have an appointment",
    )
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate.lower() not in {"my", "the", "an", "all", "whose"}:
                return candidate
    return None


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



def booking_language(session, english, hindi, marathi):
    """Select a short deterministic prompt in the caller's chosen language."""
    return localized(session, english, hindi, marathi)


def handle_reschedule_continuation(query: str, session: dict, reschedule_pending: dict) -> dict:
    """Continues a reschedule after the appointment was found: takes the new
    date (and optionally time), confirms the new slot, then cancels the old one."""
    clinic_id = reschedule_pending.get("clinic_id")
    new_date = extract_date(query) or reschedule_pending.get("new_date")
    new_time = extract_time(query)

    if not new_date:
        return {
            "response": "Sure, which new date would you like? For example, tomorrow or a specific date.",
            "guardrailTriggered": False,
            "agent": "booking"
        }

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

    # Availability must be verified at confirm time even if a slot list was
    # already shown: someone else may have taken the slot in between, and a
    # blind booking would double book the calendar.
    try:
        open_slots = get_available_slots(new_date, doctor=reschedule_pending.get("doctor"), clinic_id=clinic_id)
    except Exception:
        return {
            "response": "I am having trouble checking the calendar right now. Please call reception to reschedule.",
            "guardrailTriggered": False,
            "agent": "booking"
        }
    if new_time not in open_slots:
        return {
            "response": "I am sorry, " + new_time + " is not available on " + new_date + ". The open times are " + ", ".join(open_slots[:5]) + ". Which of these would you like?",
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

    # Handle verification for lookup, cancel, or reschedule
    verification_pending = session.get("verification_pending")
    if verification_pending:
        if time.time() - verification_pending.get("created_at", 0) > 300:
            session["verification_pending"] = None
            return {"response": booking_language(session, "Verification expired. Please start again or call reception.", "सत्यापन का समय समाप्त हो गया है। कृपया फिर से शुरू करें या रिसेप्शन पर कॉल करें।", "पडताळणीची मुदत संपली आहे. कृपया पुन्हा सुरू करा किंवा रिसेप्शनला फोन करा."), "guardrailTriggered": False, "agent": "booking"}
        verification_pending["attempts"] += 1
        if verify_patient(verification_pending["name"], query, clinic_id):
            name = verification_pending["name"]
            # Do not query the calendar or reveal whether a name exists until verified.
            try:
                matches = find_appointments_by_name(name, clinic_id=clinic_id)
            except Exception:
                session["verification_pending"] = None
                return {"response": "I could not check the calendar. Please call reception.", "guardrailTriggered": False, "agent": "booking"}
            session["verification_pending"] = None
            # Calendar adapters may use substring search; require an exact patient name.
            matches = [a for a in matches if re.sub(r"\s+\(Dr\..*\)$", "", a.get("summary", "").removeprefix("Appointment - ")).strip().casefold() == name.strip().casefold()]
            if len(matches) != 1:
                return {"response": "Please call reception to locate the correct appointment.", "guardrailTriggered": False, "agent": "booking"}
            appt = matches[0]
            appt_time = datetime.fromisoformat(appt["start"])
            readable = appt_time.strftime("%A, %B %d at %I:%M %p")
            appt_date = appt_time.strftime("%Y-%m-%d")

            session["verification_pending"] = None

            if verification_pending.get("type") == "cancel":
                try:
                    cancel_appointment(appt["id"], clinic_id=clinic_id)
                except Exception:
                    return {
                        "response": "I found the appointment, but could not cancel it just now. Please call reception directly.",
                        "guardrailTriggered": False,
                        "agent": "booking"
                    }
                webhooks.dispatch(clinic_id, "booking_cancelled", {
                    "clinic_id": clinic_id, "patient_name": name,
                    "date": appt_date, "time": readable,
                })
                notified = notify_waitlist(appt_date)
                waitlist_note = " I have also notified " + str(notified) + " waitlisted patient(s) for that date." if notified else ""
                return {
                    "response": booking_language(session,
                        "Thank you. Your appointment on " + readable + " has been cancelled." + waitlist_note + " Let me know if you would like to book a new one.",
                        "धन्यवाद। " + readable + " की आपकी अपॉइंटमेंट रद्द कर दी गई है। क्या आप नई अपॉइंटमेंट बुक करना चाहेंगे?",
                        "धन्यवाद. " + readable + " ची तुमची अपॉइंटमेंट रद्द केली आहे. नवीन अपॉइंटमेंट बुक करायची आहे का?"),
                    "guardrailTriggered": False,
                    "agent": "booking"
                }

            if verification_pending.get("type") == "reschedule":
                session["reschedule_pending"] = {
                    "event_id": appt["id"],
                    "name": name,
                    "old_readable": readable,
                    "doctor": extract_doctor(appt.get("summary", ""), clinic_id),
                    "clinic_id": clinic_id,
                }
                return {
                    "response": booking_language(session,
                        "Thank you. I found your appointment on " + readable + ". What new date and time would you like? I will move it once the new slot is confirmed.",
                        "धन्यवाद। आपकी अपॉइंटमेंट " + readable + " को है। आप कौन सी नई तारीख़ और समय चाहेंगे? नया समय पक्का होने पर मैं इसे बदल दूँगा।",
                        "धन्यवाद. तुमची अपॉइंटमेंट " + readable + " रोजी आहे. नवीन तारीख आणि वेळ कोणती हवी? नवीन वेळ निश्चित झाल्यावर मी ती बदलतो."),
                    "guardrailTriggered": False,
                    "agent": "booking"
                }

            return {
                "response": booking_language(session,
                    "Thank you. Your appointment is on " + readable + ".",
                    "धन्यवाद। आपकी अपॉइंटमेंट " + readable + " को है।",
                    "धन्यवाद. तुमची अपॉइंटमेंट " + readable + " रोजी आहे."),
                "guardrailTriggered": False,
                "agent": "booking"
            }
        else:
            if verification_pending["attempts"] >= 3:
                session["verification_pending"] = None
                return {"response": booking_language(session, "I could not verify your details. Please call reception for help.", "मैं आपकी जानकारी सत्यापित नहीं कर सका। कृपया सहायता के लिए रिसेप्शन पर कॉल करें।", "तुमची माहिती पडताळता आली नाही. कृपया मदतीसाठी रिसेप्शनला फोन करा."), "guardrailTriggered": True, "agent": "booking"}
            return {
                "response": booking_language(session, "I couldn't verify those details. Please enter the phone number or patient ID registered with the clinic, or contact reception.", "ये जानकारी सत्यापित नहीं हो सकी। कृपया क्लिनिक में दर्ज फ़ोन नंबर या मरीज़ आईडी दें, या रिसेप्शन से संपर्क करें।", "ही माहिती पडताळता आली नाही. कृपया क्लिनिकमध्ये नोंदवलेला फोन नंबर किंवा रुग्ण आयडी द्या, किंवा रिसेप्शनशी संपर्क साधा."),
                "guardrailTriggered": False,
                "agent": "booking"
            }

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
        if extract_name(query) is None and is_yes_no_answer(query):
            session["waitlist_offer"] = None
            return {
                "response": "No problem, I have not added you to the waitlist. Would you like me to check a different date?",
                "guardrailTriggered": False,
                "agent": "booking"
            }
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

    is_lookup = re.search(r"(when is|what time is|do i have|does .* have an appointment|appointment time|booking time|appointment details|appointment status|whose appointment|who has .*appointment|look up .*appointment|find .*appointment|check .*appointment|appointment for|कब है|किस समय|माझी.*अपॉइंटमेंट.*कधी)", query, re.IGNORECASE)
    is_cancel = re.search(r"\bcancel\b|रद्द|कॅन्सल|रद्द कर", query, re.IGNORECASE)
    is_reschedule = re.search(r"\breschedule\b|तारीख बदल|वेळ बदल|पुढे ढकल|दूसरी तारीख|तारीख आगे", query, re.IGNORECASE)
    pending_lookup = session.get("lookup_pending")

    # A reply to "could you tell me the name the appointment is booked under?"
    # is usually just the name ("Priya"), with no cancel/lookup keyword in it.
    # Treat any message that carries the keywords, or answers a pending lookup
    # without starting a fresh booking, as part of the lookup flow.
    fresh_booking_start = re.search(
        r"book|schedule|appointment|slot|see (a|the) doctor|come in|बुक|अपॉइंटमेंट|अपॉईंटमेंट|भेट ठरव|डॉक्टर.*दाखव|मुलाकात|नियुक्ति", query, re.IGNORECASE
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
            if extract_name(query) is None and is_yes_no_answer(query):
                session["lookup_pending"] = None
                return {
                    "response": "Okay, I have left that. Let me know if there is anything else I can help with.",
                    "guardrailTriggered": False,
                    "agent": "booking"
                }
            name = extract_name(query) or query.strip()
        else:
            name = extract_name(query) or extract_appointment_subject(query)

        if not name:
            session["lookup_pending"] = pending_lookup
            return {
                "response": booking_language(session,
                    "Sure, could you tell me the name the appointment is booked under?",
                    "ज़रूर, अपॉइंटमेंट किस नाम से बुक है?",
                    "नक्की, अपॉइंटमेंट कोणत्या नावाने बुक केली आहे?"),
                "guardrailTriggered": False,
                "agent": "booking"
            }

        # Determine intent for verification state
        v_type = "lookup"
        if pending_lookup == "cancel" or is_cancel:
            v_type = "cancel"
        elif pending_lookup == "reschedule" or is_reschedule:
            v_type = "reschedule"

        session["verification_pending"] = {
            "name": name,
            "created_at": time.time(),
            "attempts": 0,
            "type": v_type
        }
        session["lookup_pending"] = None
        return {
            "response": booking_language(session,
                "Before I look up an appointment, please provide your phone number or patient ID registered with the clinic.",
                "अपॉइंटमेंट की जानकारी देखने से पहले, कृपया क्लिनिक में दर्ज अपना फ़ोन नंबर या मरीज़ आईडी बताएँ।",
                "अपॉइंटमेंटची माहिती पाहण्यापूर्वी, कृपया क्लिनिकमध्ये नोंदवलेला फोन नंबर किंवा रुग्ण आयडी सांगा."),
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
            "response": booking_language(
                session,
                "You are all set! I have booked your appointment" + doctor_text + " for " + pending["date"] + " at " + requested_time + ". We look forward to seeing you.",
                "आपकी अपॉइंटमेंट " + pending["date"] + " को " + requested_time + " पर बुक हो गई है। हम आपसे मिलने की प्रतीक्षा करेंगे।",
                "तुमची अपॉइंटमेंट " + pending["date"] + " रोजी " + requested_time + " वाजता बुक झाली आहे. आम्ही तुमची वाट पाहत आहोत."
            ),
            "guardrailTriggered": False,
            "agent": "booking"
        }

    date_str = extract_date(query)

    if not date_str:
        prefix = ""
        if not is_clinic_open(clinic_id):
            prefix = hours_message(clinic_id) + " We are currently closed, but I can still help you book for a future date. "
        return {
            "response": prefix + booking_language(
                session,
                "I would be happy to check availability. Could you tell me what date you would like to come in? For example, tomorrow, or a specific date.",
                "ज़रूर, आप किस तारीख़ को आना चाहेंगे? उदाहरण के लिए, कल या कोई खास तारीख़ बताइए।",
                "नक्की, तुम्हाला कोणत्या तारखेला यायचे आहे? उदाहरणार्थ, उद्या किंवा एखादी ठराविक तारीख सांगा."
            ),
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
        "response": booking_language(
            session,
            "On " + date_str + doctor_text + ", we have availability at " + slots_text + ". Would you like me to book one of these for you?",
            date_str + doctor_text + " को ये समय उपलब्ध हैं: " + slots_text + ". क्या मैं इनमें से कोई समय बुक कर दूँ?",
            date_str + doctor_text + " रोजी हे वेळ उपलब्ध आहेत: " + slots_text + ". यापैकी एखादी वेळ बुक करू का?"
        ),
        "guardrailTriggered": False,
        "agent": "booking"
    }
