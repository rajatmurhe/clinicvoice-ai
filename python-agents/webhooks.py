"""Outbound webhooks with signed payloads and retries.

Clinics configure webhooks in their config (clinics/<id>.json -> "webhooks"):
a list of {"url", "secret"} entries. Events: booking_created,
booking_cancelled, escalation_raised. Each POST carries the event name and an
HMAC-SHA256 signature of the body so the receiver can authenticate it, and is
retried up to three times with backoff on failure. Delivery happens on a
background thread so the patient's reply is never delayed by a slow receiver.
"""

import hashlib
import hmac
import json
import threading
import time

import obs

RETRY_DELAYS = (0.4, 0.8, 1.6)


def sign_payload(body_bytes, secret):
    return hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()


def _deliver(url, secret, event, payload):
    import requests

    body = json.dumps({"event": event, "clinic_id": payload.get("clinic_id"), "data": payload}).encode()
    headers = {
        "Content-Type": "application/json",
        "X-ClinicVoice-Event": event,
        "X-ClinicVoice-Signature": sign_payload(body, secret),
    }
    for attempt, delay in enumerate((0,) + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            r = requests.post(url, data=body, headers=headers, timeout=(3, 10))
            if r.status_code < 300:
                obs.log_event("webhook_delivered", event_name=event, url=url, attempts=attempt + 1)
                return True
        except Exception as e:
            obs.log_event("webhook_attempt_failed", event_name=event, error_type=type(e).__name__)
    obs.log_event("webhook_failed", event_name=event, url=url)
    return False


def dispatch(clinic_id, event, payload):
    """Fire event webhooks for a clinic in the background."""
    from clinic_config import load_clinic

    hooks = load_clinic(clinic_id).get("webhooks", [])
    for hook in hooks:
        url = hook.get("url")
        secret = hook.get("secret") or ""
        if not url:
            continue
        thread = threading.Thread(
            target=_deliver, args=(url, secret, event, payload), daemon=True
        )
        thread.start()
    return len(hooks)
