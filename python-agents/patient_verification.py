"""Match clinic-managed identity records; never enroll identity from chat.

A missing, malformed or ambiguous registry fails closed. This is knowledge
verification, not proof of phone possession (production should use OTP).
"""
import hmac
import json
import os
import re
import unicodedata
from clinic_config import load_clinic


def _name(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def verify_patient(name, supplied, clinic_id=None):
    path = os.environ.get("CLINICVOICE_PATIENT_REGISTRY")
    if not path:
        return False
    try:
        with open(path, encoding="utf-8") as stream:
            records = json.load(stream)
        clinic = load_clinic(clinic_id)["id"]
        matches = [r for r in records if r["clinic_id"] == clinic and _name(r["name"]) == _name(name)]
        if len(matches) != 1:
            return False
        record = matches[0]
        # Whole input, not a matching substring in an arbitrary sentence.
        candidate = unicodedata.normalize("NFKC", supplied).strip()
        phone = re.sub(r"[\s()+.-]", "", candidate)
        expected_phone = re.sub(r"[\s()+.-]", "", record.get("phone", ""))
        if re.fullmatch(r"[0-9]{7,15}", phone) and expected_phone:
            if hmac.compare_digest(phone, expected_phone):
                return True
        patient_id = record.get("patient_id", "")
        return bool(patient_id and hmac.compare_digest(candidate.encode(), patient_id.encode()))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
