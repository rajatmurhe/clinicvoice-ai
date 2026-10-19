from agents.language import localized

def handle_escalation(query: str, session=None) -> dict:
    return {
        "response": localized(session, "I understand this needs personal attention. I'm connecting you with our reception team who can help directly — please call us, or stay on the line if you reached us by phone.", "मैं समझता हूँ कि इस मामले में व्यक्तिगत सहायता चाहिए। हमारी रिसेप्शन टीम सीधे मदद कर सकती है—कृपया हमें कॉल करें या फोन पर हैं तो लाइन पर बने रहें।", "या प्रकरणासाठी वैयक्तिक मदत आवश्यक आहे हे मला समजते. आमची रिसेप्शन टीम थेट मदत करेल—कृपया आम्हाला फोन करा किंवा फोनवर असल्यास लाईनवर थांबा."),
        "guardrailTriggered": False,
        "agent": "escalation"
    }
