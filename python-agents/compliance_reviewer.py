"""Compliance reviewer: screens every agent reply against policy before it is
spoken. Rule based, no LLM, so it adds no latency and no cost.

CLINICVOICE_COMPLIANCE_REVIEWER=true turns it on. The eval decides whether it
stays: it must block unsafe replies without blocking safe ones.
"""

import re

import obs

# Output policy: the assistant must never leak personal data it was not given,
# never state clinical facts, and never ask for identity documents.
BLOCKED_REPLY_PATTERNS = [
    (re.compile(r"\b(you (should|must) take|take \d+|recommended dose|dosage of)\b", re.IGNORECASE), "clinical_advice"),
    (re.compile(r"\bi diagnose|you (have|are suffering from) (cancer|a disease|diabetes|hypertension)\b", re.IGNORECASE), "diagnosis"),
    (re.compile(r"\b(nhs number|social security|passport number)\b.*\b(is|:)\s*\d", re.IGNORECASE), "pii_value"),
    (re.compile(r"\bwhat is your (date of birth|nhs number)\b", re.IGNORECASE), "identity_fishing"),
]

REDACTION_PATTERNS = [
    (re.compile(r"\b(my name is|this is|i am|i'm)\s+([a-z][a-zA-Z]+(?:\s[a-z][a-zA-Z]+)?)", re.IGNORECASE), r"\1 [REDACTED]"),
]


def review_reply(reply: str) -> dict:
    for pattern, violation in BLOCKED_REPLY_PATTERNS:
        match = pattern.search(reply or "")
        if match:
            obs.log_event("compliance_review", verdict="blocked", violation=violation)
            return {
                "verdict": "blocked",
                "violation": violation,
                "response": "I am not able to help with that. Please contact the clinic directly.",
            }
    return {"verdict": "pass", "response": reply}
