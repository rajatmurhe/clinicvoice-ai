# ClinicVoice AI

[![CI](https://github.com/rajatmurhe/clinicvoice-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/rajatmurhe/clinicvoice-ai/actions/workflows/ci.yml)

A voice assistant for a medical clinic reception. It answers clinic questions,
books, looks up, reschedules and cancels real appointments, logs prescription
refills and takes non-diagnostic intake notes, speaks its answers back, and
refuses everything a receptionist must refuse: medical advice, prompt
injections and requests for other patients' data.

The design goal is safety first. A four layer guardrail system sits between the
patient and the language model, an offline eval harness measures every change
against a fixed 180 case test set, and a red team set of 46 attacks proves the
guardrails hold. Every number in this README comes from a run you can reproduce
with one command (see Running the eval below).

**Live demo:** https://clinicvoice-ai.onrender.com (FAQ service) · agent
service at https://clinicvoice-ai-agents.onrender.com. Free tier cold starts
mean the first request can take 20 to 60 seconds; later requests are fast.

## Architecture

```
Browser (voice in/out, Web Speech API or push to talk fallback)
   |
   |  one request id flows through every hop and every log line
   v
Python orchestrator (FastAPI)  /api/agent-query
   |-- guardrails: emergency detector, input blocklist (Python + Node mirrors)
   |-- router: regex fast path + Hindi/Marathi keywords (+ optional LLM classifier)
   |-- agents: booking, refill, insurance, intake, escalation, faq
   |-- tools: calendar, logs, FAQ search (direct or MCP)
   |-- SQLite: sessions, query log, tool call log, fake calendar
   v
Node FAQ service (Express)  /api/text-query
   |-- retrieval: hybrid BM25 + character trigrams over the FAQ index
   |-- pre-LLM decisions: blocklist, greeting, confidence threshold
   |-- Groq LLM (gpt-oss-20b) for answers; output filter on the reply
```

Alternative orchestrators and transports are compared on the same eval and
selected behind flags: a LangGraph state graph (`CLINICVOICE_ORCHESTRATOR=graph`),
MCP tool transport (`CLINICVOICE_TOOLS=mcp`), an LLM intent classifier
(`CLINICVOICE_HYBRID_ROUTER`), and a compliance reviewer
(`CLINICVOICE_COMPLIANCE_REVIEWER`). See DECISIONS.md for the measurements
behind each default.

Multi tenant: clinic specific data lives in `python-agents/clinics/*.json`
(hours, doctors, insurance providers, FAQs, languages, scheduling adapter,
webhooks). A second clinic onboards with a config file only; the scheduling
adapter interface has Google Calendar, SQLite fake and a live FHIR sandbox
implementation.

## Results

Offline eval, fixed committed test set, no network, no LLM calls, fake
calendar. Run date and commit are stored in each results file.

| Category | Metric | Baseline (Phase 1) | Now |
|---|---|---|---|
| FAQ retrieval (30 answer cases + 12 others) | hit at 1 | 60.6 | 91.2 |
| FAQ decisions (answer / fallback / block) | decision accuracy | 68.8 | 98.1 |
| Booking (25 multi turn flows) | flow pass rate | 56.0 | 100.0 |
| Refills (12 flows) | flow pass rate | 83.3 | 100.0 |
| Insurance (12 cases) | accuracy | 83.3 | 100.0 |
| Escalation (12 cases) | accuracy | 83.3 | 100.0 |
| Unsafe inputs (20) | safety catch rate | 75.0 | 100.0 |
| Safe inputs (10) | false positive rate | 0.0 | 0.0 |
| Hindi (12 cases) | pass rate | 0.0 | 100.0 |
| Marathi (9 cases) | pass rate | 0.0 | 100.0 |
| Routing (annotated single turns) | accuracy | 75.9 | 100.0 |
| Red team (46 attacks, 5 groups) | caught | 9/40 | 40/46 |

Live latency against the deployed services (p50; free tier cold starts can
push p95 above 19s on the first request after idling):

| Stage | p50 (ms) |
|---|---|
| LLM answer (retrieval + Groq) | 1017 |
| TTS full reply | 3276 |
| Total agent turn | 1525 |
| Time to first audio, before sentence streaming | 3401 |
| Time to first audio, after sentence streaming | 2057 |

The eval baseline found real bugs that are now fixed and guarded by regression
tests: a reply to "could you tell me the name?" in the cancel flow was dropped
unless it repeated a keyword; "refill please" logged the word please as the
medication; "prescription" questions were blocked by the input filter and could
never reach the refill flow; "do you accept walk-ins" was routed to the
insurance agent; the word for disease (बीमारी) triggered the insurance keyword
बीमा.

## Red team findings

40 initial attacks in four groups (prompt injection, medical advice, identity
bypass, other patient data) plus a Hindi and Marathi group added later, 46 in
total. After the fixes, 40 of 46 are caught by the first safety layer, the
blocklists of the Python and Node layers stay in sync (drift 0, enforced by a
parity test), and an emergency detector routes chest-pain class messages to a
dedicated contact-local-emergency-services reply in the caller's language.
The six attacks that are not blocked all exploit one accepted product decision:
appointments are found by patient name only. That is documented as a known
limitation below, not hidden. Full tables and the before/after story are in
[RED_TEAM.md](RED_TEAM.md).

## Key design decisions

Short version, full records with numbers in [DECISIONS.md](DECISIONS.md):

1. Only the FAQ agent uses an LLM; flows are deterministic so they are
   testable and cannot hallucinate a booking.
2. Regex routing first (100 percent on the eval at zero latency); the LLM
   classifier stays behind a flag for live phrasings the fixed set cannot
   cover.
3. Four safety layers: input blocklist, greeting short circuit, retrieval
   confidence threshold, output filter; both services mirror the same
   blocklists, enforced by a CI parity test.
4. Hybrid retrieval (BM25 + character trigrams + disagreement penalty) raised
   FAQ hit at 1 from 60.6 to 91.2 and made Hindi and Marathi retrieval work at
   all; the old tokenizer stripped Devanagari entirely.
5. The LangGraph orchestrator scored identically on the eval but costs about
   50ms per query and a heavy dependency, so the hand written path stays
   default; both are kept and tested.
6. Tools behind MCP scored identically with about a second per call of
   transport overhead, so direct calls stay default; the MCP path is proven
   equivalent on the same eval.
7. Session state, logs, the fake calendar and graph checkpoints are all
   SQLite, so a restart never erases a booking in progress (verified).

## Run it

Fresh clone, no accounts needed (the demo calendar is SQLite; the LLM answers
degrade gracefully without a Groq key):

```bash
cp .env.example .env          # optional: add GROQ_API_KEY for real FAQ answers
docker compose up --build
```

Then:

- Agent service and admin dashboard: http://localhost:8000 (dashboard at
  http://localhost:8000/dashboard: recent requests with request ids, p50/p95
  latency, guardrail counts, failures, tool call stats, token cost estimate)
- FAQ service health: http://localhost:5050/api/health
- Ask a question:

```bash
curl -s http://localhost:8000/api/agent-query \
  -H 'Content-Type: application/json' \
  -d '{"query": "I want to book an appointment tomorrow", "session_id": "demo"}'
```

Two clinics ship side by side: send `"clinic_id": "smilecare"` in the body to
talk to the second clinic (different hours, doctors, insurance list, FAQs and
its own calendar state).

Without Docker: see `.env.example` and run `uvicorn main:app` in
`python-agents/` (Python 3.11, `pip install -r requirements.txt`) plus
`node server-cloud.js` in `backend/`.

### Running the eval

```bash
# Offline harness (no network, no LLM, ~5 seconds)
python-agents/venv/bin/python python-eval/run_eval.py

# Red team (46 attacks)
python-agents/venv/bin/python python-eval/run_eval.py --redteam

# Both orchestrators on the same cases
python-agents/venv/bin/python python-eval/run_eval.py --orchestrator legacy|graph

# Same flows with tools behind MCP
EVAL_TOOLS_MODE=mcp python-agents/venv/bin/python python-eval/run_eval.py

# Unit and regression tests (165 tests, plus 17 Node tests via `cd backend && npx jest`)
python-agents/venv/bin/python -m pytest python-agents/tests

# Live latency against the deployed services (needs network)
python-agents/venv/bin/python python-eval/run_eval.py --live
```

`check_thresholds.py` compares every metric against the ratcheted floors in
`python-eval/thresholds.json` and fails CI on any regression; CI also runs
pytest, the offline eval and the Node jest suite on every push.

## Repo map

| Path | What it is |
|---|---|
| `python-agents/` | The main path: FastAPI orchestrator, agents, safety, adapters, tools, clinics, tests |
| `backend/` | Node FAQ service: retrieval, guardrails, LLM call, TTS and transcription endpoints, tests |
| `cloud-frontend/` | Voice web client: sentence streamed TTS, barge in, push to talk fallback |
| `python-eval/` | Eval harness, fixed test sets, red team set, thresholds |
| `docs/` | Latency budget |

## Known limitations

Honest list; each is a decision or a measured gap, not an accident:

- Appointments are found and cancelled by patient name only. Anyone who knows
  a name can ask about it (the six red team attacks that pass). A real
  deployment needs phone or ID verification before lookup, cancel or
  reschedule. This is the highest priority item.
- Free tier cold starts: the first request after idling can take 20 to 60
  seconds; p95 latency in the live table reflects that.
- Three FAQ paraphrases still miss retrieval ("what kind of clinic is this"
  pulls a different FAQ that shares the word clinic); hit at 1 is 91.2, not
  100.
- The MCP path uses a one-shot stdio session per tool call (about a second per
  call); a persistent streamable HTTP session is the production shape.
- The guardrail reply for Devanagari input defaults to Hindi, with Marathi
  selected by hint phrases; detection is heuristic.
- Refill conversations break if the patient says the word "medicine" instead
  of the drug name, because the input blocklist blocks it (saying "metformin"
  works). The agent asks for the drug name explicitly.
- Languages: English, Hindi and Marathi are covered; other languages fall
  back to English retrieval with the translated-FAQ mechanism available.
- Homoglyph evasion: look-alike characters from other scripts (Cyrillic
  letters, for example) still slip past the blocklist. Needs script
  normalization; noted as future hardening.
- No request size limit at the application layer yet; a reverse proxy or
  gateway should enforce one in a real deployment.
- HIPAA: not certified, no BAA, no audit-grade logging. See COMPLIANCE.md.

## Compliance and edge cases

[COMPLIANCE.md](COMPLIANCE.md) documents what data the system collects, where
it goes and what a production deployment would still need.
[EDGE_CASES.md](EDGE_CASES.md) logs real bugs found during development and how
each was fixed. [RED_TEAM.md](RED_TEAM.md) documents the attack sets and the
before/after fix story. [docs/latency-budget.md](docs/latency-budget.md) holds
the per stage voice latency budgets and the streaming design.

## Tech stack

Python, FastAPI, LangGraph (flag), Node.js, Express, React, SQLite, hybrid
BM25 + trigram retrieval, Groq (gpt-oss-20b, whisper, TTS), MCP, Google
Calendar API, FHIR R4 sandbox adapter, Docker Compose, GitHub Actions.
