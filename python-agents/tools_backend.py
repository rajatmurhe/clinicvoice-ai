"""Tool dispatch for the agents: direct calls or MCP, chosen by env.

CLINICVOICE_TOOLS=direct (default) calls the functions in-process.
CLINICVOICE_TOOLS=mcp spawns mcp_tools_server.py over stdio and routes every
tool call through an MCP client session, so the eval can prove the same flows
pass with tools behind MCP.

Every call is logged with its request id, tool name, latency and outcome, and
counted on the dashboard.
"""

import asyncio
import json
import os
import sys
import time
import threading

import dashboard_log
import obs

TOOLS_MODE = os.environ.get("CLINICVOICE_TOOLS", "direct")

_MCP_LOCK = threading.Lock()
_MCP_SESSION = None
_MCP_TOOLS = None


def _log_tool_call(tool, latency_ms, ok, error_type=None):
    obs.log_event("tool_call", tool=tool, latency_ms=latency_ms, ok=ok, error_type=error_type)
    try:
        dashboard_log.log_tool_call(tool=tool, latency_ms=latency_ms, ok=ok, request_id=obs.get_request_id())
    except Exception:
        pass


def _direct(tool_name, fn, *args, **kwargs):
    start = time.time()
    try:
        result = fn(*args, **kwargs)
        _log_tool_call(tool_name, round((time.time() - start) * 1000, 1), True)
        return result
    except Exception as e:
        _log_tool_call(tool_name, round((time.time() - start) * 1000, 1), False, type(e).__name__)
        raise


def _mcp_call(tool_name, arguments):
    """One MCP round trip: spawn the tool server over stdio, initialize,
    call the tool, tear down.

    A persistent session would be faster, but the stdio transport and client
    session are async context managers that must stay entered inside one live
    task, which does not compose with this synchronous call path. The per call
    cost is process spawn plus initialize (about a second) and is logged like
    any other tool latency; a production deployment would switch this to the
    streamable HTTP transport with a persistent client.
    """
    from mcp import ClientSession

    async def _one_shot():
        async with _get_stdio_client()(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool_name, arguments)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_one_shot())
    # Inside a running loop (for example the test client's portal thread),
    # asyncio.run is illegal, so the one shot runs on a worker thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_one_shot())).result(timeout=120)


_MCP_SERVER_PARAMS = None


def _server_params():
    global _MCP_SERVER_PARAMS
    if _MCP_SERVER_PARAMS is None:
        from mcp import StdioServerParameters

        agents_dir = os.path.dirname(os.path.abspath(__file__))
        _MCP_SERVER_PARAMS = StdioServerParameters(
            command=sys.executable,
            args=[os.path.join(agents_dir, "mcp_tools_server.py")],
            env={**os.environ},
        )
    return _MCP_SERVER_PARAMS


_stdio_client = None


def _get_stdio_client():
    global _stdio_client
    if _stdio_client is None:
        from mcp.client.stdio import stdio_client

        _stdio_client = stdio_client
    return _stdio_client


def _call(tool_name, arguments, direct_fn, list_result=False):
    start = time.time()
    try:
        if TOOLS_MODE == "mcp":
            result = _mcp_call(tool_name, arguments)
            # mcp 2.x names it is_error; older versions isError.
            ok = not (getattr(result, "is_error", False) or getattr(result, "isError", False))
            texts = [getattr(c, "text", "") for c in (result.content or [])]
            if len(texts) == 1:
                try:
                    content = json.loads(texts[0])
                except (ValueError, TypeError):
                    content = texts[0]
            else:
                # List results come back as one text block per element.
                content = []
                for t in texts:
                    try:
                        content.append(json.loads(t))
                    except (ValueError, TypeError):
                        content.append(t)
            if list_result and not isinstance(content, list):
                content = [content]
        else:
            content = direct_fn(**arguments)
            ok = True
        _log_tool_call(tool_name, round((time.time() - start) * 1000, 1), ok)
        return content
    except Exception as e:
        _log_tool_call(tool_name, round((time.time() - start) * 1000, 1), False, type(e).__name__)
        raise


# --- Public API: same names and shapes the agents used to import directly. ---


def get_available_slots(date_str, duration_minutes=30, doctor=None):
    import calendar_service

    return _call(
        "calendar_get_available_slots",
        {"date": date_str, **({"doctor": doctor} if doctor else {})},
        lambda **kw: calendar_service.get_available_slots(date_str, duration_minutes=duration_minutes, doctor=kw.get("doctor")),
        list_result=True,
    )


def book_appointment(date_str, time_str, patient_name, duration_minutes=30, doctor=None):
    import calendar_service

    return _call(
        "calendar_book_appointment",
        {"date": date_str, "time": time_str, "patient_name": patient_name, **({"doctor": doctor} if doctor else {})},
        lambda **kw: calendar_service.book_appointment(date_str, time_str, patient_name, duration_minutes=duration_minutes, doctor=kw.get("doctor")),
    )


def find_appointments_by_name(patient_name, days_ahead=30):
    import calendar_service

    return _call(
        "calendar_find_appointments_by_name",
        {"patient_name": patient_name},
        lambda **kw: calendar_service.find_appointments_by_name(patient_name, days_ahead=days_ahead),
        list_result=True,
    )


def cancel_appointment(event_id):
    import calendar_service

    return _call(
        "calendar_cancel_appointment",
        {"event_id": event_id},
        lambda **kw: calendar_service.cancel_appointment(event_id),
    )


def log_refill_request(patient_name, medication_mentioned):
    import refill_log

    return _call(
        "records_log_refill_request",
        {"patient_name": patient_name, "medication": medication_mentioned},
        lambda **kw: refill_log.log_refill_request(kw["patient_name"], kw["medication"]),
    )


def log_intake(patient_name, reason_category, body_area=None):
    import intake_log

    return _call(
        "records_log_intake",
        {"patient_name": patient_name, "reason_category": reason_category, **({"body_area": body_area} if body_area else {})},
        lambda **kw: intake_log.log_intake(kw["patient_name"], kw["reason_category"], kw.get("body_area")),
    )
