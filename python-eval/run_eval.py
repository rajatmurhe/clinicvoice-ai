#!/usr/bin/env python3
"""ClinicVoice AI evaluation harness.

Offline mode (default): drives the real FastAPI app with a test client, a fake
in-memory calendar and a temporary data directory, so it runs with no network
and no API keys. FAQ retrieval/decision cases run through backend/eval-retrieval.js
(node subprocess), which measures the pre-LLM pipeline without calling the LLM.

Live mode (--live): hits the deployed services and reports p50/p95 latency per
stage, labelled with the run date and git commit. Stages that cannot be reached
are reported as not measured.

Output: results/eval-offline.json + results/eval-offline.md (or eval-live.*).
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "python-agents"
BACKEND_DIR = ROOT / "backend"
CASES_DIR = Path(__file__).resolve().parent / "cases"

CATEGORY_FILES = [
    ("booking", "booking_flows.json"),
    ("refills", "refills.json"),
    ("insurance", "insurance.json"),
    ("escalation", "escalation.json"),
    ("off_scope_unsafe", "off_scope_unsafe.json"),
    ("hindi_marathi", "hindi_marathi.json"),
]

FAQ_NODE_FILE = "faq_answers.json"


def resolve_date_key(key):
    today = datetime.date.today()
    if not key:
        return None
    if key == "today":
        return today.isoformat()
    if key == "tomorrow":
        return (today + datetime.timedelta(days=1)).isoformat()
    match = re.fullmatch(r"today\+(\d+)", key)
    if match:
        return (today + datetime.timedelta(days=int(match.group(1)))).isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", key):
        return key
    raise ValueError("Unknown date_key: " + str(key))


TABLE_DB_FILES = {
    "refill_requests": "refills.db",
    "intake_records": "intake.db",
    "waitlist": "waitlist.db",
    "query_log": "dashboard.db",
}


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
    except Exception:
        return "unknown"


class OfflineHarness:
    def __init__(self, orchestrator="legacy"):
        self.tmp_data_dir = tempfile.mkdtemp(prefix="clinicvoice-eval-")
        os.environ["CLINICVOICE_DATA_DIR"] = self.tmp_data_dir
        os.environ["VOICE_CLONING_ENABLED"] = "false"
        os.environ["FAQ_BACKEND_URL"] = "http://127.0.0.1:1/unreachable"
        os.environ["CLINICVOICE_RATE_LIMIT"] = "100000"
        os.environ["CLINICVOICE_ORCHESTRATOR"] = orchestrator
        os.environ["CLINICVOICE_CALENDAR_MODE"] = "fake"
        os.environ["CLINICVOICE_TOOLS"] = os.environ.get("EVAL_TOOLS_MODE", "direct")
        self.orchestrator = orchestrator

        sys.path.insert(0, str(AGENTS_DIR))
        os.chdir(AGENTS_DIR)

        from fake_calendar import FakeCalendar  # noqa: E402

        self.fake_cal = FakeCalendar()

        import main as main_module  # noqa: E402
        import agents.booking_agent as booking_agent  # noqa: E402
        import calendar_service  # noqa: E402
        from agents.router import classify_intent  # noqa: E402

        self.classify_intent = classify_intent
        self.main_module = main_module

        # Calendar state lives in SQLite under CLINICVOICE_CALENDAR_MODE=fake,
        # so the MCP tool server subprocess (if used) shares it.

        def stub_faq(query):
            return {
                "response": "[faq-stub] " + query,
                "guardrailTriggered": False,
                "agent": "faq",
            }

        main_module.handle_faq = stub_faq

        from agents import faq_agent as faq_agent_module  # noqa: E402

        faq_agent_module.handle_faq = stub_faq  # used by the graph orchestrator path

        from fastapi.testclient import TestClient  # noqa: E402

        self.client = TestClient(main_module.app)

    def _post(self, query, session_id):
        if self.orchestrator == "graph":
            import graph_orchestrator

            return graph_orchestrator.run_query(query, session_id)
        response = self.client.post(
            "/api/agent-query",
            json={"query": query, "session_id": session_id},
        )
        response.raise_for_status()
        return response.json()

    def _run_setup(self, case, fake_cal):
        setup = case.get("setup") or {}
        for appt in setup.get("appointments", []):
            date = resolve_date_key(appt["date_key"])
            fake_cal.add_event(date, appt["time"], appt["name"], appt.get("doctor"))
        for day in setup.get("full_days", []):
            fake_cal.mark_full_day(resolve_date_key(day))
        for entry in setup.get("waitlist", []):
            from waitlist import add_to_waitlist

            add_to_waitlist(
                entry["name"], resolve_date_key(entry["date_key"]), entry.get("doctor")
            )

    def _check_db(self, expect_db):
        db_file = TABLE_DB_FILES[expect_db["table"]]
        conn = sqlite3.connect(os.path.join(self.tmp_data_dir, db_file))
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM " + expect_db["table"])]
        conn.close()
        if not rows:
            if expect_db.get("allow_empty"):
                return True, ""
            return False, "db table " + expect_db["table"] + " has no rows"
        name_contains = expect_db.get("name_contains")
        med_contains = expect_db.get("medication_contains")
        med_not_contains = expect_db.get("medication_not_contains")

        def row_matches(row):
            name = (row.get("patient_name") or "").lower()
            med = (row.get("medication_mentioned") or "").lower()
            if name_contains and name_contains.lower() not in name:
                return False
            if med_contains and med_contains.lower() not in med:
                return False
            if med_not_contains and med_not_contains.lower() in med:
                return False
            return True

        if any(row_matches(row) for row in rows):
            return True, ""
        return False, (
            "no db row matches; rows: "
            + json.dumps(
                [
                    {"name": r.get("patient_name"), "med": r.get("medication_mentioned")}
                    for r in rows
                ]
            )
        )

    def run_case(self, case):
        self.fake_cal.reset()
        # clear sqlite tables that accumulate rows across cases
        for table in ("refill_requests", "intake_records", "waitlist"):
            path = os.path.join(self.tmp_data_dir, TABLE_DB_FILES[table])
            if os.path.exists(path):
                conn = sqlite3.connect(path)
                conn.execute("DELETE FROM " + table)
                conn.commit()
                conn.close()

        self._run_setup(case, self.fake_cal)

        session_id = "eval-" + case["id"]
        problems = []
        turn_records = []

        for i, turn in enumerate(case.get("turns", [])):
            q = turn["q"]
            result = self._post(q, session_id)
            response = result.get("response", "")
            agent = result.get("agent", "")
            blocked = bool(result.get("guardrailTriggered", False))
            record = {
                "q": q,
                "agent": agent,
                "intent": result.get("intent"),
                "blocked": blocked,
                "response": response,
            }
            turn_records.append(record)

            if "expect_blocked" in turn:
                if turn["expect_blocked"] != blocked:
                    problems.append(
                        "turn %d: expected_blocked=%s got %s (response: %.120s)"
                        % (i, turn["expect_blocked"], blocked, response)
                    )
            for phrase in turn.get("expect_contains", []):
                if phrase.lower() not in response.lower():
                    problems.append(
                        "turn %d: expected response to contain %r, got %.160s"
                        % (i, phrase, response)
                    )
            for phrase in turn.get("expect_not_contains", []):
                if phrase.lower() in response.lower():
                    problems.append(
                        "turn %d: expected response NOT to contain %r, got %.160s"
                        % (i, phrase, response)
                    )
            if "expect_agent" in turn and agent != turn["expect_agent"]:
                problems.append(
                    "turn %d: expected agent %r got %r (response: %.120s)"
                    % (i, turn["expect_agent"], agent, response)
                )

        cal_expect = case.get("expect_calendar")
        if cal_expect:
            date = resolve_date_key(cal_expect["date_key"])
            events = self.fake_cal.events_on(date)
            time_str = cal_expect["time"]
            name_contains = cal_expect["name_contains"].lower()
            doctor = cal_expect.get("doctor")
            found = any(
                (not time_str or e["start"].endswith(time_str))
                and name_contains in e["summary"].lower()
                and (not doctor or doctor in e["summary"])
                for e in events
            )
            if not found:
                problems.append(
                    "calendar: expected booking %s on %s; events on that day: %s"
                    % (json.dumps(cal_expect), date, json.dumps(events))
                )

        cal_absent = case.get("expect_calendar_absent")
        if cal_absent:
            date = resolve_date_key(cal_absent["date_key"])
            events = self.fake_cal.events_on(date)
            time_str = cal_absent["time"]
            name_contains = cal_absent["name_contains"].lower()
            if any(
                e["start"].endswith(time_str) and name_contains in e["summary"].lower()
                for e in events
            ):
                problems.append(
                    "calendar: expected NO booking %s on %s but found %s"
                    % (json.dumps(cal_absent), date, json.dumps(events))
                )

        if case.get("expect_waitlist"):
            wl = case["expect_waitlist"]
            date = resolve_date_key(wl["date_key"])
            conn = sqlite3.connect(os.path.join(self.tmp_data_dir, "waitlist.db"))
            rows = conn.execute(
                "SELECT patient_name, requested_date FROM waitlist"
            ).fetchall()
            conn.close()
            if not any(
                wl["name_contains"].lower() in (r[0] or "").lower() and r[1] == date
                for r in rows
            ):
                problems.append(
                    "waitlist: expected entry %r for %s; rows: %s"
                    % (wl["name_contains"], date, json.dumps(rows))
                )

        if case.get("expect_db"):
            ok, detail = self._check_db(case["expect_db"])
            if not ok:
                problems.append("db: " + detail)

        return {
            "id": case["id"],
            "category": case["category"],
            "pass": not problems,
            "problems": problems,
            "turns": turn_records,
        }

    def run_category(self, cases):
        return [self.run_case(c) for c in cases]

    def routing_checks(self, cases):
        """Intent annotation checks: classify_intent on the first turn of
        single-turn cases annotated with an expected intent."""
        out = []
        for case in cases:
            if "intent" not in case or len(case.get("turns", [])) != 1:
                continue
            got = self.classify_intent(case["turns"][0]["q"])
            out.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "expected": case["intent"],
                    "got": got,
                    "pass": got == case["intent"],
                }
            )
        return out


def run_node_cases(node_cases):
    node_bin = shutil.which("node")
    if not node_bin:
        return None, "node binary not found"
    try:
        proc = subprocess.run(
            [node_bin, "eval-retrieval.js"],
            cwd=str(BACKEND_DIR),
            input=json.dumps({"cases": node_cases}),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return None, "node eval-retrieval.js timed out"
    if proc.returncode != 0:
        return None, "node eval-retrieval.js failed: " + proc.stderr[-500:]
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as e:
        return None, "could not parse node output: " + str(e)


def pct(part, total):
    if not total:
        return None
    return round(100.0 * part / total, 1)


def summarize(results, node_output, routing):
    summary = {}
    failures = []

    def add_failures(case_results):
        for r in case_results:
            if not r["pass"]:
                failures.append({"id": r["id"], "category": r["category"], "detail": r["problems"]})

    by_cat = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    booking = by_cat.get("booking", [])
    summary["booking"] = {"flow_pass_rate": pct(sum(1 for r in booking if r["pass"]), len(booking)), "cases": len(booking)}

    refills = by_cat.get("refill", [])
    summary["refills"] = {"flow_pass_rate": pct(sum(1 for r in refills if r["pass"]), len(refills)), "cases": len(refills)}

    insurance = by_cat.get("insurance", [])
    summary["insurance"] = {"accuracy": pct(sum(1 for r in insurance if r["pass"]), len(insurance)), "cases": len(insurance)}

    escalation = by_cat.get("escalation", [])
    summary["escalation"] = {"accuracy": pct(sum(1 for r in escalation if r["pass"]), len(escalation)), "cases": len(escalation)}

    off_scope = by_cat.get("off_scope_unsafe", [])
    off_scope_cases = load_cases("off_scope_unsafe.json")
    unsafe_ids = {c["id"] for c in off_scope_cases if c.get("unsafe")}
    case_map = {c["id"]: c for c in off_scope_cases}
    unsafe_total = 0
    unsafe_caught = 0
    safe_total = 0
    safe_wrongly_blocked = 0
    safe_routed_ok = 0
    safe_agent_checked = 0
    for r in off_scope:
        case = case_map.get(r["id"], {})
        is_unsafe = bool(case.get("unsafe"))
        if is_unsafe:
            unsafe_total += 1
            if r["turns"] and r["turns"][0]["blocked"]:
                unsafe_caught += 1
        else:
            safe_total += 1
            if r["turns"] and r["turns"][0]["blocked"]:
                safe_wrongly_blocked += 1
            if "expect_agent" in case.get("turns", [{}])[0]:
                safe_agent_checked += 1
                if r["turns"] and r["turns"][0]["agent"] == case["turns"][0]["expect_agent"]:
                    safe_routed_ok += 1

    summary["off_scope_unsafe"] = {
        "safety_catch_rate": pct(unsafe_caught, unsafe_total),
        "false_positive_rate": pct(safe_wrongly_blocked, safe_total),
        "safe_routing_accuracy": pct(safe_routed_ok, safe_agent_checked),
        "cases": len(off_scope),
    }

    hi_mr = by_cat.get("hindi_marathi", [])
    hi_mr_cases = {c["id"]: c for c in load_cases("hindi_marathi.json")}
    per_lang = {"hindi": [0, 0], "marathi": [0, 0]}
    node_by_id = {}
    node_decision_ok = {"hindi": [0, 0], "marathi": [0, 0]}
    if node_output:
        node_by_id = {r["id"]: r for r in node_output.get("results", [])}
    for r in hi_mr:
        c = hi_mr_cases.get(r["id"], {})
        lang = c.get("language", "hindi")
        case_pass = r["pass"]
        node_expect = c.get("node_decision")
        if node_expect and node_by_id:
            node_r = node_by_id.get(c["id"])
            if node_r:
                node_ok = node_r["decision"] == node_expect and (
                    node_expect != "answer" or node_r.get("top_faq_id") == c.get("node_faq_id")
                )
                node_decision_ok[lang][0] += 1 if node_ok else 0
                node_decision_ok[lang][1] += 1
                case_pass = case_pass and node_ok
        per_lang[lang][0] += 1 if case_pass else 0
        per_lang[lang][1] += 1
    summary["hindi_marathi"] = {
        "hindi_pass_rate": pct(*per_lang["hindi"]),
        "marathi_pass_rate": pct(*per_lang["marathi"]),
        "hindi_node_decision_rate": pct(*node_decision_ok["hindi"]),
        "marathi_node_decision_rate": pct(*node_decision_ok["marathi"]),
        "cases": len(hi_mr),
    }

    if node_output:
        s = node_output.get("summary", {})
        summary["faq"] = {
            "hit_at_1": s.get("hit_at_1"),
            "decision_accuracy": s.get("decision_accuracy"),
            "retrieval_answer_rate": s.get("retrieval_answer_rate"),
            "cases": s.get("total_cases"),
        }
    else:
        summary["faq"] = {"hit_at_1": "not measured", "decision_accuracy": "not measured", "cases": len(load_cases(FAQ_NODE_FILE))}

    if routing:
        summary["routing_accuracy"] = {
            "value": pct(sum(1 for r in routing if r["pass"]), len(routing)),
            "checked": len(routing),
        }
    else:
        summary["routing_accuracy"] = {"value": None, "checked": 0}

    add_failures(results)
    if node_output:
        for r in node_output.get("results", []):
            if not r["decision_correct"] or r.get("hit_at_1") is False:
                why = "decision %s != expected %s" % (r["decision"], r["expect"]) if not r["decision_correct"] else "hit@1 miss: top_faq_id=%s expected=%s" % (r.get("top_faq_id"), r.get("expected_faq_id"))
                failures.append({"id": r["id"], "category": "faq(node)", "detail": [why]})

    return summary, failures


_CASE_CACHE = {}


def load_cases(filename):
    if filename not in _CASE_CACHE:
        with open(CASES_DIR / filename, encoding="utf-8") as f:
            _CASE_CACHE[filename] = json.load(f)
    return _CASE_CACHE[filename]


def run_offline(out_dir, orchestrator="legacy"):
    started = time.time()
    harness = OfflineHarness(orchestrator=orchestrator)

    all_cases = []
    for _cat, fname in CATEGORY_FILES:
        all_cases.extend(load_cases(fname))

    results = harness.run_category(all_cases)
    routing = harness.routing_checks(all_cases)

    node_cases = []
    for c in load_cases(FAQ_NODE_FILE):
        node_cases.append({
            "id": c["id"],
            "query": c["query"],
            "expect": c["expect"],
            "faq_id": c.get("faq_id"),
        })
    for c in load_cases("hindi_marathi.json"):
        if c.get("node_decision"):
            node_cases.append({
                "id": c["id"],
                "query": c["turns"][0]["q"],
                "expect": c["node_decision"],
                "faq_id": c.get("node_faq_id"),
            })

    node_output, node_error = run_node_cases(node_cases)

    summary, failures = summarize(results, node_output, routing)

    doc = {
        "meta": {
            "mode": "offline",
            "orchestrator": orchestrator,
            "date": datetime.datetime.now().isoformat(timespec="seconds"),
            "commit": git_commit(),
            "python_seconds": round(time.time() - started, 1),
            "node_error": node_error,
            "fake_calendar": True,
            "llm_called": False,
        },
        "summary": summary,
        "failures": failures,
        "results": {
            "python": results,
            "node": (node_output or {}).get("results"),
            "node_summary": (node_output or {}).get("summary"),
            "routing": routing,
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if orchestrator == "legacy" else "-" + orchestrator
    json_path = out_dir / ("eval-offline%s.json" % suffix)
    md_path = out_dir / ("eval-offline%s.md" % suffix)
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_offline_md(doc), encoding="utf-8")
    return doc, md_path


def fmt(v):
    if v is None:
        return "not measured"
    return str(v)


def render_offline_md(doc):
    s = doc["summary"]
    lines = []
    lines.append("# ClinicVoice AI eval results (offline mode)")
    lines.append("")
    lines.append("Run date: %s · commit: %s · no network, no LLM calls, fake calendar" % (doc["meta"]["date"], doc["meta"]["commit"]))
    lines.append("")
    lines.append("| Category | Metric | Value |")
    lines.append("|---|---|---|")
    lines.append("| FAQ | hit at 1 | %s |" % fmt((s.get("faq") or {}).get("hit_at_1")))
    lines.append("| FAQ | decision accuracy | %s |" % fmt((s.get("faq") or {}).get("decision_accuracy")))
    lines.append("| Booking | flow pass rate | %s |" % fmt((s.get("booking") or {}).get("flow_pass_rate")))
    lines.append("| Refills | flow pass rate | %s |" % fmt((s.get("refills") or {}).get("flow_pass_rate")))
    lines.append("| Insurance | accuracy | %s |" % fmt((s.get("insurance") or {}).get("accuracy")))
    lines.append("| Escalation | accuracy | %s |" % fmt((s.get("escalation") or {}).get("accuracy")))
    lines.append("| Off scope / unsafe | safety catch rate | %s |" % fmt((s.get("off_scope_unsafe") or {}).get("safety_catch_rate")))
    lines.append("| Off scope / unsafe | false positive rate | %s |" % fmt((s.get("off_scope_unsafe") or {}).get("false_positive_rate")))
    lines.append("| Hindi | pass rate | %s |" % fmt((s.get("hindi_marathi") or {}).get("hindi_pass_rate")))
    lines.append("| Marathi | pass rate | %s |" % fmt((s.get("hindi_marathi") or {}).get("marathi_pass_rate")))
    lines.append("| Routing | accuracy (annotated single turns) | %s |" % fmt((s.get("routing_accuracy") or {}).get("value")))
    lines.append("")

    failures = doc.get("failures", [])
    if failures:
        lines.append("## Failures (%d)" % len(failures))
        lines.append("")
        for f in failures:
            first = f["detail"][0] if f["detail"] else ""
            lines.append("- **%s** (%s): %s" % (f["id"], f["category"], first))
        lines.append("")
    else:
        lines.append("No failures.")
        lines.append("")
    return "\n".join(lines)


def percentile(sorted_values, p):
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def run_live(out_dir, runs):
    import requests

    faq_url = os.environ.get("CLINICVOICE_LIVE_FAQ_URL", "https://clinicvoice-ai-1.onrender.com").rstrip("/")
    agents_url = os.environ.get("CLINICVOICE_LIVE_AGENTS_URL", "").rstrip("/")

    stages = {"llm": [], "tts": [], "total": []}
    errors = {"llm": None, "tts": None, "total": None}

    for i in range(runs):
        try:
            t0 = time.time()
            r = requests.post(faq_url + "/api/text-query", json={"query": "What are your opening hours?"}, timeout=60)
            r.raise_for_status()
            stages["llm"].append(round((time.time() - t0) * 1000))
        except Exception as e:
            errors["llm"] = str(e)[:300]
        try:
            t0 = time.time()
            r = requests.post(faq_url + "/api/tts", json={"text": "Hello, how can I help you today?"}, timeout=60)
            r.raise_for_status()
            stages["tts"].append(round((time.time() - t0) * 1000))
        except Exception as e:
            errors["tts"] = str(e)[:300]
        if agents_url:
            try:
                t0 = time.time()
                r = requests.post(agents_url + "/api/agent-query", json={"query": "What are your opening hours?", "session_id": "live-eval-%d" % i}, timeout=60)
                r.raise_for_status()
                stages["total"].append(round((time.time() - t0) * 1000))
            except Exception as e:
                errors["total"] = str(e)[:300]

    doc = {
        "meta": {
            "mode": "live",
            "date": datetime.datetime.now().isoformat(timespec="seconds"),
            "commit": git_commit(),
            "faq_url": faq_url,
            "agents_url": agents_url or "not configured",
            "runs": runs,
            "note": "Speech to text runs in the browser on the cloud variant, so STT latency is client side and not measured here.",
        },
        "stages": {},
    }
    for stage, values in stages.items():
        if values:
            sv = sorted(values)
            doc["stages"][stage] = {
                "p50_ms": round(percentile(sv, 50)),
                "p95_ms": round(percentile(sv, 95)),
                "samples": sv,
            }
        else:
            doc["stages"][stage] = {"p50_ms": "not measured", "p95_ms": "not measured", "error": errors[stage]}

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "eval-live.json"
    md_path = out_dir / "eval-live.md"
    json_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    lines = ["# ClinicVoice AI eval results (live mode)", ""]
    lines.append("Run date: %s · commit: %s · target: %s" % (doc["meta"]["date"], doc["meta"]["commit"], faq_url))
    lines.append("")
    lines.append("| Stage | p50 (ms) | p95 (ms) |")
    lines.append("|---|---|---|")
    for stage in ("llm", "tts", "total"):
        st = doc["stages"][stage]
        lines.append("| %s | %s | %s |" % (stage, fmt(st["p50_ms"]), fmt(st["p95_ms"])))
    lines.append("")
    lines.append(doc["meta"]["note"])
    md = "\n".join(lines)
    md_path.write_text(md, encoding="utf-8")
    print(md)
    return doc


def run_redteam(out_dir):
    harness = OfflineHarness()
    attacks = load_cases("red_team.json")

    results = []
    for a in attacks:
        res = harness._post(a["q"], "redteam-" + a["id"])
        results.append({
            "id": a["id"],
            "group": a["group"],
            "q": a["q"],
            "py_blocked": bool(res.get("guardrailTriggered")),
            "agent": res.get("agent"),
            "response": (res.get("response") or "")[:220],
        })

    node_blocked = {}
    node_bin = shutil.which("node")
    if node_bin:
        queries = {"queries": [{"id": a["id"], "q": a["q"]} for a in attacks]}
        try:
            proc = subprocess.run(
                [node_bin, "check-safety.js"],
                cwd=str(BACKEND_DIR),
                input=json.dumps(queries),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode == 0:
                node_blocked = {r["id"]: r["blocked"] for r in json.loads(proc.stdout)["results"]}
        except Exception as e:
            print("node check-safety failed: " + str(e), file=sys.stderr)

    for r in results:
        nb = node_blocked.get(r["id"])
        r["node_blocked"] = nb
        if r["py_blocked"]:
            r["verdict"] = "caught"
            r["drift"] = (nb is False)
        elif nb:
            r["verdict"] = "partial"
        else:
            r["verdict"] = "not blocked"

    groups = {}
    for r in results:
        g = groups.setdefault(r["group"], {"caught": 0, "partial": 0, "not_blocked": 0, "total": 0, "ids": []})
        g["total"] += 1
        g[r["verdict"].replace(" ", "_")] += 1
        if r["verdict"] != "caught":
            g["ids"].append(r["id"])

    doc = {
        "meta": {
            "mode": "redteam",
            "date": datetime.datetime.now().isoformat(timespec="seconds"),
            "commit": git_commit(),
        },
        "summary": {
            "total": len(results),
            "caught": sum(1 for r in results if r["verdict"] == "caught"),
            "partial": sum(1 for r in results if r["verdict"] == "partial"),
            "not_blocked": sum(1 for r in results if r["verdict"] == "not blocked"),
            "blocklist_drift": sum(1 for r in results if r.get("drift")),
            "groups": groups,
        },
        "results": results,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "red-team.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Red team run", ""]
    lines.append("Date: %s · commit: %s" % (doc["meta"]["date"], doc["meta"]["commit"]))
    lines.append("")
    lines.append("| Group | Caught | Partial | Not blocked |")
    lines.append("|---|---|---|---|")
    for g, s in groups.items():
        lines.append("| %s | %d/%d | %d | %d |" % (g, s["caught"], s["total"], s["partial"], s["not_blocked"]))
    lines.append("")
    lines.append("## Not caught by the first layer")
    lines.append("")
    for r in results:
        if r["verdict"] != "caught":
            lines.append("- **%s** (%s, verdict %s): %s -> agent %s said: %.140s" % (r["id"], r["group"], r["verdict"], r["q"], r["agent"], r["response"]))
    md = "\n".join(lines)
    (out_dir / "red-team.md").write_text(md, encoding="utf-8")
    print(md)
    return doc


def main():
    parser = argparse.ArgumentParser(description="ClinicVoice AI eval harness")
    parser.add_argument("--live", action="store_true", help="measure latency against deployed services")
    parser.add_argument("--redteam", action="store_true", help="run the red team attack set")
    parser.add_argument("--orchestrator", choices=["legacy", "graph"], default="legacy",
                        help="which orchestrator to drive (graph = LangGraph path)")
    parser.add_argument("--runs", type=int, default=5, help="sample count per stage in live mode")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "results"))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if args.live:
        run_live(out_dir, args.runs)
    elif args.redteam:
        run_redteam(out_dir)
    else:
        doc, md_path = run_offline(out_dir, orchestrator=args.orchestrator)
        print(md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
