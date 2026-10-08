import re
from pathlib import Path

from safety import BLOCKED_PATTERNS_INPUT, EMERGENCY_PATTERNS

LLM_CLOUD_PATH = Path(__file__).resolve().parents[2] / "backend" / "llm-cloud.js"


def js_array_sources(source, name):
    """Extract the regex sources from `const NAME = [ ... ];` in llm-cloud.js."""
    match = re.search(name + r"\s*=\s*\[(.*?)\];", source, re.DOTALL)
    assert match, "could not find " + name + " in llm-cloud.js"
    body = match.group(1)
    return re.findall(r"/(.*?)/[a-z]*[,;\n]", body)


def test_input_blocklists_are_in_sync():
    # The Python and Node layers must block the same things. These tests fail
    # the build the moment one list is edited without the other.
    js_source = LLM_CLOUD_PATH.read_text()
    assert BLOCKED_PATTERNS_INPUT == js_array_sources(js_source, "BLOCKED_PATTERNS_INPUT")


def test_emergency_lists_are_in_sync():
    js_source = LLM_CLOUD_PATH.read_text()
    assert EMERGENCY_PATTERNS == js_array_sources(js_source, "EMERGENCY_PATTERNS")
