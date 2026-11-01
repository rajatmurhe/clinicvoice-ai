"""Exercise the built UI and real gateway/agent processes without provider calls."""
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

with tempfile.TemporaryDirectory(prefix='clinicvoice-smoke-') as temp:
    gateway_port, agent_port = port(), port()
    base = f'http://127.0.0.1:{gateway_port}'
    env = {**os.environ, 'PORT': str(gateway_port), 'AGENT_INTERNAL_URL': f'http://127.0.0.1:{agent_port}',
           'FAQ_BACKEND_URL': base + '/api/text-query', 'CLINICVOICE_SERVICE_KEY': secrets.token_hex(32),
           'CLINICVOICE_ADMIN_TOKEN': secrets.token_hex(32), 'CLINICVOICE_ALLOWED_ORIGINS': base,
           'CLINICVOICE_DEMO_MODE': 'true', 'CLINICVOICE_DATA_DIR': temp,
           'CLINICVOICE_PATIENT_REGISTRY': str(ROOT / 'python-agents/demo-patients.json'),
           'CLINICVOICE_CALENDAR_MODE': 'fake', 'VOICE_CLONING_ENABLED': 'false'}
    env.pop('GROQ_API_KEY', None); env.pop('GEMINI_API_KEY', None)
    with open(Path(temp) / 'services.log', 'w+') as log:
        processes = [subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--port', str(agent_port)], cwd=ROOT/'python-agents', env=env, stdout=log, stderr=log),
                     subprocess.Popen([shutil.which('node'), 'server-cloud.js'], cwd=ROOT/'backend', env=env, stdout=log, stderr=log)]
        try:
            for endpoint in [base+'/api/health', f'http://127.0.0.1:{agent_port}/health']:
                for _ in range(100):
                    try:
                        if requests.get(endpoint, timeout=1).ok: break
                    except requests.RequestException: pass
                    time.sleep(.1)
                else: raise AssertionError('Service did not start')
            assert '<div id="root">' in requests.get(base, timeout=2).text
            assert requests.post(base+'/api/tts', json={'text':'hello'}, timeout=2).status_code == 401
            assert requests.get(f'http://127.0.0.1:{agent_port}/api/dashboard/stats', timeout=2).status_code == 401
            token = requests.post(base+'/api/session', headers={'Origin':base}, timeout=2).json()['token']
            def ask(q, session='smoke', language='en'):
                r = requests.post(base+'/api/agent-query', headers={'Authorization':'Bearer '+token}, json={'query':q,'session_id':session,'language':language}, timeout=5)
                assert r.ok, r.text
                return r.json()['response']
            assert '09:00 AM' in ask('I have a fever, can I book an appointment tomorrow?')
            assert 'booked' in ask('09:00 AM').lower()
            assert 'name' in ask('When is my appointment?').lower()
            assert 'registered' in ask('My name is Demo Patient').lower()
            assert 'appointment is on' in ask('DEMO-12345').lower()
            ask('Reschedule my appointment'); ask('My name is Demo Patient')
            assert 'new date' in ask('DEMO-12345').lower()
            moved = ask('tomorrow at 10:00 AM')
            assert 'moved' in moved.lower(), moved
            ask('Cancel my appointment'); ask('My name is Demo Patient')
            assert 'cancelled' in ask('DEMO-12345').lower()
            assert '09:00 AM' in ask('कल अपॉइंटमेंट बुक करें', 'hi', 'hi')
            assert '09:00 AM' in ask('उद्या अपॉइंटमेंट बुक करा', 'mr', 'mr')
            print('PASS: UI, gateway authentication, dashboard protection, booking, verified lookup, reschedule, cancellation, Hindi and Marathi requests.')
        except Exception:
            log.flush(); log.seek(0); print(log.read()[-6000:]); raise
        finally:
            for p in processes: p.terminate()
            for p in processes: p.wait(timeout=10)
