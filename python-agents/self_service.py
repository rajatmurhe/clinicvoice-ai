import re

NUDGE_TEXT = " You can also manage this anytime through our online patient portal."

NUDGE_TRIGGERS = re.compile(
    r"(opening hours|when is the clinic|how do i book|appointment|reschedule)",
    re.IGNORECASE
)


def maybe_add_nudge(query, response, agent):
    if agent not in ("faq", "booking"):
        return response
    if not NUDGE_TRIGGERS.search(query):
        return response
    if "portal" in response.lower():
        return response
    return response + NUDGE_TEXT
