"""Shared patient name extraction for the booking, refill and intake agents.

One implementation instead of three diverging copies. Handles "my name is X",
"this is X", "I'm X" and "I am X". The I-forms reject common sentence words so
"I am feeling unwell" or "I am calling about my test results" are not read as
names.
"""

import re

# Words that follow "I am" or "I'm" in normal sentences but are never surnames.
NOT_NAME_WORDS = (
    "feeling", "unwell", "not", "having", "calling", "here", "from", "sick",
    "worried", "just", "also", "trying", "going", "looking", "very", "really",
    "sorry", "sure", "not", "a", "an", "the", "so", "too",
)

NAME_PATTERN = r"([a-zA-Z0-9]+(?:\s[a-zA-Z0-9]+)?)"


def extract_person_name(query: str):
    match = re.search(r"my name is\s+" + NAME_PATTERN, query, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    match = re.search(r"(?:i.?m|i\s+am|this is)\s+" + NAME_PATTERN, query, re.IGNORECASE)
    if match:
        first_word = match.group(1).split()[0].lower()
        if first_word not in NOT_NAME_WORDS:
            return match.group(1).strip()
    return None
