from fastapi import FastAPI
from pydantic import BaseModel
from agents.router import classify_intent
from agents.faq_agent import handle_faq
from agents.booking_agent import handle_booking
from agents.escalation_agent import handle_escalation
from dashboard_log import log_query, get_stats
import time
from fastapi.staticfiles import StaticFiles
from voice_service import synthesize
from fastapi.responses import FileResponse
import tempfile

app = FastAPI(title="ClinicVoice AI - Multi-Agent Orchestrator")
app.mount("/dashboard", StaticFiles(directory="static", html=True), name="dashboard")

SESSIONS = {}


class QueryRequest(BaseModel):
    query: str
    session_id: str = "default"


@app.get("/health")
def health():
    return {"status": "ok", "message": "Multi-agent orchestrator running"}


@app.post("/api/synthesize-voice")
def synthesize_voice(req: QueryRequest):
    temp_path = tempfile.mktemp(suffix=".wav")
    synthesize(req.query, temp_path)
    return FileResponse(temp_path, media_type="audio/wav")


@app.get("/api/dashboard/stats")
def dashboard_stats():
    return get_stats()

@app.post("/api/agent-query")
def agent_query(req: QueryRequest):
    start = time.time()
    intent = classify_intent(req.query)

    if req.session_id not in SESSIONS:
        SESSIONS[req.session_id] = {}

    session = SESSIONS[req.session_id]

    if session.get("booking") and intent != "escalation":
        intent = "booking"

    if intent == "escalation":
        result = handle_escalation(req.query)
    elif intent == "booking":
        result = handle_booking(req.query, session)
    else:
        result = handle_faq(req.query)

    result["intent"] = intent
    result["query"] = req.query

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
