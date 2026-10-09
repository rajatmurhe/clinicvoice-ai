import re

def accepted_providers(clinic_id=None):
    from clinic_config import load_clinic

    return load_clinic(clinic_id).get("insurance_providers", [])


def check_provider(query: str, clinic_id=None):
    # Normalise spacing so "UnitedHealthcare" matches "united healthcare".
    query_norm = query.lower().replace(" ", "")
    for provider in accepted_providers(clinic_id):
        if provider.replace(" ", "") in query_norm:
            return provider
    return None


def handle_insurance(query: str, session: dict) -> dict:
    matched = check_provider(query, session.get("clinic_id"))

    if matched:
        return {
            "response": "Yes, we accept " + matched.title() + ". Please bring your insurance card to your appointment.",
            "guardrailTriggered": False,
            "agent": "insurance"
        }

    return {
        "response": "I do not have that specific provider confirmed in our accepted list. Please call reception to verify your coverage before your appointment.",
        "guardrailTriggered": False,
        "agent": "insurance"
    }
