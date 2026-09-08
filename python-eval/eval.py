import requests
import json
import time

BASE_URL = "http://localhost:5050"

TEST_CASES = [
    {
        "name": "Normal FAQ - hours",
        "endpoint": "/graphql",
        "query": "{ faqs { question answer } }",
        "check": lambda r: "9am" in json.dumps(r)
    },
    {
        "name": "Normal FAQ - single lookup",
        "endpoint": "/graphql",
        "query": "{ faq(id: 4) { question answer } }",
        "check": lambda r: "referral" in json.dumps(r).lower()
    },
]

def run_graphql_query(query):
    response = requests.post(
        BASE_URL + "/graphql",
        json={"query": query},
        headers={"Content-Type": "application/json"}
    )
    response.raise_for_status()
    return response.json()

def run_eval():
    print("Running Python eval suite against Node/Express + GraphQL backend...\n")

    passed = 0
    failed = 0

    for test in TEST_CASES:
        start = time.time()
        result = run_graphql_query(test["query"])
        elapsed_ms = int((time.time() - start) * 1000)

        success = test["check"](result)

        status = "PASS" if success else "FAIL"
        if success:
            passed += 1
        else:
            failed += 1

        print(f"{status}: {test['name']} ({elapsed_ms}ms)")
        print(f"  Result: {json.dumps(result)}")
        print()

    print(f"Results: {passed}/{len(TEST_CASES)} passed")

if __name__ == "__main__":
    run_eval()
