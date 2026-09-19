# ClinicVoice AI — Data Handling & Compliance Notes

This document describes how ClinicVoice AI actually handles data, as a reference
for evaluating its fit against healthcare data-protection principles such as
GDPR (EU/UK) and general HIPAA-style expectations. It is an engineering
description of the real system, not a legal compliance certification.

## 1. What data the system processes

A user interaction with ClinicVoice AI can include:

- **Voice audio** (local pipeline only) — captured in the browser, sent to the
  backend for transcription, then deleted.
- **Transcribed text** — the question itself, which may include a name if the
  user states one (e.g. "My name is Rajat").
- **Conversation history** — up to the last 6 messages, used only to give the
  LLM conversational context. Sent with each request, not persisted server-side
  beyond the life of that request in the local pipeline.
- **Booking details** — when using the calendar-booking agent: a date, a time,
  and a name, which becomes the title of a real calendar event.

The system does **not** collect or request: medical history, symptoms,
diagnoses, medication details, insurance numbers, or any other sensitive
health data. This is enforced structurally, not just by policy — see Section 4.

## 2. Where data goes, by component

| Component | What it stores | Retention |
|---|---|---|
| `backend/server.js` (local voice pipeline) | Uploaded audio file, converted WAV | Deleted immediately after each request (`fs.unlinkSync`) |
| `backend/logger.js` | Transcript, top retrieval match, response, guardrail flag, latency | Appended to a local JSON-lines file (`logs/pipeline.log`), never transmitted externally |
| `backend/data/clinic.db` (SQLite) | Static FAQ knowledge base only | Not user data — read-only reference content |
| `python-agents/dashboard_log.py` | Query text, response text, intent, agent, guardrail flag, cache-hit flag, latency | Local SQLite file (`dashboard.db`), used only for the admin dashboard, gitignored, never leaves the machine it runs on |
| `python-agents/semantic_cache.py` | Query text + embedding + response, in-memory only | Cleared on every server restart — never written to disk |
| Google Calendar (via service account) | Appointment date, time, and the name given at booking | Retained per the clinic's own calendar until manually deleted — this is the one piece of data that persists outside the local machine by design, since it's the actual appointment record |
| Groq (cloud LLM/TTS, cloud deployment only) | The query text sent for that single request | Per Groq's own data-handling terms — not controlled by this project; only the cloud deployment sends data externally, the local pipeline never does |

## 3. What never leaves the local machine (local deployment)

The local pipeline (`server.js`, Ollama, whisper.cpp) runs entirely on-device:
speech recognition, retrieval, and generation all happen locally. No audio, no
transcript, and no query text is sent to any third party. This was a deliberate
architectural choice, made early in the project specifically for
data-locality reasons in a healthcare context — see the project's build notes.

The **live cloud deployment** is a separate, explicitly-labeled variant that
trades local processing for public accessibility, using Groq for LLM/TTS. Its
existence and data flow are disclosed here rather than hidden, since a real
compliance review needs to know both variants exist.

## 4. Guardrails as a compliance control, not just a UX feature

The 4-layer safety system (input pattern check, greeting detection, confidence
threshold, output pattern check) exists specifically so the assistant never
asks for or generates identity-verifying information (date of birth, ID
numbers) or clinical advice. This was tightened after a real bug was found
during development, where the LLM invented a fake identity-verification step —
the fix (an output-side check, not just an input-side one) is a direct example
of defense-in-depth: even if a bad output is generated, it's caught before
reaching the user.

## 5. Known gaps (honest, not exhaustive)

This project is a portfolio/interview build, not a certified production
healthcare system. Concretely:

- No encryption-at-rest is applied to the local log files or the dashboard's
  SQLite database — acceptable for a local dev machine, not for a real
  deployment holding patient data.
- No formal Data Processing Agreement exists with Groq, since this is a
  demo, not a live clinic.
- No user-facing mechanism exists yet to request deletion of a specific
  logged interaction (the "right to erasure" under GDPR) — the closest
  equivalent today is manually clearing the log files.
- The Google Calendar integration uses a single shared service account
  rather than per-clinic access scoping, which would need to change for a
  genuine multi-tenant product.

A real deployment would need: encryption at rest, a signed DPA with any
third-party LLM/TTS provider, an audit log separate from the operational
log, and a data-retention policy with an actual deletion mechanism — none of
which are hard to add given the current architecture, but none of which
are pretended to already exist here.

## 6. Relationship to DTAC (Digital Technology Assessment Criteria)

DTAC is the NHS framework used to assess digital health tools before adoption
by GP surgeries. It covers five areas: clinical safety, data protection,
technical security, interoperability, and usability/accessibility. This
project is a portfolio build, not a submitted or assessed DTAC product, but
its design choices map onto DTAC's structure deliberately:

- **Clinical safety**: enforced through the 4-layer guardrail system (see
  Section 4), which prevents diagnostic or advice-giving responses and
  escalates anything outside the assistant's scope to a human.
- **Data protection**: covered in Sections 1 to 3 above (what is collected,
  where it goes, what never leaves the local machine).
- **Technical security**: rate limiting, input validation, and the known
  gaps in Section 5 are the honest starting point for a real security
  review, not a claim of completion.
- **Interoperability**: the assistant integrates with a real external
  system (Google Calendar) via a documented service account pattern, the
  same shape of integration a real NHS booking or consultation system would
  need.
- **Usability and accessibility**: voice-first design with a clear,
  disclosed scope (appointment and clinic information only) so patients are
  never left unsure whether they are talking to a clinician.

This project does not claim DTAC compliance. It is built with DTAC's
structure in mind so that the gap between a portfolio build and a
DTAC-assessed product is well understood.
