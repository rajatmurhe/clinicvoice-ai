import os
import re
import time

import requests as http_requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from agents.router import classify_intent
from agents.faq_agent import handle_faq
from agents.booking_agent import handle_booking
from agents.escalation_agent import handle_escalation
from agents.refill_agent import handle_refill
from agents.insurance_agent import handle_insurance
from agents.intake_agent import handle_intake
from self_service import maybe_add_nudge
from safety import check_input_safety, check_emergency, BLOCKED_RESPONSE, EMERGENCY_RESPONSE
from dashboard_log import log_query, get_stats
import sessions as session_store
import obs
from rate_limit import SlidingWindowLimiter
import tempfile

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.mount("/dashboard", StaticFiles(directory="static", html=True), name="dashboard")

RATE_LIMITER = SlidingWindowLimiter(
    max_requests=int(os.environ.get("CLINICVOICE_RATE_LIMIT", "60")),
    window_seconds=60,
)

REPEAT_PATTERN = re.compile(r"(what did you say|say that again|repeat that|can you repeat|pardon|come again|sorry what)", re.IGNORECASE)


def clear_pending_flows(session):
    session["booking_in_progress"] = False
    session["lookup_pending"] = None
    session["waitlist_offer"] = None
    session["refill_pending"] = None
    session["intake_pending"] = None
    session["reschedule_pending"] = None


class QueryRequest(BaseModel):
    query: str
    session_id: str = "default"


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or obs.new_request_id()
    obs.set_request_id(request_id)

    path = request.url.path
    if path not in ("/health", "/ready") and not path.startswith("/dashboard"):
        ip = request.client.host if request.client else "unknown"
        if not RATE_LIMITER.allow(ip):
            obs.log_event("rate_limited", route=path, ip=ip)
            response = JSONResponse(
                {"error": "Too many requests. Please wait a moment and try again."},
                status_code=429,
            )
            response.headers["X-Request-ID"] = request_id
            return response

    start = time.time()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    if path not in ("/health", "/ready") and not path.startswith("/dashboard"):
        obs.log_event(
            "request",
            route=path,
            status=response.status_code,
            latency_ms=round((time.time() - start) * 1000, 1),
        )
    return response


@app.get("/health")
def health():
    return {"status": "ok", "message": "Multi-agent orchestrator running", "voice_cloning": VOICE_CLONING_ENABLED}


@app.get("/ready")
def ready():
    checks = {}

    faq_health_url = os.environ.get(
        "FAQ_HEALTH_URL",
        os.environ.get("FAQ_BACKEND_URL", "http://localhost:5050/api/text-query").rsplit("/", 1)[0] + "/api/health",
    )
    try:
        r = http_requests.get(faq_health_url, timeout=2)
        checks["faq_service"] = "ok" if r.status_code == 200 else "degraded (%d)" % r.status_code
    except Exception:
        checks["faq_service"] = "unreachable"

    try:
        from calendar_service import get_calendar_service

        get_calendar_service()
        checks["calendar"] = "ok"
    except Exception as e:
        checks["calendar"] = "unavailable (%s)" % type(e).__name__

    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ready" if ok else "degraded", "checks": checks},
        status_code=200 if ok else 503,
    )


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


@app.get("/api/dashboard/failures")
def dashboard_failures():
    from dashboard_log import get_recent_failures

    return {"failures": get_recent_failures()}


def process_query(req: QueryRequest, session: dict, start: float):
    query = req.query

    if REPEAT_PATTERN.search(query) and session.get("last_response"):
        return {
            "response": session["last_response"],
            "guardrailTriggered": False,
            "agent": "repeat",
            "intent": "repeat",
            "query": query
        }

    if check_emergency(query):
        clear_pending_flows(session)
        result = {
            "response": EMERGENCY_RESPONSE,
            "guardrailTriggered": True,
            "agent": "faq",
            "intent": "emergency",
            "query": query
        }
        session["last_response"] = result["response"]
        obs.log_event("guardrail", kind="emergency", intent="emergency")
        log_query(
            query=query,
            response=result["response"],
            intent="emergency",
            agent="emergency",
            guardrail_triggered=True,
            cache_hit=False,
            latency_ms=round((time.time() - start) * 1000, 1),
            request_id=obs.get_request_id(),
        )
        return result

    if check_input_safety(query):
        clear_pending_flows(session)
        result = {
            "response": BLOCKED_RESPONSE,
            "guardrailTriggered": True,
            "agent": "faq",
            "intent": "faq",
            "query": query
        }
        session["last_response"] = result["response"]
        obs.log_event("guardrail", kind="input_block", intent="faq")
        log_query(
            query=query,
            response=result["response"],
            intent="faq",
            agent="faq",
            guardrail_triggered=True,
            cache_hit=False,
            latency_ms=round((time.time() - start) * 1000, 1),
            request_id=obs.get_request_id(),
        )
        return result

    intent = classify_intent(query)

    STRONG_INTENTS = ("booking", "refill", "insurance", "intake", "escalation")

    pending_flow = None
    if (
        session.get("booking_in_progress")
        or session.get("lookup_pending")
        or session.get("waitlist_offer")
        or session.get("reschedule_pending")
    ):
        pending_flow = "booking"
    elif session.get("refill_pending"):
        pending_flow = "refill"
    elif session.get("intake_pending"):
        pending_flow = "intake"

    if pending_flow:
        if intent == "escalation":
            clear_pending_flows(session)
            obs.log_event("flow_cleared", reason="escalation", previous_flow=pending_flow)
        elif intent not in STRONG_INTENTS or intent == pending_flow:
            intent = pending_flow
        else:
            clear_pending_flows(session)
            obs.log_event("flow_cleared", reason="strong_intent", previous_flow=pending_flow, new_intent=intent)

    if intent == "escalation":
        result = handle_escalation(query)
    elif intent == "booking":
        result = handle_booking(query, session)
    elif intent == "refill":
        result = handle_refill(query, session)
    elif intent == "insurance":
        result = handle_insurance(query, session)
    elif intent == "intake":
        result = handle_intake(query, session)
    else:
        result = handle_faq(query)

    result["intent"] = intent
    result["query"] = query
    result["response"] = maybe_add_nudge(query, result.get("response", ""), result.get("agent", intent))

    session["last_response"] = result.get("response", "")

    total_latency = round((time.time() - start) * 1000, 1)
    error_type = result.get("error_type")
    obs.log_event(
        "query",
        intent=intent,
        agent=result.get("agent", intent),
        guardrail=result.get("guardrailTriggered", False),
        cache_hit=result.get("cache_hit", False),
        latency_ms=result.get("latency_ms", total_latency),
        error_type=error_type,
    )
    log_query(
        query=query,
        response=result.get("response", ""),
        intent=intent,
        agent=result.get("agent", intent),
        guardrail_triggered=result.get("guardrailTriggered", False),
        cache_hit=result.get("cache_hit", False),
        latency_ms=result.get("latency_ms", total_latency),
        request_id=obs.get_request_id(),
        error_type=error_type,
        tokens=result.get("usage_tokens"),
    )

    return result


@app.post("/api/agent-query")
def agent_query(req: QueryRequest):
    start = time.time()
    session = session_store.get_session(req.session_id)
    try:
        return process_query(req, session, start)
    finally:
        session_store.save_session(req.session_id, session)
