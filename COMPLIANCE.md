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

The booking verification flow requests a registered phone number or patient ID.
Refill requests may include medication names, and intake may include a reason
category/body area. User text can contain other sensitive information even when
a guardrail refuses the request; refusal is not data minimization by itself.

## 2. Where data goes, by component

| Component | What it stores | Retention |
|---|---|---|
| `backend/server.js` (local voice pipeline) | Uploaded audio file, converted WAV | Deleted immediately after each request (`fs.unlinkSync`) |
| `backend/logger.js` | Transcript, top retrieval match, response, guardrail flag, latency | Appended to a local JSON-lines file (`logs/pipeline.log`), never transmitted externally |
| `backend/data/clinic.db` (SQLite) | Static FAQ knowledge base only | Not user data — read-only reference content |
| `python-agents/dashboard_log.py` | Query text, response text, intent, agent, guardrail flag, cache-hit flag, latency | Local SQLite file (`dashboard.db`), used only for the admin dashboard, gitignored, never leaves the machine it runs on |
| `python-agents/semantic_cache.py` | Query text + embedding + response, in-memory only | Cleared on every server restart — never written to disk |
| Google Calendar (via service account) | Appointment date, time, and the name given at booking | Retained per the clinic's own calendar until manually deleted — this is the one piece of data that persists outside the local machine by design, since it's the actual appointment record |
| Groq and Google Gemini (cloud FAQ; Groq also provides speech services) | The query text sent for that single request | Per each provider's data-handling terms — not controlled by this project; only the cloud deployment sends data externally, the local pipeline never does |
| Langfuse (optional cloud FAQ tracing) | Request ID, clinic ID, prepared SQL template, retrieval result IDs/scores, validation outcomes, model/provider, latency, and token usage. Question/answer/prompt content is omitted by default. | Langfuse project retention and data region settings; this project does not enforce provider-side deletion |

## 3. What never leaves the local machine (local deployment)

The local pipeline (`server.js`, Ollama, whisper.cpp) runs entirely on-device:
speech recognition, retrieval, and generation all happen locally. No audio, no
transcript, and no query text is sent to any third party. This was a deliberate
architectural choice, made early in the project specifically for
data-locality reasons in a healthcare context — see the project's build notes.

The **live cloud deployment** is a separate, explicitly-labeled variant that
trades local processing for public accessibility, using Groq for LLM/TTS and Gemini for optional FAQ failover. Its
existence and data flow are disclosed here rather than hidden, since a real
compliance review needs to know both variants exist.

## 4. Guardrails as a compliance control, not just a UX feature

The 4-layer safety system (input pattern check, greeting detection, confidence
threshold, output pattern check) exists specifically so the FAQ LLM does not invent identity-verification procedures or clinical
advice. The deterministic booking agent separately asks for registered identity
details before calendar access. This was tightened after a real bug was found
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
  - Appointment access requires an exact clinic-scoped registry match. Merely
    providing digits is insufficient. This is knowledge verification, not OTP;
    a caller who knows the registered identifier can still impersonate a patient.
    Session IDs are not authenticated and challenge limits reset with a new flow.


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

## 7. Verification registry and Gemini data flow

`CLINICVOICE_PATIENT_REGISTRY` points to a private JSON file managed by clinic
staff, containing clinic ID, exact patient name and phone and/or patient ID.
It is read locally, never sent to an LLM, and has no automatic retention policy.
Missing, invalid or ambiguous records fail closed. Calendar access follows a
successful match, with five-minute challenges and three attempts per challenge.
Ambiguous appointments require reception. Enrollment from chat is not allowed.

Verification-turn text is redacted in dashboard query logging. Browser transcripts
still contain what the user entered. LangGraph checkpoint history can retain raw
turn inputs, including identifiers; the latest state is redacted but this does
not erase historical checkpoints. Protect these SQLite files and establish
retention/deletion before real patient use. Session state and calendar records
also persist locally; the local voice-only pipeline description above does not
apply to the cloud orchestrator.

When a configured FAQ provider has a transient failure, the same FAQ prompt
(question and retrieved context) may be sent to the other provider, including
Google Gemini. Gemini receives this data even when Groq is primary. Provider
retention and contractual terms need separate review; this project supplies no
BAA/DPA or certification. Groq remains the provider for hosted transcription/TTS.
The browser speech-recognition service may also process microphone audio.

Langfuse FAQ tracing is disabled unless `LANGFUSE_ENABLED=true` and both
Langfuse keys are configured. `LANGFUSE_TRACE_CONTENT=false` is the default:
the trace contains metadata and the fixed, parameterized FAQ SQL template, but
not the user's question, model prompt, FAQ content, or generated answer. Setting
`LANGFUSE_TRACE_CONTENT=true` sends the question, prompt, and answer to the
configured Langfuse project; enable it only after reviewing the project's
region, access controls, retention, and contractual terms for the data you
intend to trace. Do not use identifiable patient data with a demo Langfuse
project. ClinicVoice does not generate SQL; it retrieves FAQs with a fixed
SQLite statement. Provider-reported token usage is attached to generation
traces; Langfuse cost is inferred from that model's configured price and can be
missing or approximate if the model/provider price is not configured.
