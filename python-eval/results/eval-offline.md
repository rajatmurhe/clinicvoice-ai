# ClinicVoice AI eval results (offline mode)

Run date: 2026-10-09T15:41:37 · commit: 3536f07 · no network, no LLM calls, fake calendar

| Category | Metric | Value |
|---|---|---|
| FAQ | hit at 1 | 91.2 |
| FAQ | decision accuracy | 98.1 |
| Booking | flow pass rate | 100.0 |
| Refills | flow pass rate | 100.0 |
| Insurance | accuracy | 100.0 |
| Escalation | accuracy | 100.0 |
| Off scope / unsafe | safety catch rate | 100.0 |
| Off scope / unsafe | false positive rate | 0.0 |
| Hindi | pass rate | 100.0 |
| Marathi | pass rate | 100.0 |
| Routing | accuracy (annotated single turns) | 100.0 |

## Failures (3)

- **faq-01** (faq(node)): decision fallback != expected answer
- **faq-07** (faq(node)): hit@1 miss: top_faq_id=12 expected=7
- **faq-21** (faq(node)): hit@1 miss: top_faq_id=13 expected=21
