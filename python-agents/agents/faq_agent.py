import time
import os

import requests

from semantic_cache import check_cache, store_in_cache
import obs

FAQ_BACKEND_URL = os.environ.get("FAQ_BACKEND_URL", "http://localhost:5050/api/text-query")

FAQ_UNREACHABLE_RESPONSE = (
    "I'm having trouble accessing that information right now. "
    "Please call our reception team and they'll be happy to help."
)

RETRYABLE_STATUS = (500, 502, 503, 504)


def _post_with_retries(query):
    """Calls the FAQ backend with short timeouts and two retries with backoff.

    Raises the last exception only after all attempts fail, so the caller can
    degrade gracefully instead of hanging.
    """
    headers = {"X-Request-ID": obs.get_request_id()}
    last_error = None
    for attempt in range(3):
        try:
            response = requests.post(
                FAQ_BACKEND_URL,
                json={"query": query},
                headers=headers,
                timeout=(3, 10),
            )
            if response.status_code in RETRYABLE_STATUS and attempt < 2:
                time.sleep(0.3 * (2 ** attempt))
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            last_error = e
            if attempt < 2:
                time.sleep(0.3 * (2 ** attempt))
    raise last_error


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
        data = _post_with_retries(query)
    except Exception as e:
        obs.log_event("faq_backend_failed", error_type=type(e).__name__)
        return {
            "response": FAQ_UNREACHABLE_RESPONSE,
            "guardrailTriggered": False,
            "agent": "faq",
            "cache_hit": False,
            "error_type": "faq_backend_unreachable",
            "latency_ms": round((time.time() - start) * 1000, 1)
        }

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
        "usage_tokens": data.get("usage_tokens"),
        "latency_ms": elapsed_ms
    }
