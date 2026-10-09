"""Per clinic configuration.

Clinic specific data lives in clinics/<clinic_id>.json: hours, doctors,
accepted insurance providers, optional inline FAQs, tone and languages, plus
which scheduling adapter and webhooks to use. A second clinic onboards with a
config file only, no code change.

The clinic id comes from the request (session.clinic_id, set by /api/agent-query)
or from CLINICVOICE_CLINIC_ID for single tenant deployments. The default clinic
reproduces the pre multi-tenant behavior exactly.
"""

import json
import os
from datetime import datetime, timedelta, timezone

_CLINICS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clinics")
_CACHE = {}

DEFAULT_CLINIC_ID = os.environ.get("CLINICVOICE_CLINIC_ID", "default")


def load_clinic(clinic_id=None):
    cid = clinic_id or DEFAULT_CLINIC_ID
    if cid in _CACHE:
        return _CACHE[cid]
    path = os.path.join(_CLINICS_DIR, cid + ".json")
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    _CACHE[cid] = config
    return config


def clinic_timezone(config):
    offset = config.get("timezone_offset_minutes", 330)
    return timezone(timedelta(minutes=offset))


def is_clinic_open(clinic_id=None, now=None):
    config = load_clinic(clinic_id)
    now = now or datetime.now(clinic_timezone(config))
    weekday = now.weekday()
    hour_min = now.hour + now.minute / 60

    windows = config.get("hours", {})
    if weekday == 6:
        window = windows.get("sunday")
    elif weekday == 5:
        window = windows.get("saturday")
    else:
        window = windows.get("monday_friday")
    if not window:
        return False
    open_h, open_m = (int(x) for x in window["open"].split(":"))
    close_h, close_m = (int(x) for x in window["close"].split(":"))
    return open_h + open_m / 60 <= hour_min < close_h + close_m / 60


def hours_message(clinic_id=None):
    return load_clinic(clinic_id).get("hours_message", "")
