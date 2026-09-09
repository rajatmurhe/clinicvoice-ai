import requests
import math
import time

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "all-minilm"
SIMILARITY_THRESHOLD = 0.80
MAX_CACHE_SIZE = 200

_cache = []


def get_embedding(text: str):
    response = requests.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=10
    )
    response.raise_for_status()
    return response.json()["embedding"]


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0
    return dot / (norm_a * norm_b)


def check_cache(query: str):
    try:
        query_embedding = get_embedding(query)
    except Exception:
        return None

    best_match = None
    best_score = 0

    for entry in _cache:
        score = cosine_similarity(query_embedding, entry["embedding"])
        if score > best_score:
            best_score = score
            best_match = entry

    if best_match and best_score >= SIMILARITY_THRESHOLD:
        return {
            "response": best_match["response"],
            "guardrailTriggered": best_match["guardrailTriggered"],
            "matched_query": best_match["query"],
            "similarity": round(best_score, 4)
        }

    return None


def store_in_cache(query: str, response: str, guardrail_triggered: bool):
    try:
        embedding = get_embedding(query)
    except Exception:
        return

    _cache.append({
        "query": query,
        "embedding": embedding,
        "response": response,
        "guardrailTriggered": guardrail_triggered,
        "timestamp": time.time()
    })

    if len(_cache) > MAX_CACHE_SIZE:
        _cache.pop(0)


def cache_stats():
    return {
        "size": len(_cache),
        "max_size": MAX_CACHE_SIZE,
        "threshold": SIMILARITY_THRESHOLD
    }
