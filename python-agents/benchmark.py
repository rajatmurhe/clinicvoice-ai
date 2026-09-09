import requests
import time
import statistics

API_URL = "http://localhost:8000/api/agent-query"

TEST_PAIRS = [
    ("Is there parking?", "Do you have parking?"),
    ("Do you offer vaccinations?", "Do you offer vaccinations?"),
    ("How do I pay my bill?", "How do I pay my bill?"),
]


def query(text, session_id):
    start = time.time()
    response = requests.post(API_URL, json={"query": text, "session_id": session_id})
    elapsed = (time.time() - start) * 1000
    data = response.json()
    return elapsed, data.get("cache_hit", False)


def run_benchmark():
    cold_latencies = []
    warm_latencies = []

    print("Running latency benchmark...\n")

    for i, (original, followup) in enumerate(TEST_PAIRS):
        session_id = f"bench-{i}"

        cold_ms, cold_hit = query(original, session_id)
        cold_latencies.append(cold_ms)
        print(f"COLD: \"{original}\" -> {cold_ms:.0f}ms (cache_hit={cold_hit})")

        warm_ms, warm_hit = query(followup, session_id)
        warm_latencies.append(warm_ms)
        print(f"WARM: \"{followup}\" -> {warm_ms:.0f}ms (cache_hit={warm_hit})")
        print()

    print("=" * 50)
    print("RESULTS")
    print("=" * 50)
    print(f"Cold (uncached) average: {statistics.mean(cold_latencies):.0f}ms")
    print(f"Warm (post-query) average: {statistics.mean(warm_latencies):.0f}ms")

if __name__ == "__main__":
    run_benchmark()
