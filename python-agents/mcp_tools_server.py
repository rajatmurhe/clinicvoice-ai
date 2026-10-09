"""MCP tool server for the clinic backend tools.

Exposes the calendar operations, the refill and intake logs, and the FAQ
search as MCP tools with typed schemas (JSON Schema derived from the function
signatures). Run standalone for manual testing:

    python mcp_tools_server.py        # speaks MCP over stdio

The orchestrator normally spawns it itself (see tools_backend.py) when
CLINICVOICE_TOOLS=mcp, so agents reach these tools through an MCP client
session instead of direct function calls.
"""

import asyncio

from mcp.server.mcpserver import MCPServer

import calendar_service
import refill_log
import intake_log

server = MCPServer("clinic-tools")


def calendar_get_available_slots(date: str, doctor: str | None = None) -> list[str]:
    """List free 30 minute slots on a date (YYYY-MM-DD), optionally for one doctor (e.g. 'Dr. Patel')."""
    return calendar_service.get_available_slots(date, doctor=doctor)


def calendar_book_appointment(date: str, time: str, patient_name: str, doctor: str | None = None) -> str:
    """Book a 30 minute appointment at a date (YYYY-MM-DD) and time (hh:mm AM/PM) for a patient. Idempotent for the same name, date, time and doctor."""
    event_id = calendar_service.book_appointment(date, time, patient_name, doctor=doctor)
    return event_id


def calendar_find_appointments_by_name(patient_name: str) -> list[dict]:
    """Find upcoming appointments (next 30 days) whose summary contains the patient name."""
    return calendar_service.find_appointments_by_name(patient_name)


def calendar_cancel_appointment(event_id: str) -> bool:
    """Cancel (delete) the appointment with this event id."""
    return calendar_service.cancel_appointment(event_id)


def records_log_refill_request(patient_name: str, medication: str) -> bool:
    """Log a prescription refill request with patient name and medication name only. Never include dosage."""
    refill_log.log_refill_request(patient_name, medication)
    return True


def records_log_intake(patient_name: str, reason_category: str, body_area: str | None = None) -> bool:
    """Log a non diagnostic intake note: reason category (test results, ongoing symptom, prescription, admin) and body area."""
    intake_log.log_intake(patient_name, reason_category, body_area)
    return True


def faq_search(query: str) -> dict:
    """Search the clinic FAQ index. Returns the top matches with scores. Answer generation happens in the FAQ service."""
    import os

    import requests

    url = os.environ.get("FAQ_BACKEND_URL", "http://localhost:5050/api/text-query")
    try:
        response = requests.post(url, json={"query": query}, timeout=(3, 10))
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": "faq_service_unreachable", "detail": type(e).__name__}


server.add_tool(calendar_get_available_slots)
server.add_tool(calendar_book_appointment)
server.add_tool(calendar_find_appointments_by_name)
server.add_tool(calendar_cancel_appointment)
server.add_tool(records_log_refill_request)
server.add_tool(records_log_intake)
server.add_tool(faq_search)

TOOL_NAMES = [
    "calendar_get_available_slots",
    "calendar_book_appointment",
    "calendar_find_appointments_by_name",
    "calendar_cancel_appointment",
    "records_log_refill_request",
    "records_log_intake",
    "faq_search",
]


if __name__ == "__main__":
    server.run("stdio")
