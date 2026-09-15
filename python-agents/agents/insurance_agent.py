import re

ACCEPTED_PROVIDERS = [
    "united healthcare", "aetna", "cigna", "blue cross blue shield",
    "star health", "hdfc ergo", "icici lombard", "care health insurance",
    "national insurance", "new india assurance"
]


def check_provider(query: str):
    query_lower = query.lower()
    for provider in ACCEPTED_PROVIDERS:
        if provider in query_lower:
            return provider
    return None


def handle_insurance(query: str, session: dict) -> dict:
    matched = check_provider(query)

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
