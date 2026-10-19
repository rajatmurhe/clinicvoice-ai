"""LangGraph based orchestrator, run behind CLINICVOICE_ORCHESTRATOR=graph.

A state graph version of the same flow the legacy orchestrator implements by
hand: a safety node, a router node, one node per agent, and a human handoff
node. Session state is a typed dict checkpointed to SQLite by SqliteSaver, so
a restart does not erase a flow in progress.

The agent handlers themselves are shared with the legacy path, so both
orchestrators run the same logic and are comparable on the same eval.
"""

import os
import sqlite3
from typing import Any, Dict, Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict

from agents import booking_agent, escalation_agent, faq_agent, insurance_agent, intake_agent, refill_agent
from agents.router import classify_intent_with_confidence
from safety import check_input_safety, check_emergency, blocked_response_for, emergency_response_for

_DATA_DIR = os.environ.get("CLINICVOICE_DATA_DIR") or os.path.dirname(__file__)
CHECKPOINT_DB = os.path.join(_DATA_DIR, "graph-checkpoints.sqlite")


class OrchestratorState(TypedDict):
    query: str
    intent: str
    agent: str
    response: str
    guardrail_triggered: bool
    session: Dict[str, Any]
    error_type: Optional[str]


def safety_node(state: OrchestratorState) -> dict:
    query = state["query"]
    session = state["session"]
    if check_emergency(query):
        _clear_flows(session)
        return {
            "response": emergency_response_for(query),
            "guardrail_triggered": True,
            "agent": "emergency",
            "intent": "emergency",
            "session": session,
        }
    if check_input_safety(query):
        _clear_flows(session)
        return {
            "response": blocked_response_for(query),
            "guardrail_triggered": True,
            "agent": "faq",
            "intent": "faq",
            "session": session,
        }
    return {}


def _clear_flows(session):
    session["booking_in_progress"] = False
    session["lookup_pending"] = None
    session["verification_pending"] = None
    session["waitlist_offer"] = None
    session["refill_pending"] = None
    session["intake_pending"] = None
    session["reschedule_pending"] = None


STRONG_INTENTS = ("booking", "refill", "insurance", "intake", "escalation")


def _pending_flow(session):
    if (
        session.get("verification_pending")
        or session.get("booking_in_progress")
        or session.get("lookup_pending")
        or session.get("waitlist_offer")
        or session.get("reschedule_pending")
    ):
        return "booking"
    if session.get("refill_pending"):
        return "refill"
    if session.get("intake_pending"):
        return "intake"
    return None


def router_node(state: OrchestratorState) -> dict:
    query = state["query"]
    session = state["session"]
    intent, _confidence = classify_intent_with_confidence(query)
    pending = _pending_flow(session)
    if pending:
        if intent == "escalation":
            _clear_flows(session)
        elif intent not in STRONG_INTENTS or intent == pending:
            intent = pending
        else:
            _clear_flows(session)
    return {"intent": intent, "session": session}


def booking_node(state: OrchestratorState) -> dict:
    result = booking_agent.handle_booking(state["query"], state["session"])
    return {"response": result.get("response", ""), "agent": result.get("agent", "booking"), "guardrail_triggered": result.get("guardrailTriggered", False), "session": state["session"], "error_type": result.get("error_type")}


def refill_node(state: OrchestratorState) -> dict:
    result = refill_agent.handle_refill(state["query"], state["session"])
    return {"response": result.get("response", ""), "agent": result.get("agent", "refill"), "guardrail_triggered": result.get("guardrailTriggered", False), "session": state["session"], "error_type": result.get("error_type")}


def insurance_node(state: OrchestratorState) -> dict:
    result = insurance_agent.handle_insurance(state["query"], state["session"])
    return {"response": result.get("response", ""), "agent": result.get("agent", "insurance"), "guardrail_triggered": result.get("guardrailTriggered", False), "error_type": result.get("error_type")}


def intake_node(state: OrchestratorState) -> dict:
    result = intake_agent.handle_intake(state["query"], state["session"])
    return {"response": result.get("response", ""), "agent": result.get("agent", "intake"), "guardrail_triggered": result.get("guardrailTriggered", False), "session": state["session"], "error_type": result.get("error_type")}


def faq_node(state: OrchestratorState) -> dict:
    # Module attribute access so the eval harness can stub the FAQ backend the
    # same way it does for the legacy path.
    result = faq_agent.handle_faq(state["query"], state.get("session", {}).get("clinic_id"))
    return {"response": result.get("response", ""), "agent": result.get("agent", "faq"), "guardrail_triggered": result.get("guardrailTriggered", False), "error_type": result.get("error_type")}


def handoff_node(state: OrchestratorState) -> dict:
    result = escalation_agent.handle_escalation(state["query"], state.get("session", {}))
    return {"response": result.get("response", ""), "agent": result.get("agent", "escalation"), "guardrail_triggered": result.get("guardrailTriggered", False)}


def route_to_agent(state: OrchestratorState) -> str:
    return state["intent"]


def blocked_or_continue(state: OrchestratorState) -> str:
    if state.get("guardrail_triggered"):
        return END
    return "router"


def build_graph(checkpointer=None):
    graph = StateGraph(OrchestratorState)
    graph.add_node("safety", safety_node)
    graph.add_node("router", router_node)
    graph.add_node("booking", booking_node)
    graph.add_node("refill", refill_node)
    graph.add_node("insurance", insurance_node)
    graph.add_node("intake", intake_node)
    graph.add_node("faq", faq_node)
    graph.add_node("handoff", handoff_node)

    graph.add_edge(START, "safety")
    graph.add_conditional_edges("safety", blocked_or_continue)
    graph.add_conditional_edges("router", route_to_agent, {
        "booking": "booking",
        "refill": "refill",
        "insurance": "insurance",
        "intake": "intake",
        "faq": "faq",
        "escalation": "handoff",
    })
    for node in ("booking", "refill", "insurance", "intake", "faq", "handoff"):
        graph.add_edge(node, END)

    return graph.compile(checkpointer=checkpointer)


_CHECKPOINTER = None
_APP = None


def get_app():
    global _CHECKPOINTER, _APP
    if _APP is None:
        conn = sqlite3.connect(
            CHECKPOINT_DB, check_same_thread=False,
        )
        _CHECKPOINTER = SqliteSaver(conn)
        _APP = build_graph(checkpointer=_CHECKPOINTER)
    return _APP


def run_query(query: str, session_id: str, clinic_id="default", language="en") -> dict:
    app = get_app()
    config = {"configurable": {"thread_id": clinic_id + ":" + session_id}}
    existing = app.get_state(config)
    session = {}
    if existing and existing.values and existing.values.get("session"):
        session = existing.values["session"]
    verification_turn = bool(session.get("verification_pending"))
    session["clinic_id"] = clinic_id
    session["language"] = language if language in ("en", "hi", "mr") else "en"
    result = app.invoke({"query": query, "session": session, "guardrail_triggered": False, "error_type": None}, config=config)
    if verification_turn:
        app.update_state(config, {"query": "[verification response redacted]"})
    return {
        "response": result.get("response", ""),
        "guardrailTriggered": result.get("guardrail_triggered", False),
        "agent": result.get("agent", "faq"),
        "intent": result.get("intent", "faq"),
        "query": "[verification response redacted]" if verification_turn else query,
        "error_type": result.get("error_type"),
    }
