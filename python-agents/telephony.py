"""Signed Twilio inbound webhooks. No outbound calls or recordings are created."""
import os
import math
import re
from urllib.parse import parse_qsl, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

import phone_workflow

router = APIRouter()
LANGUAGES = {'en': 'en-IN', 'hi': 'hi-IN', 'mr': 'mr-IN'}


def enabled():
    base = urlsplit(os.environ.get('TWILIO_PUBLIC_URL', ''))
    return (os.environ.get('CLINICVOICE_PHONE_ENABLED') == 'true'
            and bool(os.environ.get('TWILIO_AUTH_TOKEN'))
            and bool(re.fullmatch(r'AC[0-9a-fA-F]{32}', os.environ.get('TWILIO_ACCOUNT_SID', '')))
            and base.scheme == 'https' and bool(base.netloc)
            and not base.path.strip('/') and not base.query and not base.fragment)


def twiml(result):
    response = VoiceResponse()
    language = result.get('language', 'en')
    attrs = {'language': LANGUAGES[language]}
    # Map all three locales to tested voices in the Twilio console, or set overrides.
    voice = os.environ.get('TWILIO_VOICE_' + language.upper())
    if voice:
        attrs['voice'] = voice
    if result['mode'] == 'end':
        response.say(result['response'], **attrs)
        response.hangup()
    else:
        gather = response.gather(
            input='dtmf' if result['mode'] == 'language' else 'speech',
            action=f"/voice/twilio?turn={result['next_turn']}", method='POST',
            timeout=8, action_on_empty_result=True,
            **({'num_digits': 1} if result['mode'] == 'language' else {
                'language': LANGUAGES[language], 'speech_model': 'default', 'speech_timeout': 'auto',
            }))
        gather.say(result['response'], **attrs)
        if result['mode'] == 'language':
            for lang, prompt in (
                ('hi', 'यह परीक्षण सेवा है। केवल काल्पनिक जानकारी दें। आपकी बातें लिखकर स्टाफ की समीक्षा के लिए सहेजी जाएँगी। सहमति देकर हिंदी में जारी रखने के लिए 2 दबाएँ। अन्यथा कॉल बंद करें।'),
                ('mr', 'ही चाचणी सेवा आहे. फक्त काल्पनिक माहिती द्या. तुमचे बोलणे मजकुरात साठवून कर्मचाऱ्यांना पाहता येईल. संमती देऊन मराठीत पुढे जाण्यासाठी 3 दाबा. अन्यथा कॉल बंद करा.'),
            ):
                menu_attrs = {'language': LANGUAGES[lang]}
                if os.environ.get('TWILIO_VOICE_' + lang.upper()):
                    menu_attrs['voice'] = os.environ['TWILIO_VOICE_' + lang.upper()]
                gather.say(prompt, **menu_attrs)
    return str(response)


def run_agent(query, state):
    from main import QueryRequest, process_query
    import time
    session = state.setdefault('agent_session', {})
    session.update(channel='phone', clinic_id='default', language=state['language'], patient_name=state.get('patient_name'))
    return process_query(QueryRequest(query=query, language=state['language']), session, time.time())


@router.post('/voice/twilio')
async def voice(request: Request):
    if not enabled():
        return JSONResponse({'error': 'Telephone pilot is not configured.'}, status_code=503)
    if not request.headers.get('content-type', '').startswith('application/x-www-form-urlencoded'):
        return JSONResponse({'error': 'Form request required.'}, status_code=415)
    raw = b''
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > 16000:
            return JSONResponse({'error': 'Request too large.'}, status_code=413)
    pairs = parse_qsl(raw.decode('utf-8', errors='replace'), keep_blank_values=True)
    form = dict(pairs)
    if len(form) != len(pairs):
        return JSONResponse({'error': 'Duplicate form fields.'}, status_code=400)
    # Use the explicitly configured public URL, never an untrusted Host header.
    public_url = os.environ['TWILIO_PUBLIC_URL'].rstrip('/') + request.url.path
    if request.url.query:
        public_url += '?' + request.url.query
    if not RequestValidator(os.environ['TWILIO_AUTH_TOKEN']).validate(public_url, form, request.headers.get('x-twilio-signature', '')):
        return JSONResponse({'error': 'Invalid webhook signature.'}, status_code=403)
    if form.get('AccountSid') != os.environ['TWILIO_ACCOUNT_SID'] or not re.fullmatch(r'CA[0-9a-fA-F]{32}', form.get('CallSid', '')):
        return JSONResponse({'error': 'Invalid call identity.'}, status_code=403)
    try:
        number = int(request.query_params.get('turn', '0'))
        if number < 0 or number > 60:
            raise ValueError()
        query = form.get('SpeechResult', '').strip()
        if len(query) > 2000:
            raise ValueError()
        confidence = float(form['Confidence']) if form.get('Confidence') else None
        if confidence is not None and (not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError()
        result = await run_in_threadpool(phone_workflow.turn, form['CallSid'], number, query, form.get('Digits', ''), confidence, run_agent)
        return Response(twiml(result), media_type='application/xml', headers={'Cache-Control': 'no-store'})
    except ValueError:
        return JSONResponse({'error': 'Invalid or out-of-order turn.'}, status_code=400)
    except Exception:
        # Do not disclose patient text, provider details, or imply an action succeeded.
        reply = VoiceResponse()
        reply.say('The assistant is unavailable. Please contact reception directly. No booking is confirmed by this message.')
        reply.hangup()
        return Response(str(reply), media_type='application/xml')
