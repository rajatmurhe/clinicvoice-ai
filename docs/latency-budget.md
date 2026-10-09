# Voice Latency Budget

Budgets for one voice turn on the cloud deployment, stage by stage. The
budgets are targets set before measuring; the p50 and p95 columns come from
live runs against the deployed Render services (results/eval-live.md, run date
and commit recorded with every run). Speech to text runs in the browser on the
cloud variant, so its latency is not measured server side.

| Stage | Budget | What it covers |
|---|---|---|
| Speech to text | 800 ms | Browser Web Speech API (client side, not measured) or the /api/transcribe fallback |
| Retrieval | 50 ms | SQLite FAQ index, hybrid BM25 plus trigrams |
| LLM answer | 1500 ms | Guardrail pre-decisions plus one Groq call, 1 to 2 sentences |
| TTS first audio | 900 ms | First sentence synthesized and starting to play |
| Total turn | 3000 ms | Mic tap to first word heard |

## Streaming and time to first audio

The reply is spoken sentence by sentence: the first sentence is synthesized
and starts playing while the rest is still being fetched, instead of waiting
for the whole reply's audio. Measured on the deployed service (see
eval-live.md for the current numbers):

- before: time to first audio equals the TTS latency of the whole reply
- after: time to first audio equals the TTS latency of the first sentence only

## Barge in

Tapping the mic pauses the audio player immediately and cancels any queued
browser speech, so the caller never has to wait out a long answer. A reply
that has been synthesized but not yet played is dropped if the caller barges
in first.

## Push to talk fallback

The browser Speech API fails on Safari and Brave. When it is missing the
frontend switches to a push to talk mode: hold the mic, record with
MediaRecorder, send the clip to /api/transcribe (Groq whisper-large-v3-turbo
server side), and the transcript flows into the same agent pipeline.

## Emergency path

Emergency phrasings (chest pain, cannot breathe, overdose, and the Hindi and
Marathi equivalents) bypass every flow, deliver a dedicated contact local
emergency services message in the caller's language, clear any pending state
and log the call with intent emergency for human review. See RED_TEAM.md and
safety.py.
