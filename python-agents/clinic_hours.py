from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def is_clinic_open():
    now = datetime.now(IST)
    weekday = now.weekday()
    hour_min = now.hour + now.minute / 60

    if weekday == 6:
        return False

    if weekday == 5:
        return 10 <= hour_min < 14

    return 9 <= hour_min < 18


def hours_message():
    return ("Our clinic is open Monday to Friday, 9am to 6pm, and Saturday "
            "10am to 2pm. We're closed on Sundays and public holidays.")
