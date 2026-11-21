# Launch regression evidence

These reports were generated on 1 November 2026 from the launch-readiness working tree based on commit 25c8ae8. The commit field in the generated reports identifies that base, not a clean checkout of the final implementation.

Validation completed locally:

- Python: 225 passed, 1 skipped.
- Node: 62 passed.
- Frontend: ESLint and production build passed.
- Offline evaluation: existing thresholds passed; FAQ hit-at-1 91.2%, decision accuracy 98.1%.
- Nine new administrative-request cases in English, Hindi and Marathi passed.
- Red team: previous caught cases preserved, no Python/Node disagreement; six documented first-layer gaps remain.
- Real-process smoke check: built UI, authentication, booking, verified lookup, reschedule, cancellation, Hindi/Marathi slot requests passed.

Provider calls in Node tests are mocked. The smoke test does not use provider keys. Live microphone, paid transcription/TTS, Docker image execution, and hosted deployment were not verified in this run. Docker is unavailable on this host. These results do not establish production readiness for patient data.
