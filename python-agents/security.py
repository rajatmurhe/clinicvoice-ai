"""Fail-closed access control. No credentials are exposed to the frontend."""
import base64
import hmac
import os
import re
import uuid


def request_id(value):
    return value if value and re.fullmatch(r'[A-Za-z0-9-]{1,64}', value) else str(uuid.uuid4())


def service_headers():
    return {'Authorization': 'Bearer ' + os.environ.get('CLINICVOICE_SERVICE_KEY', '')}


def authorized(header, setting, basic=False):
    expected = os.environ.get(setting, '')
    if len(expected) < 32:
        return False
    if not (header or '').startswith('Bearer ') and not (basic and (header or '').startswith('Basic ')):
        return False
    supplied = (header or '').removeprefix('Bearer ')
    if basic and (header or '').startswith('Basic '):
        try:
            decoded = base64.b64decode(header[6:], validate=True).decode()
            username, supplied = decoded.split(':', 1)
            if username != 'admin':
                return False
        except (ValueError, UnicodeError):
            return False
    return hmac.compare_digest(supplied.encode(), expected.encode())

from contextvars import ContextVar
demo_session = ContextVar("demo_session", default=None)
