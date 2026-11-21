import uuid
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

import main
import phone_workflow
from fake_calendar import FakeCalendar
from agents import booking_agent

ACCOUNT = 'AC' + 'a' * 32
TOKEN = 'test-twilio-token'
PUBLIC = 'https://phone.example'


@pytest.fixture
def phone(monkeypatch):
    monkeypatch.setenv('CLINICVOICE_PHONE_ENABLED', 'true')
    monkeypatch.setenv('TWILIO_ACCOUNT_SID', ACCOUNT)
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', TOKEN)
    monkeypatch.setenv('TWILIO_PUBLIC_URL', PUBLIC)
    fake = FakeCalendar()
    fake.reset()
    monkeypatch.setattr(booking_agent, 'get_available_slots', fake.get_available_slots)
    monkeypatch.setattr(booking_agent, 'book_appointment', fake.book_appointment)
    client = TestClient(main.app)
    call = 'CA' + uuid.uuid4().hex
    def send(turn, query='', digits='', confidence=None, signature=True):
        path = '/voice/twilio' + (f'?turn={turn}' if turn else '')
        data = dict(AccountSid=ACCOUNT, CallSid=call, SpeechResult=query, Digits=digits)
        if confidence is not None:
            data['Confidence'] = str(confidence)
        headers = {'X-Twilio-Signature': RequestValidator(TOKEN).compute_signature(PUBLIC + path, data)} if signature else {}
        return client.post(path, data=data, headers=headers)
    return send, fake


def test_signed_booking_intake_correction_and_retry(phone):
    send, fake = phone
    assert 'synthetic' in send(0).text
    assert 'test patient name' in send(1, digits='1').text
    send(2, 'Priya')
    send(3, 'Fever')
    assert 'Fever' in send(4, 'three days').text
    send(5, 'no')
    send(6, 'Cough')
    send(7, 'two days')
    send(8, 'yes')
    assert 'availability' in send(9, '2031-09-09').text
    assert 'Say yes to book' in send(10, '10:00 AM').text
    assert not fake.events_on('2031-09-09')
    r = send(11, 'yes')
    assert 'booked' in r.text
    assert send(11, 'yes').text == r.text
    assert len(fake.events_on('2031-09-09')) == 1
    row = phone_workflow.recent_calls()[0]
    assert row['patient_words'] == 'Cough'
    assert row['duration_words'] == 'two days'
    assert row['intake_status'] == 'patient_confirmed'
    assert row['booking_confirmation']['patient_name'] == 'Priya'


@pytest.mark.parametrize('digit, name, reason, duration, yes', [
    ('2', 'प्रिया', 'तीन दिन से बुखार', 'तीन दिन', 'हाँ'),
    ('3', 'प्रिया', 'ताप आहे', 'तीन दिवस', 'हो'),
])
def test_localized_intake(phone, digit, name, reason, duration, yes):
    send, _ = phone
    send(0); send(1, digits=digit); send(2, name); send(3, reason)
    response = send(4, duration)
    assert reason in response.text
    assert 'Saved' not in send(5, yes).text
    assert phone_workflow.recent_calls()[0]['intake_status'] == 'patient_confirmed'


def test_fails_closed_and_rejects_out_of_order(phone, monkeypatch):
    send, _ = phone
    assert send(0, signature=False).status_code == 403
    assert send(4).status_code == 400
    monkeypatch.setenv('CLINICVOICE_PHONE_ENABLED', 'false')
    assert send(0).status_code == 503


def test_uncertain_speech_is_not_saved(phone):
    send, _ = phone
    send(0); send(1, digits='1')
    assert 'repeat' in send(2, 'Priya', confidence=.2).text
    assert phone_workflow.recent_calls()[0]['stage'] == 'name'


def test_emergency_during_confirmation_never_books(phone):
    send, fake = phone
    send(0); send(1, digits='1'); send(2, 'Priya'); send(3, 'fever'); send(4, 'two days')
    root = ET.fromstring(send(5, 'I have chest pain').text)
    assert root.find('Hangup') is not None
    assert 'No clinic alert' in root.find('Say').text
    assert phone_workflow.recent_calls()[0]['outcome'] == 'safety_escalation'
    assert not fake.events_on('2031-09-09')


def test_staff_endpoint_requires_admin(phone):
    client = TestClient(main.app)
    assert client.get('/api/dashboard/phone-calls').status_code == 401


def test_silence_ends_after_three_attempts(phone):
    send, _ = phone
    send(0); send(1, digits='1')
    send(2); send(3)
    assert ET.fromstring(send(4).text).find('Hangup') is not None


def test_skip_intake_and_decline_booking(phone):
    send, fake = phone
    send(0); send(1, digits='1'); send(2, 'Priya'); send(3, 'skip')
    send(4, '2031-09-09'); send(5, '10:00 AM')
    send(6, 'no')
    assert not fake.events_on('2031-09-09')
    assert phone_workflow.recent_calls()[0]['stage'] == 'booking'


def test_medical_advice_does_not_get_stored_as_intake(phone):
    send, _ = phone
    send(0); send(1, digits='1'); send(2, 'Priya')
    assert 'not able' in send(3, 'What medicine should I take?').text
    assert phone_workflow.recent_calls()[0]['stage'] == 'reason'


def test_staff_can_read_confirmed_intake(phone, monkeypatch):
    send, _ = phone
    send(0); send(1, digits='1'); send(2, '<test>'); send(3, 'cough'); send(4, 'two days'); send(5, 'yes')
    monkeypatch.setenv('CLINICVOICE_ADMIN_TOKEN', 'a' * 32)
    r = TestClient(main.app).get('/api/dashboard/phone-calls', headers={'Authorization': 'Bearer ' + 'a' * 32})
    assert r.status_code == 200
    assert r.json()['calls'][0]['patient_words'] == 'cough'


def test_changed_date_is_checked_before_booking_confirmation(phone):
    send, fake = phone
    send(0); send(1, digits='1'); send(2, 'Priya'); send(3, 'skip')
    send(4, '2031-09-09')
    response = send(5, '2031-09-10 at 10:00 AM')
    assert '2031-09-10' in response.text
    assert 'Say yes to book' not in response.text
    assert not fake.events_on('2031-09-09')


def test_nan_confidence_rejected(phone):
    send, _ = phone
    send(0)
    assert send(1, confidence='nan').status_code == 400
