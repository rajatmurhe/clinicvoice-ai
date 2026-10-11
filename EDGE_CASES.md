# Edge Cases and Troubleshooting Log

Real bugs found during development of ClinicVoice AI, how they were
diagnosed, and how they were fixed. Kept as a living record of what
"instrument pipelines, analyze logs, and troubleshoot edge cases" actually
looks like on this project, not a list of hypothetical problems.

## 1. LLM hallucinated an identity verification step

**Symptom**: the assistant occasionally asked patients for a date of birth
or NHS number before answering a normal question, even though no part of
the knowledge base or prompt ever describes such a step.

**Diagnosis**: the LLM was inventing a plausible-sounding clinic procedure
that does not exist, a classic hallucination under a loosely constrained
prompt.

**Fix**: added an output-side guardrail that scans the model's own
generated response for identity-verification language and blocks it,
separate from the input-side check that scans the user's question. This
was the reasoning behind the whole 4-layer safety design: a hallucination
in the output needs its own check, an input filter alone cannot catch it.

## 2. Confidence-threshold gate silently masking real coverage gaps

**Symptom**: "Do you accept international insurance?" always returned "I
don't know," even after insurance information was added to the knowledge
base.

**Diagnosis**: the retrieval confidence score for that exact phrasing sat
just under the cutoff, so the LLM was never even called.

**Fix**: not a code fix, a data fix. Once a real, matching FAQ entry
existed, the same question resolved correctly on its own. This is the
expected behavior of a confidence gate: it is honest about not knowing
something, which is preferable to a fluent wrong answer, but it means gaps
in the knowledge base show up as "I don't know" rather than a crash, and
need to be checked for deliberately.

## 3. Output guardrail false positive on a legitimate answer

**Symptom**: "What is this clinic?" got blocked by the safety system, even
though the generated answer was accurate and simply mentioned
"prescription support" as one of the clinic's services.

**Diagnosis**: the same blocked-word list was being used for both the
input check (should be broad, catch any clinical question) and the output
check (should be narrow, catch only actual advice-giving language). The
word "prescri" alone was enough to trip the output check.

**Fix**: split into two separate pattern lists with different sensitivity.
The input list stayed broad. The output list was narrowed to phrases that
actually indicate advice-giving, like "you should take" or "recommended
dose," not just the presence of a clinical-sounding word.

## 4. Safari cannot record audio in the format the code assumed

**Symptom**: every voice recording in Safari produced either a 0-byte file
or a transcript of `[BLANK_AUDIO]`.

**Diagnosis**: the code hardcoded `audio/webm` as the recording format.
Safari's MediaRecorder does not support webm at all, only mp4/AAC. Safari
was silently producing a mislabeled, unusable file rather than throwing an
error.

**Fix**: detect the browser's actual supported format at runtime with
`MediaRecorder.isTypeSupported()` and use whatever it reports, instead of
assuming one format works everywhere.

## 5. A router that only recognizes exact keywords breaks mid conversation

**Symptom**: after the assistant asked "what date would you like?", a
completely natural reply like "tomorrow 3pm" got routed to the FAQ agent
instead of continuing the booking flow.

**Diagnosis**: the keyword-based router only looked at the current message
in isolation. A date with no booking-related words in it does not match
any booking pattern, so it fell through to the default FAQ path.

**Fix**: added explicit session state (`booking_in_progress`) that the
router checks before falling back to keyword matching. If a booking
conversation is already underway, the next message stays routed to
booking regardless of its wording. The same pattern was later reused for
refill requests, waitlist offers, and the intake flow, since all of them
have the same "mid-flow reply should not derail" problem.

## 6. A time format nobody explicitly planned for

**Symptom**: confirming a booking with "yes, for 1030 am" silently failed
and the assistant asked for a date again from scratch, even though a date
had already been given.

**Diagnosis**: the time-parsing code only handled `HH:MM AM/PM` (needs a
colon) or a bare hour like `10 AM`. A 4-digit spoken time with no
separator, "1030," matched neither pattern. The bare-hour regex partially
matched and tried to parse "30" as an hour, which is invalid, and the
function returned nothing without raising a visible error.

**Fix**: added a third parsing tier specifically for 3 and 4-digit
times, splitting the digits into hour and minute based on length. Found
through live voice testing, not by planning for it up front, which is
exactly why this document exists.

## 7. Whisper's fastest model trades accuracy for speed

**Symptom**: during a live booking conversation, several consecutive
attempts to say "ten am" were transcribed as "Then a.m.", "Benim.", and
"Then, I am..." before one attempt finally transcribed correctly.

**Diagnosis**: this is not a bug, it is the real tradeoff of using
`ggml-tiny.en.bin`, the fastest and smallest Whisper model, chosen
specifically to keep end-to-end latency low. The system's state handling
worked correctly throughout, since the assistant kept re-asking for a
valid time instead of losing the conversation.

**Fix**: none needed at the state-management level, the retry behavior was
already correct. This is documented here as an honest limitation: a faster
model means more transcription noise, and a production system would need
to weigh that tradeoff explicitly rather than just picking the fastest
option by default.

## 8. A shared debug session revealed a stale dependency assumption

**Symptom**: cloning a voice locally worked from the command line but
crashed with a native library error when called through the API.

**Diagnosis**: `torchcodec`, a dependency pulled in by a newer version of
PyTorch, required system-level FFmpeg libraries at specific major versions
that did not match what was installed via Homebrew.

**Fix**: downgraded PyTorch below the version threshold that requires
`torchcodec` at all, sidestepping the native library mismatch entirely
rather than trying to match FFmpeg versions exactly. Documented here
because it is a good example of choosing the simpler fix over the
technically "correct" one when both solve the problem.

## QA cycle findings (11 Oct 2026)

A full QA pass ran three sweeps against the system: malformed and adversarial
inputs at the API boundary, flow level defect hypotheses through the real
pipeline, and HTTP level concurrency, rate limiting and cross service checks
against the running docker stack. Ten defects were confirmed and fixed, each
with a regression test in python-agents/tests/test_qa_regressions.py:

1. Safety blocklist evasion (high). Invisible characters and letter spacing
   ("diag\u200bnose", "d i a g n o s e") bypassed the input patterns and
   reached the FAQ layer. Fix: both safety layers now also check a squeezed
   copy of the text (whitespace and invisible characters removed) against a
   conservative list of high confidence clinical literals, chosen to stay
   false positive free. Emergency phrases got the same treatment, so a spaced
   out "c h e s t p a i n" now reaches the emergency path.
2. False positive found by the evasion fix (medium): the old
   "how much .* (take|dose)" pattern blocked "how much does it cost to take
   the bus". Tightened in both layers to require an intent word
   (should/can/could plus a pronoun).
3. Unknown clinic id crashed the endpoint (high): a request with
   clinic_id "does-not-exist" raised FileNotFoundError as an unhandled 500.
   Fix: fall back to the default clinic, log unknown_clinic_requested for the
   dashboard. Non string clinic ids get a structured 422 from request
   validation, which is correct.
4. Session state bled across tenants (high): two clinics sharing a session id
   inherited each other's pending flows because sessions were keyed only by
   session id. Fix: session keys are now clinic_id prefixed.
5. Rescheduling double booked an occupied slot (high): the reschedule
   continuation booked the requested new time without rechecking
   availability, so a slot taken between listing and confirming got two
   appointments. Fix: availability is verified at confirm time.
6. The word "no" was recorded as a patient name (medium): answering a name
   question with no/yes/ok created waitlist and refill records named "no".
   Fix: yes/no answers in name questions decline the flow politely and log
   nothing.
7. Intake body areas matched by substring (medium): "my heart hurts" recorded
   the body area "ear" and "the fire alarm scared me" recorded "arm". Fix:
   word boundary matching.
8. Impossible dates reached the calendar (medium): "2031-13-45" passed the
   date shape regex and failed inside the calendar call with a misleading
   "trouble checking the calendar" reply. Fix: extract_date validates the
   date and asks again.
9. /ready reported the FAQ service as 404 (medium): the health URL was
   derived from FAQ_BACKEND_URL by cutting the last path segment, turning
   /api/text-query into /api/api/health. The same bug silently broke the
   hybrid router classify URL. Fix: strip the known suffix exactly.
10. /ready required Google libraries even in fake calendar mode (medium):
    the calendar readiness check constructed the Google client directly, so
    the docker image without google-api-python-client reported degraded
    forever. Fix: /ready asks the configured scheduling adapter for a health
    check; each adapter implements its own cheap probe.

Not reproducible / accepted: a handful of connection resets when 30 requests
hit the agents container in the same second as it was starting (startup
transient, not reproducible after warm up); request bodies are not size
limited at the application layer (deployment concern, documented in Known
Limitations territory); homoglyph substitutions (Cyrillic letters) still
bypass the blocklist, which needs script normalization and is noted as a
future hardening item.
