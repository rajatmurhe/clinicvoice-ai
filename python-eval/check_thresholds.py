#!/usr/bin/env python3
"""Fails (exit 1) if the offline eval regressed below the committed thresholds.

Usage: check_thresholds.py [path/to/eval-offline.json]
"""

import json
import sys
from pathlib import Path

DEFAULT_RESULTS = Path(__file__).resolve().parent / "results" / "eval-offline.json"
THRESHOLDS = Path(__file__).resolve().parent / "thresholds.json"


def main():
    results_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RESULTS
    if not results_path.exists():
        print("No eval results found at " + str(results_path))
        return 1

    with open(results_path, encoding="utf-8") as f:
        results = json.load(f)
    with open(THRESHOLDS, encoding="utf-8") as f:
        thresholds = json.load(f)

    s = results["summary"]

    def metric(name):
        if name == "faq_hit_at_1":
            return (s.get("faq") or {}).get("hit_at_1")
        if name == "faq_decision_accuracy":
            return (s.get("faq") or {}).get("decision_accuracy")
        if name == "booking_flow_pass_rate":
            return (s.get("booking") or {}).get("flow_pass_rate")
        if name == "refill_flow_pass_rate":
            return (s.get("refills") or {}).get("flow_pass_rate")
        if name == "insurance_accuracy":
            return (s.get("insurance") or {}).get("accuracy")
        if name == "escalation_accuracy":
            return (s.get("escalation") or {}).get("accuracy")
        if name == "safety_catch_rate":
            return (s.get("off_scope_unsafe") or {}).get("safety_catch_rate")
        if name == "false_positive_rate_max":
            return (s.get("off_scope_unsafe") or {}).get("false_positive_rate")
        if name == "routing_accuracy":
            return (s.get("routing_accuracy") or {}).get("value")
        raise KeyError(name)

    failures = []
    for name, floor in thresholds.items():
        if name == "comment":
            continue
        value = metric(name)
        if value in (None, "not measured"):
            failures.append("%s: not measured (floor %s)" % (name, floor))
        elif name == "false_positive_rate_max":
            if value > floor:
                failures.append("%s: %.1f is above ceiling %.1f" % (name, value, floor))
        elif value < floor:
            failures.append("%s: %.1f is below floor %.1f" % (name, value, floor))

    if failures:
        print("Eval thresholds FAILED:")
        for line in failures:
            print("  " + line)
        return 1

    print("Eval thresholds passed (results: %s)" % results_path.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
