def handle_escalation(query: str) -> dict:
    return {
        "response": "I understand this needs personal attention. I'm connecting you with our reception team who can help directly — please call us, or stay on the line if you reached us by phone.",
        "guardrailTriggered": False,
        "agent": "escalation"
    }
