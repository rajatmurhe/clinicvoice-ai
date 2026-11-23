import { useState, useRef, useEffect } from 'react';
import './App.css';

// The browser talks only to the gateway; no service key is bundled here.
const API_URL = import.meta.env.VITE_API_URL || '';
let sessionPromise;
async function apiFetch(url, options) {
  async function session() {
    const res = await fetch(API_URL + '/api/session', {method: 'POST', signal: AbortSignal.timeout(15000)});
    if (!res.ok) throw new Error('Unable to start the demo. Please try again shortly.');
    return (await res.json()).token;
  }
  if (!sessionPromise) sessionPromise = session().catch(e => { sessionPromise = null; throw e; });
  const send = async () => fetch(url, {...options, headers: {...options.headers, Authorization: 'Bearer ' + await sessionPromise}});
  let res = await send();
  if (res.status === 401) { sessionPromise = session().catch(e => {sessionPromise = null; throw e;}); res = await send(); }
  return res;
}

function MicIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="9" y="2" width="6" height="12" rx="3" stroke="currentColor" strokeWidth="1.6"/>
      <path d="M5 11a7 7 0 0014 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
      <path d="M12 18v3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
      <path d="M9 21h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2l8 3v6c0 5-3.5 8.5-8 11-4.5-2.5-8-6-8-11V5l8-3z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/>
      <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function SendIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 12h13m0 0-5.5-5.5M17 12l-5.5 5.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function UserIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.8"/>
      <path d="M4 20c0-4.4 3.6-7 8-7s8 2.6 8 7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  );
}

function BotIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="8" width="16" height="11" rx="3" stroke="currentColor" strokeWidth="1.8"/>
      <path d="M12 8V4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <circle cx="12" cy="3" r="1.3" fill="currentColor"/>
      <circle cx="9" cy="13.5" r="1.3" fill="currentColor"/>
      <circle cx="15" cy="13.5" r="1.3" fill="currentColor"/>
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.7"/>
      <path d="M3 10h18M8 3v4M16 3v4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7"/>
      <path d="M12 7v5l3.5 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    </svg>
  );
}

function CardIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="6" width="18" height="12" rx="2" stroke="currentColor" strokeWidth="1.7"/>
      <path d="M3 10h18" stroke="currentColor" strokeWidth="1.7"/>
    </svg>
  );
}

const CAPABILITIES = [
  { icon: CalendarIcon, label: 'Book in English', example: '"Book an appointment tomorrow"', query: 'I want to book an appointment tomorrow' },
  { icon: CardIcon, label: 'हिन्दी में बुक करें', example: 'कल अपॉइंटमेंट बुक करें', query: 'कल अपॉइंटमेंट बुक करें', language: 'hi' },
  { icon: ClockIcon, label: 'मराठीत बुक करा', example: 'उद्या अपॉइंटमेंट बुक करा', query: 'उद्या अपॉइंटमेंट बुक करा', language: 'mr' },
];

const CLINICS = [
  { id: 'default', label: 'General Clinic' },
  { id: 'smilecare', label: 'SmileCare Dental' },
];

function App() {
  const [isListening, setIsListening] = useState(false);
  const [loading, setLoading] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [openingMic, setOpeningMic] = useState(false);
  const micPendingRef = useRef(false);
  const [coldStart, setColdStart] = useState(false);
  const [error, setError] = useState('');
  const [phoneNumber, setPhoneNumber] = useState(null);
  useEffect(() => {
    let active = true;
    fetch(API_URL + '/api/phone-info').then(r => r.ok ? r.json() : null).then(data => {
      if (active && data?.available && /^\+[1-9]\d{7,14}$/.test(data.number)) setPhoneNumber(data.number);
    }).catch(() => {});
    return () => { active = false; };
  }, []);
  const [messages, setMessages] = useState([]);

  const [inputValue, setInputValue] = useState('');
  const [clinicId, setClinicId] = useState('default');

  const recognitionRef = useRef(null);
  const conversationEndRef = useRef(null);
  const [initialSessionId] = useState(() => crypto.randomUUID());
  const sessionIdRef = useRef(initialSessionId);
  const audioPlayerRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef(null);
  const speakingRef = useRef(false);
  const [speaking, setSpeaking] = useState(false);
  const conversationRef = useRef(null);
  const clinicRef = useRef('default');
  const coldStartTimerRef = useRef(null);

  const [lastAssistantResponse, setLastAssistantResponse] = useState('');
  const playbackRef = useRef(0);
  const finishAudioRef = useRef(null);

  const LANGS = [
    { id: 'en', label: 'English' },
    { id: 'hi', label: 'हिन्दी', lang: 'hi' },
    { id: 'mr', label: 'मराठी', lang: 'mr' },
  ];
  const [lang, setLang] = useState('en');
  const languageRef = useRef('en');

  const switchClinic = (id) => {
    if (id === clinicRef.current) return;
    stopSpeaking();
    clinicRef.current = id;
    setClinicId(id);
    sessionIdRef.current = crypto.randomUUID();
    setMessages([]);
    setLastAssistantResponse('');
    setError('');
  };

  const switchLang = (id) => {
    stopSpeaking();
    setLang(id);
    languageRef.current = id;
    sessionIdRef.current = crypto.randomUUID();
    setMessages([]);
    setLastAssistantResponse('');
    setError('');
  };

  const replayLastResponse = () => {
    if (lastAssistantResponse) {
      stopSpeaking();
      speakReply(lastAssistantResponse, null, null);
    }
  };

  useEffect(() => {
    // Scroll inside the transcript card only, so the page itself stays put.
    const box = conversationRef.current;
    if (box) box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => () => {
    clearTimeout(coldStartTimerRef.current);
    recognitionRef.current?.abort();
    playbackRef.current += 1;
    audioPlayerRef.current?.pause();
    finishAudioRef.current?.();
    window.speechSynthesis?.cancel();
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.onstop = null;
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
    }
  }, []);

  const formatTime = () => {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const stopSpeaking = () => {
    // Barge in: tapping the mic must stop playback at once.
    speakingRef.current = false;
    setSpeaking(false);
    playbackRef.current += 1;
    finishAudioRef.current?.();
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause();
      audioPlayerRef.current.currentTime = 0;
    }
    if (window.speechSynthesis && window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
    }
  };

  const splitSentences = (text) => {
    const parts = (text || '').split(/(?<=[.!?।])\s+/).filter(Boolean);
    return parts.length ? parts : [text];
  };

  const browserSpeak = (text, playback) => new Promise(resolve => {
    if (playback !== playbackRef.current || !window.speechSynthesis) return resolve();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = { en: 'en-US', hi: 'hi-IN', mr: 'mr-IN' }[languageRef.current];
    utterance.onend = resolve;
    utterance.onerror = resolve;
    finishAudioRef.current = resolve;
    window.speechSynthesis.speak(utterance);
  });

  const speakText = async (text, requestId, playback) => {
    // The hosted voice is English; use the selected browser voice for Hindi/Marathi.
    if (languageRef.current !== 'en') return browserSpeak(text, playback);
    try {
      const res = await apiFetch(API_URL + '/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId || '' },
        body: JSON.stringify({ text }), signal: AbortSignal.timeout(15000)
      });
      if (!res.ok) throw new Error('TTS failed');
      const blob = await res.blob();
      if (playback !== playbackRef.current) return;
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioPlayerRef.current = audio;
      try {
        await new Promise((resolve, reject) => {
          finishAudioRef.current = resolve;
          audio.onended = resolve;
          audio.onerror = reject;
          audio.play().catch(reject);
        });
      } finally {
        URL.revokeObjectURL(url);
      }
    } catch {
      await browserSpeak(text, playback);
    }
  };

  const speakReply = async (text, requestId) => {
    const playback = ++playbackRef.current;
    speakingRef.current = true;
    setSpeaking(true);
    for (const sentence of splitSentences(text)) {
      if (playback !== playbackRef.current) return;
      await speakText(sentence, requestId, playback);
    }
    if (playback === playbackRef.current) { speakingRef.current = false; setSpeaking(false); }
  };

  const startListening = () => {
    stopSpeaking();
    setError('');
    void startPushToTalk();
  };

  const startPushToTalk = async () => {
    if (micPendingRef.current) return;
    micPendingRef.current = true;
    setOpeningMic(true);
    let stream;
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error("This browser cannot record audio. Please type your question or open the app in Chrome or Safari.");
      }
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (e) => audioChunksRef.current.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        setIsListening(false);
        setLoading(true);
        setTranscribing(true);
        try {
          const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
          const reader = new FileReader();
          const dataUrl = await new Promise((resolve, reject) => {
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
          });
          const res = await apiFetch(API_URL + '/api/transcribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ audio: dataUrl, language: lang }),
            signal: AbortSignal.timeout(60000)
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || 'Transcription unavailable. Please type your question.');
          setTranscribing(false);
          if (data.text) {
            await sendQuery(data.text);
          } else {
            setError('Nothing heard. Please try again.');
            setLoading(false);
          }
        } catch (err) {
          setError(err.message || 'Transcription failed.');
          setLoading(false);
        } finally {
          setTranscribing(false);
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsListening(true);
    } catch (err) {
      stream?.getTracks().forEach(track => track.stop());
      setIsListening(false);
      setError('Microphone unavailable: ' + err.message);
    } finally {
      micPendingRef.current = false;
      setOpeningMic(false);
    }
  };

  const stopListening = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    } else if (recognitionRef.current) {
      recognitionRef.current.stop();
    } else {
      setIsListening(false);
    }
  };

  const onComposerSubmit = (e) => {
    e.preventDefault();
    const value = inputValue.trim();
    if (!value || loading || isListening || openingMic) return;
    setInputValue('');
    stopSpeaking();
    sendQuery(value);
  };

  const sendQuery = async (query, language = languageRef.current) => {
    setLoading(true);
    setColdStart(false);
    if (coldStartTimerRef.current) clearTimeout(coldStartTimerRef.current);
    coldStartTimerRef.current = setTimeout(() => setColdStart(true), 5000);
    const time = formatTime();
    // One id per turn flows through the agent service, the FAQ service and
    // every log line, so any answer can be traced end to end.
    const requestId = crypto.randomUUID();

    setMessages(function(prev) {
      return prev.concat([{ role: 'user', text: query, time: time }]);
    });

    try {
      const res = await apiFetch(API_URL + '/api/agent-query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Request-ID': requestId
        },
        body: JSON.stringify({ query: query, session_id: sessionIdRef.current, clinic_id: clinicRef.current, language }),
        signal: AbortSignal.timeout(90000)
      });

      if (res.status === 429) {
        throw new Error('You are sending messages too quickly. Please wait a moment and try again.');
      }

      if (!res.ok) {
        const failure = await res.json().catch(() => ({}));
        throw new Error(failure.error || 'The assistant is temporarily unavailable. Please try again.');
      }

      const data = await res.json();

      clearTimeout(coldStartTimerRef.current);
      coldStartTimerRef.current = null;
      setColdStart(false);
      setMessages(prev => prev.concat([
        { role: 'assistant', text: data.response, guardrail: data.guardrailTriggered, time: formatTime() }
      ]));
      setLastAssistantResponse(data.response);
      // Text stays usable if audio is blocked or the user interrupts playback.
      void speakReply(data.response, res.headers.get('X-Request-ID') || requestId);
    } catch (err) {
      setError(['TimeoutError', 'AbortError'].includes(err.name) ? 'The assistant took too long to respond. Please try again.' : err.message);
    } finally {
      if (coldStartTimerRef.current) { clearTimeout(coldStartTimerRef.current); coldStartTimerRef.current = null; }
      setColdStart(false);
      setLoading(false);
    }
  };

  const busy = loading || isListening || openingMic;
  const orbState = isListening ? 'listen' : loading ? 'think' : speaking ? 'speak' : '';
  const orbHint = openingMic ? 'Waiting for microphone permission' : isListening ? 'Recording · tap stop to send' : transcribing ? 'Transcribing your recording' : loading ? 'Thinking' : speaking ? 'Speaking · tap to interrupt' : 'Tap the orb to speak';
  const callState = isListening ? 'Listening' : loading ? 'Thinking' : speaking ? 'Speaking' : messages.length ? 'Ready' : 'Waiting for you';
  const activeClinic = CLINICS.find(c => c.id === clinicId)?.label;

  return (
    <div className="app-shell">
      <header className="nav">
        <div className="wrap nav-row">
          <div className="brand">Clinic<b>Voice</b> <span className="brand-ai">AI</span></div>
          <div className="nav-live" aria-label="Service status"><span className="live-dot"></span>Live demo</div>
          <div className="nav-right">
            <div className="seg dark" role="group" aria-label="Language">
              {LANGS.map(l => (
                <button key={l.id} className={lang === l.id ? 'on' : ''} onClick={() => switchLang(l.id)} lang={l.lang} disabled={busy} aria-pressed={lang === l.id}>{l.label}</button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="wrap">
            <div className="eyebrow">AI voice receptionist · English · हिन्दी · मराठी</div>
            <h1>The clinic front desk that <em>answers every call.</em></h1>
            <p className="tri">Ask a question. Book a visit. Request a refill.</p>
            <p className="sub">ClinicVoice listens, checks the clinic calendar and registry, and only changes an appointment after the patient is verified.</p>

            <div className="seg light clinic-seg" role="group" aria-label="Clinic (demo tenant)">
              {CLINICS.map(c => (
                <button key={c.id} className={clinicId === c.id ? 'on' : ''} onClick={() => switchClinic(c.id)} disabled={busy} aria-pressed={clinicId === c.id}>{c.label}</button>
              ))}
            </div>

            <div className="stage">
              <div className="orb-wrap">
                <span className="ring"></span><span className="ring"></span><span className="ring"></span>
                <div className={'orb ' + orbState}></div>
                <button
                  className={'orb-btn' + (isListening ? ' stop' : '')}
                  onClick={isListening ? stopListening : startListening}
                  disabled={loading || openingMic}
                  aria-label={isListening ? 'Stop recording' : 'Start recording'}
                >
                  {isListening ? <StopIcon /> : <MicIcon />}
                </button>
              </div>
              <span className="orb-label" role="status">{orbHint}</span>
            </div>
          </div>
        </section>

        <div className="strip">
          <div className="wrap">
            <span><ShieldIcon /> Verified before any calendar access</span>
            <span><CalendarIcon /> Books only open slots</span>
            <span><ClockIcon /> Safety filter on every reply</span>
            <span><CardIcon /> Synthetic demo data</span>
          </div>
        </div>

        {error && <div className="wrap"><div className="error-banner" role="alert">{error}</div></div>}

        <section className="sec wrap">
          <div className="head">
            <div className="kicker">Live conversation</div>
            <h2>Talk to <em>{activeClinic}</em></h2>
          </div>

          <div className="grid">
            <div className="call">
              <div className="top">
                <span className={'dot' + (busy || speaking ? ' on' : '')}></span>
                <span className="t">{callState}</span>
                <button className="replay" type="button" onClick={replayLastResponse} disabled={!lastAssistantResponse || busy} aria-label="Replay last answer" title="Replay last answer">↻ Replay</button>
              </div>

              <div className="conversation" ref={conversationRef}>
                {messages.length === 0 && !loading && (
                  <div className="empty-state">
                    <div className="empty-state-title">Ask a question to get started</div>
                    <div className="empty-state-sub">Tap the orb, speak, then tap stop to send. Or type below.</div>
                  </div>
                )}

                {messages.map((msg, i) => {
                  const isUser = msg.role === 'user';
                  const kind = isUser ? 'user' : msg.guardrail ? 'guardrail' : 'assistant';
                  return (
                    <div key={i} className={'ln ' + kind}>
                      <div className="who">
                        {isUser ? <UserIcon /> : msg.guardrail ? <ShieldIcon /> : <BotIcon />}
                        {isUser ? 'Patient' : 'ClinicVoice'}
                        <span className="time">{msg.time}</span>
                      </div>
                      {msg.guardrail && <div className="safety-tag"><ShieldIcon /> Blocked by the safety filter</div>}
                      <div className="text">{msg.text}</div>
                    </div>
                  );
                })}

                {loading && (
                  <div className="ln assistant">
                    <div className="who"><BotIcon /> ClinicVoice</div>
                    <div className="typing-indicator"><span></span><span></span><span></span></div>
                    {coldStart && (<div className="cold-start-hint" role="status">The assistant is taking longer than usual. Waiting for a response…</div>)}
                  </div>
                )}
                <div ref={conversationEndRef}></div>
              </div>

              <form className="composer" onSubmit={onComposerSubmit}>
                <input
                  className="composer-input"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="Or type a question…"
                  aria-label="Type your question"
                  disabled={busy}
                />
                <button className="btn primary" type="submit" disabled={busy || !inputValue.trim()} aria-label="Send question">
                  Send <SendIcon />
                </button>
              </form>
            </div>

            <aside className="side">
              <div className="work">
                <div className="top"><span className="t">Try asking</span></div>
                <div className="caps">
                  {CAPABILITIES.map((cap, i) => {
                    const Icon = cap.icon;
                    return (
                      <button className="cap" key={i} onClick={() => { const chosen = cap.language || 'en'; switchLang(chosen); sendQuery(cap.query, chosen); }} disabled={busy}>
                        <span className="cap-icon"><Icon /></span>
                        <span>
                          <span className="cap-label">{cap.label}</span>
                          <span className="cap-example">{cap.example}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="work">
                <div className="top"><span className="t">Call the clinic</span></div>
                <div className="phone">
                  {phoneNumber
                    ? <a className="phone-num" href={'tel:' + phoneNumber}>{phoneNumber}</a>
                    : <div className="phone-num muted">Telephone pilot · number not connected yet</div>}
                  <p>Describe your reason for a visit and confirm your details by voice. Synthetic test details only.</p>
                </div>
              </div>
            </aside>
          </div>
        </section>
      </main>

      <footer>
        <div className="wrap foot">
          <div className="brand dark-ink">Clinic<b>Voice</b> <span className="brand-ai">AI</span></div>
          <p>A software engineering demo, not a medical device. It does not diagnose, recommend treatment, or replace clinic staff.</p>
        </div>
      </footer>
    </div>
  );
}

export default App;
