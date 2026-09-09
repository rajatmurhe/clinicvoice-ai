import requests

FAQ_BACKEND_URL = "http://localhost:5050/api/text-query"


def handle_faq(query: str) -> dict:
    try:
        response = requests.post(
            FAQ_BACKEND_URL,
            json={"query": query},
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        return {
            "response": data.get("response", ""),
            "guardrailTriggered": data.get("guardrailTriggered", False),
            "agent": "faq"
        }
    except Exception as e:
        return {
            "response": "I'm having trouble accessing that information right now. Please call our reception team.",
            "guardrailTriggered": False,
            "agent": "faq",
            "error": str(e)
        }
