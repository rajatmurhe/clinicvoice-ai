# ClinicVoice AI eval results (live mode)

Run date: 2026-10-09T15:48:06 · commit: b06912e · FAQ service: https://clinicvoice-ai.onrender.com · agent service: https://clinicvoice-ai-agents.onrender.com

| Stage | p50 (ms) | p95 (ms) |
|---|---|---|
| LLM answer (retrieval plus Groq) | 1017 | 19678 |
| TTS full reply | 3276 | 3658 |
| Total agent turn | 1525 | 19705 |
| Time to first audio, before streaming | 3401 | 3876 |
| Time to first audio, sentence streaming | 2057 | 2628 |

Speech to text runs in the browser on the cloud variant, so STT latency is client side and not measured here. Time to first audio compares synthesizing the whole reply (before) with synthesizing only the first sentence, which the streaming frontend plays immediately (after).