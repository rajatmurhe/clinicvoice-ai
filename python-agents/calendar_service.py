import datetime
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), 'service-account-key.json')
CALENDAR_ID = 'c7a96c6fe2ec8d04973de5e5f01444a92f8208e9c9d47ea7b7ea771be0695654@group.calendar.google.com'

def get_calendar_service():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=credentials)


def get_available_slots(date_str, duration_minutes=30):
    service = get_calendar_service()

    day_start = datetime.datetime.fromisoformat(date_str + "T09:00:00+05:30")
    day_end = datetime.datetime.fromisoformat(date_str + "T18:00:00+05:30")

    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    busy_slots = []
    for event in events:
        start = event['start'].get('dateTime')
        end = event['end'].get('dateTime')
        if start and end:
            busy_slots.append((
                datetime.datetime.fromisoformat(start),
                datetime.datetime.fromisoformat(end)
            ))

    available = []
    current = day_start
    slot_delta = datetime.timedelta(minutes=duration_minutes)

    while current + slot_delta <= day_end:
        slot_end = current + slot_delta
        overlaps = any(current < b_end and slot_end > b_start for b_start, b_end in busy_slots)
        if not overlaps:
            available.append(current.strftime('%I:%M %p'))
        current += slot_delta

    return available


def book_appointment(date_str, time_str, patient_name, duration_minutes=30):
    service = get_calendar_service()

    start_dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
    start_dt = start_dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)

    event = {
        'summary': f'Appointment - {patient_name}',
        'start': {'dateTime': start_dt.isoformat()},
        'end': {'dateTime': end_dt.isoformat()},
    }

    created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return created_event.get('id')


def find_appointments_by_name(patient_name, days_ahead=30):
    service = get_calendar_service()
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    time_max = now + datetime.timedelta(days=days_ahead)

    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=now.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy='startTime',
        q=patient_name
    ).execute()

    events = events_result.get('items', [])
    matches = []
    for event in events:
        summary = event.get('summary', '')
        if patient_name.lower() in summary.lower():
            start = event['start'].get('dateTime')
            matches.append({
                'id': event['id'],
                'summary': summary,
                'start': start
            })

    return matches


def cancel_appointment(event_id):
    service = get_calendar_service()
    service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    return True
