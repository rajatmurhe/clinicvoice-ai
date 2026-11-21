# Call the Clinic: inbound telephone pilot

ClinicVoice now has an optional Twilio inbound-call adapter on the Python service. It uses turn-by-turn speech recognition and TwiML speech playback, not continuous full-duplex audio. No real calls have been placed as part of local development.

## Working path

A signed incoming webhook returns a keypad consent/language menu (1 English, 2 Hindi, 3 Marathi). After consent, the assistant collects a test patient name, the reason for visiting in the patient's own words, and duration. It reads these back; yes confirms, no restarts the reason/duration collection. Patients can skip symptom collection. The confirmed intake is available on the authenticated Python staff dashboard.

Booking reuses `main.process_query` and the existing agent handlers/session dictionary. This telephone adapter currently uses that shared deterministic orchestration entry point; it does not run through the optional LangGraph entry point. The chosen slot is read back and an explicit yes is required before the booking handler writes the appointment. A successful booking is stored with its returned event ID and ends the call. Calendar failures never produce a successful-booking card. Browser calls continue to use their existing path.

Every speech turn goes through the existing emergency and medical-advice filters, including corrections and confirmations. These are limited phrase checks, not clinical triage. No flag means no conclusion about whether waiting is safe. Safety escalation ends the call with localized guidance; it does not contact emergency services or promise a staff notification. No diagnosis, treatment recommendation, or risk classification is generated.

## Configure on the Python service

Install `requirements-prod.txt` (now includes Twilio). Set:

- `CLINICVOICE_PHONE_ENABLED=true`
- `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` from your own provider account
- `TWILIO_PUBLIC_URL=https://<public-python-service-origin>` with no path
- Existing service/admin credentials and clinic/calendar configuration remain required.

Configure the voice-enabled number's incoming-call webhook as **POST** to `https://<public-python-service-origin>/voice/twilio`. Use the Python service URL, not the Node gateway. For local provider testing, use a public HTTPS tunnel to Python and set the exact tunnel origin in TWILIO_PUBLIC_URL. Never disable signature verification.

Twilio speech recognition is configured with each selected locale (`en-IN`, `hi-IN`, `mr-IN`) and the `default` speech model. Configure a supported voice for each locale in Twilio's Text-to-Speech language mapping, or supply `TWILIO_VOICE_EN`, `TWILIO_VOICE_HI`, `TWILIO_VOICE_MR` overrides using provider-qualified identifiers. Verify voice/model availability in your account before announcing support. See https://www.twilio.com/docs/voice/twiml/gather and https://www.twilio.com/docs/voice/twiml/say/text-speech. Mixed-language recognition, local accents and actual telephone audio quality require recorded real-call tests; unit tests only cover transcribed examples.

This adapter does not acquire a number or verify Indian number availability/eligibility. Provider account requirements and telephone/STT/TTS charges must be checked before activation. No SMS, reminder, missed-call callback, live transfer, or outbound calling is implemented.

## Staff and frontend

Python `/dashboard/` now includes telephone intake records. `/api/dashboard/phone-calls` requires the existing admin credentials. Draft symptoms are not displayed as confirmed. The dashboard distinguishes intake confirmation, booking confirmation, and safety escalation. It does not claim a clinician has seen a record.

After testing a real call successfully, set `CLINICVOICE_PUBLIC_PHONE_NUMBER` to the verified E.164 number and `CLINICVOICE_PHONE_VERIFIED=true` on the Node gateway. The browser then shows a `tel:` link. Until then it explicitly says the number is not connected.

## Persistence, retries and limitations

`phone.sqlite` in `CLINICVOICE_DATA_DIR` stores call state, patient-reported text and response metadata. Mount persistent storage for restart survival; ephemeral hosting loses this data. Caller phone numbers and audio recordings are not stored by this adapter. The provider processes speech; review its data handling separately. Consent is requested before intake. Automated deletion is not implemented: use only synthetic information for this pilot and delete pilot records under the operator's retention policy.

SQLite serializes phone turns and cached responses prevent ordinary webhook retries from executing bookings twice. This is not an exactly-once guarantee across process crashes between a calendar write and the local transaction commit. Real-clinic use needs calendar-level idempotency, authenticated patient identities, deletion/retention controls and clinician-reviewed escalation wording. The current name intake is not identity verification.

Calls end after three consecutive empty speech turns or at the 60-turn limit. The signed webhook fails closed when disabled or misconfigured. Low reported speech confidence triggers a repeat request. Deploy on a responsive service: cold starts or slow FAQ calls can exceed a telephone provider's webhook timeout; free sleeping hosting is not a validated telephone production setup.

## Validation

`python -m pytest python-agents/tests/test_telephony.py -q` exercises signed HTTP webhooks, localized intake, corrections, explicit booking confirmation, retry protection, safety escalation, silence, authorization, and failure modes without provider calls or charges. Test a genuine inbound call in all enabled languages before setting the verified flag.

### Current Twilio trial limits

Twilio's current trial uses a guided Voice experience and may supply shared trial numbers rather than a dedicated number visible in the IncomingPhoneNumbers API. A zero-length number list is not proof the Voice trial is unavailable. The operator must enable the inbound Custom scenario in the console. Custom Say/Gather TwiML is supported, but the documented trial caps action/redirect chains at 10 hops and webhook fetching at 5 seconds. The shortest booking journey fits; repeated corrections can exceed that cap. Test this before a demonstration and do not promise long conversations on the trial. See https://www.twilio.com/docs/usage/trials/try-out-voice.
