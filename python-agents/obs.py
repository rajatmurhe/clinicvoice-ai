"""Request scoped logging for the orchestrator.

Every request gets an id (inherited from X-Request-ID when the caller or the
frontend supplied one). Every log line carries it and patient names are
redacted before anything is written.
"""

import json
import os
import re
import sys
import time
import uuid
from contextvars import ContextVar

_request_id = ContextVar("request_id", default="-")

# Patient names show up in three shapes: announced ("my name is Priya"),
# referenced in a reply ("booked under Priya") and possessives. Redact the
# announced and referenced forms; the reply text is also redacted so names the
# assistant repeats do not end up in logs either.
_REDACTIONS = [
    (re.compile(r"\b(my name is|this is|i am|i'm|im|name's)\s+([a-z][a-zA-Z]+(?:\s[a-z][a-zA-Z]+)?)", re.IGNORECASE), r"\1 [REDACTED]"),
    (re.compile(r"\b(under|for)\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)(?=[ .,!]|$)"), r"\1 [REDACTED]"),
]


def redact(text):
    if not text:
        return text
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


# Clinic id used when a request does not carry one (single tenant default).
DEFAULT_CLINIC_FALLBACK = os.environ.get("CLINICVOICE_CLINIC_ID", "default")


def set_request_id(request_id):
    _request_id.set(request_id)


def get_request_id():
    return _request_id.get()


def new_request_id():
    return uuid.uuid4().hex[:12]


def log_event(event, **fields):
    record = {
        "ts": round(time.time(), 3),
        "request_id": get_request_id(),
        "event": event,
    }
    for key, value in fields.items():
        record[key] = redact(value) if isinstance(value, str) else value
    # Structured logs go to stderr so stdout stays clean for API data and
    # harness output; container log collectors read both streams.
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr, flush=True)
