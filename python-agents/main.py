from fastapi import FastAPI
from pydantic import BaseModel
from agents.router import classify_intent
from agents.faq_agent import handle_faq
from agents.booking_agent import handle_booking
from agents.escalation_agent import handle_escalation

app = FastAPI(title="ClinicVoice AI - Multi-Agent Orchestrator")


class QueryRequest(BaseModel):
    query: str


@app.get("/health")
def health():
    return {"status": "ok", "message": "Multi-agent orchestrator running"}


@app.post("/api/agent-query")
def agent_query(req: QueryRequest):
    intent = classify_intent(req.query)

    if intent == "escalation":
        result = handle_escalation(req.query)
    elif intent == "booking":
        result = handle_booking(req.query)
    else:
        result = handle_faq(req.query)

    result["intent"] = intent
    result["query"] = req.query
    return result
