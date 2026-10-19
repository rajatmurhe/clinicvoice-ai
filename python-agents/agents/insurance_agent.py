import re
from agents.language import localized

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
            "response": localized(session,
                "Yes, we accept " + matched.title() + ". Please bring your insurance card to your appointment.",
                "हाँ, हम " + matched.title() + " स्वीकार करते हैं। कृपया अपॉइंटमेंट पर अपना बीमा कार्ड लाएँ।",
                "हो, आम्ही " + matched.title() + " स्वीकारतो. कृपया अपॉइंटमेंटला तुमचे विमा कार्ड आणा."),
            "guardrailTriggered": False,
            "agent": "insurance"
        }

    return {
        "response": localized(session,
            "I do not have that specific provider confirmed in our accepted list. Please call reception to verify your coverage before your appointment.",
            "यह बीमा प्रदाता हमारी पुष्टि की गई सूची में नहीं है। अपॉइंटमेंट से पहले कवरेज की पुष्टि के लिए कृपया रिसेप्शन पर कॉल करें।",
            "हा विमा प्रदाता आमच्या पुष्टी केलेल्या यादीत नाही. अपॉइंटमेंटपूर्वी कव्हरेजची खात्री करण्यासाठी कृपया रिसेप्शनला फोन करा."),
        "guardrailTriggered": False,
        "agent": "insurance"
    }
