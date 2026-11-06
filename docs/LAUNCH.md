# ClinicVoice demo launch

This release fixes the administrative-request false positives and protects the public demo path. It remains a synthetic-data demo. Real patient deployment requires stronger verification, persistent distributed abuse controls, access management, retention/deletion, and provider agreements.

## Local Docker setup

Run `python3 scripts/setup_demo.py`, add provider credentials to `.env`, then run `docker compose up --build`. Visit http://localhost:5050. The Node gateway serves the built React UI, proxies agent turns with a server-only key, and serves speech routes to expiring browser sessions. Python calls the internal FAQ/classification routes using the same server-only key.

The bundled registry contains Demo Patient / DEMO-12345 for both demo clinics. Demo-mode calendars are scoped to the browser session. This deliberately public ID must never be used to protect real records. The local volume holds synthetic session and calendar files; remove the Compose volume only when deliberately resetting this demo. Automatic deletion is not implemented.

## Native development

1. Run `python3 scripts/setup_demo.py` and configure provider keys in `.env`.
2. Create a virtual environment and install `python-agents/requirements.txt`.
3. Install dependencies with `npm ci --prefix backend` and `npm ci --prefix cloud-frontend`.
4. In an environment that loads the root `.env`, start Python from `python-agents`: `python -m uvicorn main:app --host 127.0.0.1 --port 8001`. Set `CLINICVOICE_DEMO_MODE=true`, `CLINICVOICE_CALENDAR_MODE=fake`, `CLINICVOICE_PATIENT_REGISTRY` to the absolute bundled demo-patients.json path, and `CLINICVOICE_DATA_DIR` to a local writable directory.
5. From `backend`, run `DOTENV_CONFIG_PATH=../.env node -r dotenv/config server-cloud.js`.
6. Run `npm run dev --prefix cloud-frontend`. Vite proxies `/api` to port 5050; do not point the browser directly at Python.

## Hosted rollout (requires hosting account configuration)

Deploy the agent using `python-agents/Dockerfile`, with its root directory set to `python-agents`. Deploy the gateway using the new **root Dockerfile**, with its root directory set to the repository root. It includes the React production build. Existing deployments that build only `backend/` must change their build configuration.

Configure a random key of at least 32 characters as `CLINICVOICE_SERVICE_KEY` on **both services**. Generate a different admin key as `CLINICVOICE_ADMIN_TOKEN` on Python. Never place either in a frontend/VITE variable or commit them.

Gateway settings:

- `AGENT_INTERNAL_URL`: full HTTP(S) URL for the agent service.
- `CLINICVOICE_ALLOWED_ORIGINS`: exact public UI origin, including scheme; comma-separated if needed, no wildcard.
- `GROQ_API_KEY`, optionally `GEMINI_API_KEY` and `GEMINI_MODEL`.
- `CLINICVOICE_REQUESTS_PER_HOUR`: default 300 gateway/provider requests per process; agent turns and their FAQ provider request can each count.
- `CLINICVOICE_TRUST_PROXY`: leave unset unless the host's actual trusted proxy addresses/CIDRs are known. Do not blindly trust forwarded headers or every proxy.

Agent settings:

- `FAQ_BACKEND_URL`: gateway URL plus `/api/text-query`.
- `CLINICVOICE_ORCHESTRATOR=graph`: enable the LangGraph workflow on the Python service. Install `requirements-prod.txt` for native hosting, or use the Python Dockerfile. `/health` reports `orchestrator: graph`; startup checks graph imports and checkpoint storage.
- Mount persistent storage at `CLINICVOICE_DATA_DIR` if conversations must survive host restarts. Ephemeral hosting storage does not provide that guarantee.
- `CLINICVOICE_DEMO_MODE=true`, `CLINICVOICE_CALENDAR_MODE=fake`.
- `CLINICVOICE_PATIENT_REGISTRY=/app/demo-patients.json` for the supplied Python image.
- `CLINICVOICE_DATA_DIR=/data`, with writable storage, and `VOICE_CLONING_ENABLED=false`.

Set health paths to `/api/health` for the gateway and `/health` for agents. Coordinate both services' keys and URLs before switching traffic. Keep the public demo explicitly synthetic.

Anonymous session issuance is publicly reachable by design. Origin checks and signed tokens prevent accidental cross-site/browser access and unsigned paid calls; they do not identify a person or stop a scripted caller from starting sessions. Global limits are in memory and reset on restart; replicas each have their own budget. Use provider-side spending limits and host-level abuse controls before exposing provider keys publicly.

The changes do not automatically deploy or configure a hosting account. After rollout, verify the root URL serves HTML, run booking/verification/reschedule/cancel, and test actual microphone/transcription/playback on a phone. Local automated tests do not certify live provider or microphone behavior.

## Verification

```bash
npm test --prefix backend -- --runInBand
npm run lint --prefix cloud-frontend
npm run build --prefix cloud-frontend
python -m pytest python-agents/tests -q
python python-eval/run_eval.py --out-dir python-eval/results-ci
python python-eval/check_thresholds.py python-eval/results-ci/eval-offline.json
python python-eval/run_eval.py --redteam --out-dir python-eval/results-ci
python python-eval/check_redteam.py python-eval/results-ci/red-team.json
python scripts/smoke_demo.py
```

The smoke test starts real services in temporary storage without provider keys. It checks the built UI, protected endpoints, booking, verification, rescheduling, cancellation, and Hindi/Marathi slot requests. It does not send audio or charge a provider.

## Resume wording

Use: React, Python/FastAPI, Node/Express, SQLite, Groq, Gemini, Whisper, Docker Compose, GitHub Actions. Describe LangGraph/MCP as optional implementations. Do not claim PostgreSQL, deployed XTTS, Bedrock, a 99% cache improvement, real-clinic usage, or a live completed rollout without corresponding evidence. Red-team CI refers to the workflow in this release; the previous six first-layer gaps remain documented.

Graph verification: `CLINICVOICE_ORCHESTRATOR=graph python scripts/smoke_demo.py` and `python python-eval/run_eval.py --orchestrator graph --out-dir /tmp/clinicvoice-graph-eval`. New Compose and example configurations select graph; existing hosted environment overrides must be updated separately.
