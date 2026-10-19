# ClinicVoice AI: Multilingual Voice Assistant for Clinic Reception

[![Live Demo](https://img.shields.io/badge/Live%20Demo-ClinicVoice-00C853?style=for-the-badge&logo=render&logoColor=white)](https://clinicvoice-ai.onrender.com)
[![React](https://img.shields.io/badge/React-Vite-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![Python](https://img.shields.io/badge/Python-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Node.js](https://img.shields.io/badge/Node.js-Express-339933?style=for-the-badge&logo=nodedotjs&logoColor=white)](https://nodejs.org/)
[![Groq](https://img.shields.io/badge/Groq-Primary%20LLM-F55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com/)
[![Gemini](https://img.shields.io/badge/Gemini-LLM%20Failover-8E75B2?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-Local%20State-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org/)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/rajatmurhe/clinicvoice-ai/actions/workflows/ci.yml)

**Live Application:** https://clinicvoice-ai.onrender.com/

ClinicVoice AI is a voice-first clinic receptionist that answers clinic FAQs,
supports appointment booking and verified appointment changes, logs refill
requests, and records non-diagnostic intake notes. Patients can speak or type
in English, Hindi, or Marathi and hear the assistant's reply.

The project combines deterministic clinic workflows with a guardrailed FAQ
assistant. Its offline evaluation suite covers 180+ cases, and its 46-case
red-team set tracks attacks and first-layer safety behavior. Evaluation
limitations are documented below; these results are not a clinical or
production privacy certification.

Free-tier hosting can take 20–60 seconds to wake after inactivity.

---

## Dashboard

### Voice Assistant Home

![ClinicVoice AI voice assistant dashboard](docs/screenshots/clinicvoice-english.png)

### Hindi Appointment Booking

![ClinicVoice AI responding to a Hindi appointment request](docs/screenshots/clinicvoice-hindi-booking.png)

### Marathi Appointment Verification

![ClinicVoice AI asking for registered patient verification in Marathi](docs/screenshots/clinicvoice-marathi-verification.png)

## Architecture

```
Browser (voice in/out, browser recognition with recorded-audio fallback)
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
   |-- Groq LLM (gpt-oss-20b), with Gemini failover, for answers; output filter on the reply
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

## Conversation Workflow

```text
Patient voice or text
        |
        v
Transcription (voice) -> safety checks -> language-aware intent routing
                                      |
                +---------------------+--------------------+
                |                     |                    |
                v                     v                    v
        Clinic workflow         FAQ retrieval        Reception handoff
        booking/refill/intake    BM25 + trigrams     escalation
                |                     |
                v                     v
        Calendar / SQLite      Groq -> Gemini fallback
                +---------------------+
                            |
                            v
             Localized text + spoken response
```

Appointment reads and changes follow a separate verification path: identify
the patient, match a registered phone number or patient ID, then access the
calendar. A name supplied during the conversation cannot enroll a new identity.

## Key Capabilities

### Voice and Multilingual Conversation

- Browser microphone recording with server transcription and push-to-talk
  fallback when browser speech recognition is unavailable.
- Spoken replies, replay, barge-in, and typed chat as a fallback.
- English, Hindi, and Marathi controls for transcription, intent routing,
  workflow prompts, and playback.
- Frontend waiting indicator for cold starts and delayed responses.

### Clinic Workflows

- Book appointments against the selected clinic's scheduling adapter.
- Look up, reschedule, or cancel an existing appointment only after matching a
  clinic-registered phone number or patient ID.
- Log prescription refill requests and non-diagnostic intake notes.
- Check accepted insurance and route personal requests to reception.
- Support multiple clinics from separate configuration files.

### FAQ Retrieval and Provider Resilience

- Hybrid BM25 and character-trigram retrieval for lexical and multilingual
  matches.
- Groq as the primary FAQ answer provider with Gemini failover on transient
  errors such as timeouts, rate limits, and provider 5xx responses.
- Input and output safety checks remain active around generated answers.
- Optional LangGraph orchestrator, MCP tool transport, LLM intent classifier,
  and compliance reviewer can be evaluated behind feature flags.

### Safety and Evaluation

- Emergency detection, prompt-injection and unsafe-request filters, retrieval
  confidence checks, and generated-answer review.
- Clinic isolation and fail-closed appointment verification.
- Offline flow evaluation, regression tests, and a reproducible red-team set.

## Evaluation Results

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
The six attacks not blocked by the first layer are still reported separately:
the red-team harness uses a FAQ stub, so its blocklist score is not an end-to-end
privacy guarantee. Appointment lookup, cancellation and rescheduling now require
matching a clinic-managed phone number or patient ID before calendar access.
Dedicated regression tests cover wrong identifiers, expiry and clinic isolation.
Full historical tables are in [RED_TEAM.md](RED_TEAM.md).

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

## Quickstart

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

# Unit and regression tests (Python tests, plus Node tests via `cd backend && npx jest`)
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

- Identity verification matches a registered phone number or patient ID; it does
  not prove possession of a phone. Production needs OTP or an authenticated
  patient portal, account-level throttling, and authenticated session ownership.
  Three failures end a challenge; a new conversation can start another one.
  Missing registry records and ambiguous names/appointments require reception.
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

## Technology Stack

### Frontend

React, Vite, browser speech APIs, recorded-audio fallback, responsive CSS.

### Backend

Python, FastAPI, Node.js, Express, SQLite, Docker Compose.

### AI and Retrieval

Groq, Gemini, hybrid BM25 and character-trigram retrieval, optional LangGraph,
MCP tools, optional Ollama embeddings.

### Integrations and Delivery

Google Calendar adapter, FHIR R4 sandbox adapter, GitHub Actions, Render.

## Provider Configuration Details

Set `GROQ_API_KEY` and `GEMINI_API_KEY` in the root `.env` for Docker.
`LLM_PROVIDER=groq|gemini` selects the primary; `GEMINI_MODEL` defaults to
`gemini-3.8-flash` ([Google model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)).
Network errors, timeouts, HTTP 408/429 and 5xx try the configured secondary once.
Each request has an eight-second deadline, keeping both attempts within the
Python FAQ client's twenty-second timeout. Authentication, invalid requests,
malformed/empty responses and provider safety refusals do not trigger failover.
Both providers still pass through the existing input and output guardrails.

## Configure Appointment Verification

For appointment verification, create a **private**, clinic-managed `patients.json`:

```json
[
  {"clinic_id": "default", "name": "Demo Patient", "phone": "9000000000", "patient_id": "DEMO-12345"}
]
```

These are illustrative values only. For native Python, set
`CLINICVOICE_PATIENT_REGISTRY` to the file's absolute path. With Compose, copy
your registry to the persistent volume after starting the stack:

```bash
docker compose cp /absolute/path/patients.json agents:/data/patients.json
```

The application never enrolls an identifier supplied in chat. It asks for the
name, then a registered identifier, then accesses the calendar. Missing or
malformed registries fail closed. Challenges expire after five minutes and
allow three attempts. More than one matching appointment is handed to reception.
New bookings remain available without a registry. Keep registry files out of Git;
`patients.json` is ignored. Restrict filesystem access to the service account.

## Run the Voice Client

Run the voice client locally in a separate terminal:

```bash
cd cloud-frontend
npm ci
VITE_API_URL=http://localhost:5050 VITE_AGENT_URL=http://localhost:8000 npm run dev
```

The mic records audio directly for server transcription: tap to record, then
tap Stop to send. This avoids browser speech-recognition network failures.
The English/Hindi/Marathi selector controls transcription, booking prompts, and playback.
Deterministic booking, refill, insurance, intake, and handoff prompts are
localized for all three supported languages; FAQ replies follow the current
language. Hindi/Marathi playback needs a corresponding browser/system voice.
Repeat replays the last answer without another agent call.
Switching clinic or language clears replay and starts a fresh session. A delayed
request shows a waiting notice after five seconds; text remains
available even when audio cannot play.

## Verification

Validation: `npm test --prefix backend -- --runInBand`, frontend `npm run build`
and `npm run lint`, Python pytest, offline eval and thresholds, graph eval, and
the 46-case red-team run. The existing three FAQ retrieval misses remain;
first-layer red-team catch rate remains 40/46 with zero blocklist drift.
Live provider calls require configured credentials. Microphone interaction needs
a browser; mocked provider tests exercise failover without paid requests.

Local live smoke checks (2026-10-19): Groq and Gemini responses, speech synthesis,
transcription of generated audio, observed Gemini-timeout failover to Groq,
and demo booking/incorrect-ID rejection/correct-ID lookup passed. The audio
route accepts up to 10 MB of JSON so base64 recordings are not rejected by
the default 100 KB parser limit. Browser microphone interaction remains a
manual check. Gemini 3.8 uses low thinking per the [provider documentation](https://ai.google.dev/gemini-api/docs/generate-content/thinking).

The optional Ollama semantic cache is disabled by default to avoid delaying
cloud requests. Enable `CLINICVOICE_SEMANTIC_CACHE=true` only with a working
local `all-minilm` embedding model; embedding calls have short timeouts.
