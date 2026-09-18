from fastapi import FastAPI
from pydantic import BaseModel
from agents.router import classify_intent
from agents.faq_agent import handle_faq
from agents.booking_agent import handle_booking
from agents.escalation_agent import handle_escalation
from agents.refill_agent import handle_refill
from agents.insurance_agent import handle_insurance
from dashboard_log import log_query, get_stats
import time
import re
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import tempfile
import os

VOICE_CLONING_ENABLED = os.environ.get("VOICE_CLONING_ENABLED", "true").lower() == "true"

if VOICE_CLONING_ENABLED:
    try:
        from voice_service import synthesize
    except Exception:
        VOICE_CLONING_ENABLED = False
        synthesize = None
else:
    synthesize = None

app = FastAPI(title="ClinicVoice AI - Multi-Agent Orchestrator")
app.mount("/dashboard", StaticFiles(directory="static", html=True), name="dashboard")

SESSIONS = {}

REPEAT_PATTERN = re.compile(r"(what did you say|say that again|repeat that|can you repeat|pardon|come again|sorry what)", re.IGNORECASE)


class QueryRequest(BaseModel):
    query: str
    session_id: str = "default"


@app.get("/health")
def health():
    return {"status": "ok", "message": "Multi-agent orchestrator running", "voice_cloning": VOICE_CLONING_ENABLED}


@app.post("/api/synthesize-voice")
def synthesize_voice(req: QueryRequest):
    if not VOICE_CLONING_ENABLED or synthesize is None:
        return {"error": "Voice cloning is not available on this deployment."}
    temp_path = tempfile.mktemp(suffix=".wav")
    synthesize(req.query, temp_path)
    return FileResponse(temp_path, media_type="audio/wav")


@app.get("/api/dashboard/stats")
def dashboard_stats():
    return get_stats()


@app.post("/api/agent-query")
def agent_query(req: QueryRequest):
    start = time.time()

    if req.session_id not in SESSIONS:
        SESSIONS[req.session_id] = {}

    session = SESSIONS[req.session_id]

    if REPEAT_PATTERN.search(req.query) and session.get("last_response"):
        return {
            "response": session["last_response"],
            "guardrailTriggered": False,
            "agent": "repeat",
            "intent": "repeat",
            "query": req.query
        }

    intent = classify_intent(req.query)

    if (session.get("booking_in_progress") or session.get("lookup_pending") or session.get("waitlist_offer")) and intent != "escalation":
        intent = "booking"

    if session.get("refill_pending") and intent != "escalation":
        intent = "refill"

    if intent == "escalation":
        result = handle_escalation(req.query)
    elif intent == "booking":
        result = handle_booking(req.query, session)
    elif intent == "refill":
        result = handle_refill(req.query, session)
    elif intent == "insurance":
        result = handle_insurance(req.query, session)
    else:
        result = handle_faq(req.query)

    result["intent"] = intent
    result["query"] = req.query

    session["last_response"] = result.get("response", "")

    total_latency = round((time.time() - start) * 1000, 1)
    log_query(
        query=req.query,
        response=result.get("response", ""),
        intent=intent,
        agent=result.get("agent", intent),
        guardrail_triggered=result.get("guardrailTriggered", False),
        cache_hit=result.get("cache_hit", False),
        latency_ms=result.get("latency_ms", total_latency)
    )

    return result
