"""Patient-confirmed telephone intake; reuses the existing agent orchestrator.

SQLite serialises turns and caches responses so webhook retries do not repeat
side effects. This is a synthetic-data pilot, not a clinical triage service.
"""
import json
from contextlib import contextmanager
import os
import sqlite3
import time

from agents.language import localized
from agents.booking_agent import extract_time, extract_date
from safety import check_emergency, check_input_safety, blocked_response_for

DB_PATH = os.path.join(os.environ.get('CLINICVOICE_DATA_DIR') or os.path.dirname(__file__), 'phone.sqlite')


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute('CREATE TABLE IF NOT EXISTS phone_calls (call_id TEXT PRIMARY KEY, state TEXT NOT NULL, turn INTEGER NOT NULL, reply TEXT NOT NULL, updated REAL NOT NULL)')
    conn.commit()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def recent_calls():
    with connect() as conn:
        rows = conn.execute('SELECT state, updated FROM phone_calls ORDER BY updated DESC LIMIT 50').fetchall()
    return [dict(json.loads(state), updated=updated) for state, updated in rows]


def text(s, en, hi, mr):
    return localized(s, en, hi, mr)


def answer(s, response, mode='speech'):
    return {'response': response, 'language': s.get('language', 'en'), 'mode': mode, 'stage': s['stage']}


def advance(s, query, digits, confidence, run_agent):
    if s['stage'] == 'ended':
        return answer(s, text(s, 'This call has ended. Goodbye.', 'यह कॉल समाप्त हो गई है। धन्यवाद।', 'हा कॉल संपला आहे. धन्यवाद.'), 'end')
    # Check every speech turn, including names, corrections, and confirmations.
    if query and check_emergency(query):
        s['stage'] = 'ended'
        s['outcome'] = 'safety_escalation'
        s['safety_flag'] = True
        return answer(s, text(s,
            'This may be an emergency. Please contact your local emergency service or seek urgent in-person care now. This assistant cannot assess your condition. No clinic alert or emergency call has been sent.',
            'यह आपातकाल हो सकता है। अभी स्थानीय आपातकालीन सेवा से संपर्क करें या तुरंत अस्पताल जाएँ। यह सहायक आपकी स्थिति का आकलन नहीं कर सकता। क्लिनिक या आपातकालीन सेवा को सूचना नहीं भेजी गई है।',
            'ही आपत्कालीन परिस्थिती असू शकते. आत्ताच स्थानिक आपत्कालीन सेवेशी संपर्क करा किंवा तातडीने रुग्णालयात जा. हा सहाय्यक तुमच्या स्थितीचे मूल्यांकन करू शकत नाही. क्लिनिक किंवा आपत्कालीन सेवेला सूचना पाठवलेली नाही.'), 'end')
    if query and (confidence is not None and confidence < 0.6):
        return answer(s, text(s, 'I did not hear that clearly. Please repeat.', 'स्पष्ट सुनाई नहीं दिया। कृपया फिर से बोलें।', 'स्पष्ट ऐकू आले नाही. कृपया पुन्हा सांगा.'))
    if query and check_input_safety(query):
        return answer(s, blocked_response_for(query))
    if s['stage'] == 'language':
        if digits not in ('1', '2', '3'):
            return answer(s, 'ClinicVoice synthetic-data demo. Your spoken answers will be transcribed and stored for staff review. Use test details only. To agree and continue, press 1 for English, 2 for Hindi, or 3 for Marathi. Otherwise hang up.', 'language')
        s['language'] = {'1': 'en', '2': 'hi', '3': 'mr'}[digits]
        s['consent'] = True
        s['stage'] = 'name'
        return answer(s, text(s, 'Please say your test patient name.', 'कृपया अपना परीक्षण नाम बताएं।', 'कृपया तुमचे चाचणीसाठीचे नाव सांगा.'))
    if not query:
        s['silence'] = s.get('silence', 0) + 1
        if s['silence'] >= 3:
            s['stage'] = 'ended'
            s['outcome'] = 'no_input'
            return answer(s, text(s, 'No answer received. Please call again. Goodbye.', 'जवाब नहीं मिला। कृपया फिर कॉल करें।', 'उत्तर मिळाले नाही. कृपया पुन्हा कॉल करा.'), 'end')
        return answer(s, s['last_prompt'])
    s['silence'] = 0
    if s['stage'] == 'name':
        s['patient_name'] = query
        s['stage'] = 'reason'
        return answer(s, text(s, 'In your own words, why would you like a visit? Say skip to book without sharing symptoms.', 'आप क्यों मिलना चाहते हैं? अपने शब्दों में बताएं। लक्षण बताए बिना बुक करने के लिए स्किप कहें।', 'तुम्हाला भेट का हवी आहे? तुमच्या शब्दांत सांगा. लक्षणे न सांगता बुक करण्यासाठी स्किप म्हणा.'))
    if s['stage'] == 'reason':
        if query.lower().strip() in ('skip', 'स्किप'):
            s['intake_status'] = 'skipped'
            s['stage'] = 'booking'
            s.setdefault('agent_session', {})['booking_in_progress'] = True
            return answer(s, text(s, 'What date would you like your appointment?', 'किस तारीख की अपॉइंटमेंट चाहिए?', 'कोणत्या तारखेची अपॉइंटमेंट हवी?'))
        s['patient_words'] = query
        s['stage'] = 'duration'
        return answer(s, text(s, 'How long has this been happening? Say unknown if you are unsure.', 'यह कब से हो रहा है? पता नहीं तो बताएं।', 'हे किती दिवसांपासून होत आहे? माहीत नसेल तर तसे सांगा.'))
    if s['stage'] == 'duration':
        s['duration_words'] = query
        s['stage'] = 'confirm'
        summary = f"{s['patient_name']}. {s['patient_words']}. {s['duration_words']}. "
        return answer(s, summary + text(s, 'Is this correct? Say yes to save, or no to describe it again.', 'क्या यह सही है? सहेजने के लिए हाँ, फिर बताने के लिए नहीं कहें।', 'हे बरोबर आहे का? जतन करण्यासाठी हो, पुन्हा सांगण्यासाठी नाही म्हणा.'))
    if s['stage'] == 'confirm':
        q = query.lower().strip(' .!?।')
        if q in ('no', 'नहीं', 'नही', 'नाही', 'नको'):
            s.pop('patient_words', None)
            s.pop('duration_words', None)
            s['stage'] = 'reason'
            return answer(s, text(s, 'Please describe your reason for the visit again.', 'कृपया मिलने का कारण फिर बताएं।', 'कृपया भेटीचे कारण पुन्हा सांगा.'))
        if q not in ('yes', 'correct', 'हाँ', 'हां', 'हो', 'होय', 'बरोबर'):
            return answer(s, s['last_prompt'])
        s['intake_status'] = 'patient_confirmed'
        s['stage'] = 'booking'
        s.setdefault('agent_session', {})['booking_in_progress'] = True
        return answer(s, text(s, 'Saved for staff review. This is not a medical assessment. What date would you like your appointment?', 'स्टाफ की समीक्षा के लिए सहेजा गया है। यह चिकित्सा आकलन नहीं है। किस तारीख की अपॉइंटमेंट चाहिए?', 'कर्मचाऱ्यांच्या पाहणीसाठी जतन केले. हे वैद्यकीय मूल्यांकन नाही. कोणत्या तारखेची अपॉइंटमेंट हवी?'))
    if s['stage'] == 'booking_confirm':
        q = query.lower().strip(' .!?।')
        if q in ('no', 'नहीं', 'नही', 'नाही', 'नको'):
            s['stage'] = 'booking'
            s.pop('proposed_time', None)
            return answer(s, text(s, 'Please choose another time or date.', 'कृपया दूसरा समय या तारीख चुनें।', 'कृपया दुसरी वेळ किंवा तारीख निवडा.'))
        if q not in ('yes', 'correct', 'हाँ', 'हां', 'हो', 'होय', 'बरोबर'):
            return answer(s, s['last_prompt'])
        query = s.pop('proposed_time')
        s['stage'] = 'booking'
    else:
        pending = s.get('agent_session', {}).get('booking')
        new_date = extract_date(query)
        if pending and new_date and new_date != pending['date']:
            s['agent_session']['booking'] = None
            pending = None
        selected_time = extract_time(query)
        if pending and selected_time in pending.get('slots', []):
            s['proposed_time'] = selected_time
            s['stage'] = 'booking_confirm'
            details = f"{pending['date']}, {selected_time}. "
            return answer(s, details + text(s, 'Say yes to book this appointment, or no to change it.', 'बुक करने के लिए हाँ, बदलने के लिए नहीं कहें।', 'बुक करण्यासाठी हो, बदलण्यासाठी नाही म्हणा.'))
    result = run_agent(query, s)
    s['outcome'] = result.get('intent', result.get('agent', 'unknown'))
    # The shared handler exposes structured booking metadata on success.
    if result.get('booking_confirmation'):
        s['booking_confirmation'] = result['booking_confirmation']
        s['outcome'] = 'booked'
        s['stage'] = 'ended'
        return answer(s, result['response'], 'end')
    return answer(s, result['response'])


def turn(call_id, number, query='', digits='', confidence=None, run_agent=None):
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT state, turn, reply FROM phone_calls WHERE call_id=?', (call_id,)).fetchone()
        if row and number <= row[1]:
            return json.loads(row[2])
        if (row and number != row[1] + 1) or (not row and number != 0):
            raise ValueError('Unexpected telephone turn')
        s = json.loads(row[0]) if row else {'stage': 'language', 'language': 'en', 'outcome': 'in_progress', 'safety_flag': False}
        if number >= 60:
            s['stage'] = 'ended'
        result = advance(s, query, digits, confidence, run_agent)
        s['last_prompt'] = result['response']
        result['next_turn'] = number + 1
        conn.execute('INSERT OR REPLACE INTO phone_calls VALUES (?, ?, ?, ?, ?)', (call_id, json.dumps(s), number, json.dumps(result), time.time()))
    return result
