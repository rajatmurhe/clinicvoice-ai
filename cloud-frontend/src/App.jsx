import { useState, useRef, useEffect } from 'react';
import './App.css';

// Point at your local stack with VITE_API_URL / VITE_AGENT_URL when developing;
// defaults are the deployed services.
const API_URL = import.meta.env.VITE_API_URL || 'https://clinicvoice-ai.onrender.com';
const AGENT_URL = import.meta.env.VITE_AGENT_URL || 'https://clinicvoice-ai-agents.onrender.com';

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

function ClinicIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 13v-1a8 8 0 0116 0v1" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
      <rect x="3" y="13" width="4" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.6"/>
      <rect x="17" y="13" width="4" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.6"/>
      <path d="M19 19v1a3 3 0 01-3 3h-3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
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
  { icon: CalendarIcon, label: 'Ask about appointments', example: '"What are your opening hours?"', query: 'What are your opening hours?' },
  { icon: CardIcon, label: 'Check accepted insurance', example: '"Do you accept Aetna?"', query: 'Do you accept Aetna?' },
  { icon: ClockIcon, label: 'General clinic questions', example: '"Is there parking?"', query: 'Is there parking?' },
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
    conversationEndRef.current?.scrollIntoView({ behavior: 'smooth' });
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
    utterance.lang = { en: 'en-US', hi: 'hi-IN', mr: 'mr-IN' }[lang];
    utterance.onend = resolve;
    utterance.onerror = resolve;
    finishAudioRef.current = resolve;
    window.speechSynthesis.speak(utterance);
  });

  const speakText = async (text, requestId, playback) => {
    // The hosted voice is English; use the selected browser voice for Hindi/Marathi.
    if (lang !== 'en') return browserSpeak(text, playback);
    try {
      const res = await fetch(API_URL + '/api/tts', {
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
    for (const sentence of splitSentences(text)) {
      if (playback !== playbackRef.current) return;
      await speakText(sentence, requestId, playback);
    }
    if (playback === playbackRef.current) speakingRef.current = false;
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
          const res = await fetch(API_URL + '/api/transcribe', {
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

  const sendQuery = async (query) => {
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
      const res = await fetch(AGENT_URL + '/api/agent-query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Request-ID': requestId
        },
        body: JSON.stringify({ query: query, session_id: sessionIdRef.current, clinic_id: clinicRef.current, language: lang }),
        signal: AbortSignal.timeout(90000)
      });

      if (res.status === 429) {
        throw new Error('You are sending messages too quickly. Please wait a moment and try again.');
      }

      if (!res.ok) {
        throw new Error('Server error: ' + res.status);
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
      setError(err.message);
    } finally {
      if (coldStartTimerRef.current) { clearTimeout(coldStartTimerRef.current); coldStartTimerRef.current = null; }
      setColdStart(false);
      setLoading(false);
    }
  };

  const orbState = isListening ? 'listening' : loading ? 'thinking' : '';
  const orbHint = openingMic ? 'Waiting for microphone permission…' : isListening ? 'Recording… Tap Stop to send' : transcribing ? 'Transcribing your recording…' : loading ? 'Thinking...' : 'Tap to record';

  return (
    <div className="app-shell">
      <div className="header">
        <div className="brand">
          <div className="brand-icon"><ClinicIcon /></div>
          <div className="brand-text">
            <h1>ClinicVoice AI</h1>
            <div className="status-row">
              <span className="status-dot"></span>
              <span className="status-text">Live</span>
            </div>
          </div>
        </div>

        <div className="clinic-switch" role="group" aria-label="Language">
          {LANGS.map(function(l) {
            return (
              <button
                key={l.id}
                className={'clinic-pill' + (lang === l.id ? ' active' : '')}
                onClick={() => switchLang(l.id)}
                lang={l.lang}
                disabled={loading || isListening || openingMic}
                aria-pressed={lang === l.id}
              >
                {l.label}
              </button>
            );
          })}
        </div>
        <div className="clinic-switch" role="group" aria-label="Clinic (demo tenant)">
          {CLINICS.map(function(c) {
            return (
              <button
                key={c.id}
                className={'clinic-pill' + (clinicId === c.id ? ' active' : '')}
                onClick={() => switchClinic(c.id)}
                disabled={loading || isListening || openingMic}
                aria-pressed={clinicId === c.id}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="main-layout">
        <div className="chat-column">
          <div className="voice-stage">
            <div className={'orb-wrap ' + orbState}>
              <div className="orb-ring"></div>
              <button
                className={'orb-btn ' + (isListening ? 'recording' : loading ? 'thinking' : '')}
                onClick={isListening ? stopListening : startListening}
                disabled={loading || openingMic}
                aria-label={isListening ? 'Stop recording' : 'Start recording'}
              >
                {isListening ? <StopIcon /> : <MicIcon />}
              </button>
            </div>
            <span className="voice-hint">{orbHint}</span>
          </div>

          {messages.length === 0 && !loading && (
            <div className="empty-state">
              <div className="empty-state-title">Ask a question to get started</div>
              <div className="empty-state-sub">Tap the mic, speak, then tap Stop to send. You can also type a question below.</div>
            </div>
          )}

          <div className="conversation">
            {messages.map(function(msg, i) {
              const isUser = msg.role === 'user';
              const bubbleClass = isUser ? 'bubble user' : msg.guardrail ? 'bubble guardrail' : 'bubble assistant';
              const avatarClass = isUser ? 'avatar user' : msg.guardrail ? 'avatar guardrail' : 'avatar assistant';

              return (
                <div key={i} className={'message-group ' + msg.role}>
                  <div className={avatarClass}>
                    {isUser ? <UserIcon /> : msg.guardrail ? <ShieldIcon /> : <BotIcon />}
                  </div>
                  <div className="bubble-wrap">
                    {msg.guardrail && (
                      <div className="safety-tag"><ShieldIcon /> Blocked by the safety filter</div>
                    )}
                    <div className={bubbleClass}>{msg.text}</div>
                    <div className="timestamp">{msg.time}</div>
                  </div>
                </div>
              );
            })}

            {loading && (
              <div className="message-group assistant">
                <div className="avatar assistant"><BotIcon /></div>
                <div className="bubble-wrap">
                  <div className="typing-indicator">
                    <div className="typing-dot"></div>
                    <div className="typing-dot"></div>
                    <div className="typing-dot"></div>
                  </div>
                  {coldStart && (<div className="cold-start-hint" role="status">The assistant is taking longer than usual. Waiting for a response…</div>)}
                </div>
              </div>
            )}

            <div ref={conversationEndRef}></div>
          </div>

          <form className="composer" onSubmit={onComposerSubmit}>
            <button className="composer-send composer-replay" type="button" onClick={replayLastResponse} disabled={!lastAssistantResponse || loading || isListening || openingMic} aria-label="Replay last answer" title="Replay last answer">↻</button>
            <input
              className="composer-input"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Or type a question…"
              aria-label="Type your question"
              disabled={loading || openingMic || isListening}
            />
            <button className="composer-send" type="submit" disabled={loading || isListening || openingMic || !inputValue.trim()} aria-label="Send question">
              <SendIcon />
            </button>
          </form>
        </div>

        <div className="capabilities-panel">
          <div className="capabilities-title">What I can help with</div>
          <div className="capabilities-sub">Try asking about any of these.</div>
          <div className="capabilities-list">
            {CAPABILITIES.map(function(cap, i) {
              const Icon = cap.icon;
              return (
                <button className="capability-item" key={i} onClick={() => { stopSpeaking(); sendQuery(cap.query); }} disabled={loading || openingMic || isListening}>
                  <div className="capability-icon"><Icon /></div>
                  <div>
                    <div className="capability-label">{cap.label}</div>
                    <div className="capability-example">{cap.example}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
