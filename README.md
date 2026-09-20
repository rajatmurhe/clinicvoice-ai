# ClinicVoice AI

A voice assistant for a medical clinic. It answers patient questions,
books real appointments, and speaks its answers back, using a fully
local speech pipeline and a separate multi-agent system for anything
beyond simple FAQ.

**Live demo:** https://clinicvoice-ai-1.onrender.com

## What it does

- Answers clinic FAQs by voice (hours, parking, services)
- Books, looks up, and cancels real appointments on Google Calendar
- Lets a patient request a specific doctor
- Offers a waitlist when a day is fully booked
- Logs prescription refill requests (name and medication only, never dosage)
- Checks accepted insurance providers
- Collects a structured, non-diagnostic reason for calling (a lighter
  version of clinical triage), then hands off to a human clinician
- Escalates frustrated callers to a human
- Answers in Hindi, Marathi, or English depending on how the patient asks
- Caches semantically similar questions so repeat questions answer almost
  instantly instead of calling the LLM again
- Clones a real (public domain) voice locally for text to speech
- Shows a live admin dashboard of real usage, safety triggers, and latency

## Why it is built this way

The core design goal is safety first. A 4-layer guardrail system sits
between the patient and the language model:

1. An input filter blocks clinical questions before they reach the LLM
2. A separate check catches plain greetings so they never need the LLM either
3. A confidence threshold on retrieval means the assistant says "I don't
   know" rather than guessing when nothing relevant is found
4. An output filter scans the model's own generated answer, since a
   hallucination happens in the output, not the question

See COMPLIANCE.md for a full, honest breakdown of what data this system
collects, where it goes, and what a real production deployment would
still need. See EDGE_CASES.md for a log of real bugs found during
development and how each was fixed.

## Architecture

Two backends work together behind one voice pipeline:

- **Node/Express** (`backend/`): speech to text (whisper.cpp), retrieval,
  and the guardrailed LLM call for FAQ answers. Runs entirely locally, no
  external calls.
- **Python/FastAPI** (`python-agents/`): a multi-agent system that routes
  each message to the right handler (FAQ, booking, refill, insurance,
  intake, or escalation) using session state to keep multi-turn
  conversations on track.

A separate cloud deployment (`server-cloud.js`) swaps the local-only
pieces (Ollama, whisper.cpp) for cloud equivalents (Groq) so the same
assistant can run as a public demo.

## Running it locally

Requires Ollama (with `llama3.2:3b` and `all-minilm` pulled) and a Python
virtual environment for the agent service.

```bash
# Terminal 1
ollama serve

# Terminal 2, Node backend
cd backend && node server.js

# Terminal 3, Python multi-agent service
cd python-agents && source venv/bin/activate && uvicorn main:app --port 8000

# Terminal 4, frontend
cd frontend && npm run dev
```

Then open http://localhost:5173.

## Tech stack

Node.js, Express, Python, FastAPI, React, Whisper (whisper.cpp), Ollama,
Groq, Google Calendar API, SQLite, Docker, NestJS, Next.js, GraphQL.
