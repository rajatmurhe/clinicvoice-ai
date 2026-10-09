# Decision Records

Short records for design choices where an alternative existed and the eval
decided. Every number comes from the offline harness (`python-eval/run_eval.py`)
on the committed fixed test set.

## 1. Hybrid retrieval (BM25 plus character trigrams) replaced keyword overlap

Date: 8 Oct 2026. Commit range: the Phase 5 changes.

The original retrieval scored a weighted token overlap between the query and
each FAQ question and answer. It measured 63.6 percent hit at 1 and 70.8
percent decision accuracy on the 42 case FAQ set, and scored Devanagari
queries at zero because the old tokenizer stripped every non ASCII character.

The replacement is BM25 over the question tokens (weighted three times) plus
the answer, a Unicode aware tokenizer that keeps Devanagari combining marks,
character trigram similarity as a second opinion, and a disagreement penalty
when the two methods pick different winners. Hindi and Marathi question
variants were added to the FAQ index so cross-lingual queries have something
to match.

Result on the same eval: hit at 1 went from 63.6 to 91.2, decision accuracy
from 70.8 to 98.1, Hindi and Marathi retrieval from 0 to passing (the per
language pass rates went from 0 to 100 on their routing, retrieval and refusal
cases), with the false positive rate on impossible questions still at zero.
The three residual misses are genuinely hard paraphrases ("what kind of clinic
is this" pulls a different FAQ that shares the word clinic) and are listed as
known gaps rather than tuned away, so the test set stays honest.

Kept: the hybrid scorer, threshold unchanged at 0.35 (measured; lower
thresholds trade false positives for nothing at this set size).

## 2. Hybrid router: regex fast path, keywords for Hindi and Marathi, LLM classifier behind a flag

Date: 8 Oct 2026.

Option A was an LLM classifier on every message. Option B was the regex router
plus a small cross-lingual keyword table, with an LLM classifier only for
messages the regex router cannot match (confidence below 0.5), behind
CLINICVOICE_HYBRID_ROUTER.

The offline comparison is necessarily on the deterministic part: the regex
router plus the keyword table took routing accuracy on the annotated single
turn cases from 79.3 to 100 without touching the false positive rate, at zero
latency and zero cost. The LLM classifier path exists (Node
/api/router-classify, strict single word output, regex-safe fallback to faq on
any LLM problem) but stays off by default because the deterministic path
covered every case in the eval. It is there for live phrasings the fixed set
cannot anticipate, and turning it on is a one environment variable change.

Kept: Option B, flag off by default. The flag and the endpoint are the only
code the live classifier needs if the regex path starts missing in real
traffic.

## 3. Guardrail replies now speak the caller's language

Date: 8 Oct 2026.

Devanagari input gets a Hindi or Marathi blocked and emergency message,
selected by a small Marathi hint list (Hindi is the default for Devanagari
scripts when no Marathi hint appears). The unsafe phrase blocklists gained
Hindi and Marathi patterns in both safety layers, kept in sync by the parity
test added in Phase 3. Deliberate exception: the words for medicine (दवा,
औषध) are not blocked bare, because the refill flow needs them; the dosage
words (खुराक, डोस) are blocked. Six Hindi and Marathi attacks were added to
the red team set; all six are caught (see RED_TEAM.md).

## 4. LangGraph orchestrator compared against the hand written one, same eval

Date: 9 Oct 2026.

The flow was rebuilt as a state graph (safety node, router node, one node per
agent, human handoff node) with session state typed and checkpointed to SQLite
by LangGraph's SqliteSaver. Both orchestrators run the same agent handlers, so
the comparison is about orchestration, not logic. The graph path lives behind
CLINICVOICE_ORCHESTRATOR=graph; the legacy path stays the default.

Full offline eval on both paths, same 130 Python driven cases and the same FAQ
node cases, run with `run_eval.py --orchestrator legacy|graph`:

| Metric | Legacy | Graph |
|---|---|---|
| Booking flow pass rate | 100.0 | 100.0 |
| Refill flow pass rate | 100.0 | 100.0 |
| Insurance accuracy | 100.0 | 100.0 |
| Escalation accuracy | 100.0 | 100.0 |
| Safety catch rate | 100.0 | 100.0 |
| False positive rate | 0.0 | 0.0 |
| Hindi pass rate | 100.0 | 100.0 |
| Marathi pass rate | 100.0 | 100.0 |
| Same failures | faq-01, faq-07, faq-21 | faq-01, faq-07, faq-21 |
| Full suite wall time | 2.7s | 9.4s (about 50ms per query overhead) |

No category regressed and the checkpointed state survived a simulated restart
(a booking mid flow continued after the checkpointer was rebuilt from disk),
which the legacy in-process path only gained in Phase 4 via its own SQLite
session store.

Kept: the legacy hand written path as the default. The graph path adds about
50ms per query and a heavy dependency (langgraph) for equal measured quality
on this eval; it earns its place if the flow grows more branching (parallel
nodes, retries per node) or if per thread checkpoint history becomes a
product feature. Both paths stay tested: CI runs the legacy eval plus the
graph unit tests, and the graph eval is one command for anyone who wants to
re-verify.

## 5. Tools behind MCP

Date: 9 Oct 2026.

The calendar operations, the refill and intake logs, and FAQ search are exposed
as an MCP tool server (python-agents/mcp_tools_server.py, seven tools with
typed JSON schemas, stdio transport). The agents reach them through
tools_backend.py, which calls the same functions directly by default and goes
through an MCP client session when CLINICVOICE_TOOLS=mcp. Every tool call is
logged with its request id and counted on the dashboard.

The full offline eval was run with CLINICVOICE_TOOLS=mcp (committed as
results/eval-offline-mcp.json): every category matches the direct-call run
exactly (booking, refills, insurance, escalation, safety, both languages and
routing all 100, FAQ 91.2 hit at 1 with the same 3 residuals). Measured cost of
the one-shot stdio transport: about 0.7 to 2.2 seconds per tool call for
process spawn plus initialize, which is logged and visible on the dashboard.
Production would use a persistent session over the streamable HTTP transport;
the per-call one-shot exists because the stdio transport's async context
managers must stay entered inside one live task, which does not compose with
the synchronous agent call path.

Kept: direct calls as the default (no measured quality gain, real latency
cost), MCP available behind the flag and proven equivalent on the same eval.

## 6. Compliance reviewer agent

Date: 9 Oct 2026.

A rule based reviewer screens each reply against output policy (clinical
advice phrasings, diagnosis statements, identity fishing) before it is spoken,
behind CLINICVOICE_COMPLIANCE_REVIEWER. On the full eval with the reviewer on:
zero false blocks and zero extra catches, because the input blocklist already
stops every unsafe message before a reply exists. Per the phase gate (keep
only if it shows fewer unsafe replies without extra false blocks) it stays off
by default. Its value is defense in depth on the output side, mainly if the
LLM path ever produced a policy violating answer that the input filter could
not have anticipated; the code and tests stay in the repo, one environment
variable turns it on.
