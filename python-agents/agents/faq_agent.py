import requests
import time
from semantic_cache import check_cache, store_in_cache

FAQ_BACKEND_URL = "http://localhost:5050/api/text-query"


def handle_faq(query: str) -> dict:
    start = time.time()

    cached = check_cache(query)
    if cached:
        elapsed_ms = round((time.time() - start) * 1000, 1)
        return {
            "response": cached["response"],
            "guardrailTriggered": cached["guardrailTriggered"],
            "agent": "faq",
            "cache_hit": True,
            "matched_query": cached["matched_query"],
            "similarity": cached["similarity"],
            "latency_ms": elapsed_ms
        }

    try:
        response = requests.post(
            FAQ_BACKEND_URL,
            json={"query": query},
            timeout=15
        )
        response.raise_for_status()
        data = response.json()

        result_response = data.get("response", "")
        guardrail_triggered = data.get("guardrailTriggered", False)

        if not guardrail_triggered:
            store_in_cache(query, result_response, guardrail_triggered)

        elapsed_ms = round((time.time() - start) * 1000, 1)
        return {
            "response": result_response,
            "guardrailTriggered": guardrail_triggered,
            "agent": "faq",
            "cache_hit": False,
            "latency_ms": elapsed_ms
        }
    except Exception as e:
        return {
            "response": "I'm having trouble accessing that information right now. Please call our reception team.",
            "guardrailTriggered": False,
            "agent": "faq",
            "cache_hit": False,
            "error": str(e)
        }
