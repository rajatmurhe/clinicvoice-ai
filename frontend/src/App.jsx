import { useState, useRef, useEffect } from 'react';
import './App.css';

function MicIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="9" y="2" width="6" height="12" rx="3" stroke="currentColor" strokeWidth="1.8"/>
      <path d="M5 11a7 7 0 0014 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <path d="M12 18v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <path d="M9 21h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2l8 3v6c0 5-3.5 8.5-8 11-4.5-2.5-8-6-8-11V5l8-3z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/>
      <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function BoltIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/>
    </svg>
  );
}

function ClinicIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 13v-1a8 8 0 0116 0v1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <rect x="3" y="13" width="4" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.8"/>
      <rect x="17" y="13" width="4" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.8"/>
      <path d="M19 19v1a3 3 0 01-3 3h-3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  );
}

function App() {
  const [showLanding, setShowLanding] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [messages, setMessages] = useState([]);

  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioChunksRef = useRef([]);
  const conversationEndRef = useRef(null);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const formatTime = () => {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const pickMimeType = () => {
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/mp4;codecs=mp4a.40.2',
      'audio/mp4',
      'audio/ogg;codecs=opus'
    ];
    for (const type of candidates) {
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) {
        return type;
      }
    }
    return '';
  };

  const startRecording = async () => {
    setError('');
    audioChunksRef.current = [];

    if (!streamRef.current) {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    }

    const mimeType = pickMimeType();
    const mediaRecorder = mimeType
      ? new MediaRecorder(streamRef.current, { mimeType: mimeType })
      : new MediaRecorder(streamRef.current);
    mediaRecorderRef.current = mediaRecorder;

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        audioChunksRef.current.push(e.data);
      }
    };

    mediaRecorder.onstop = async () => {
      const finalType = mediaRecorder.mimeType || 'audio/webm';
      const audioBlob = new Blob(audioChunksRef.current, { type: finalType });
      await sendAudio(audioBlob, finalType);
    };

    mediaRecorder.start();
    setIsRecording(true);
  };

  const stopRecording = () => {

    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      setLoading(true);
    }
  };

  const sendAudio = async (audioBlob, mimeType) => {
    try {
      const ext = (mimeType && mimeType.includes('mp4')) ? 'mp4' : (mimeType && mimeType.includes('ogg')) ? 'ogg' : 'webm';
      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.' + ext);
      formData.append('history', JSON.stringify(messages.map(function(m) { return { role: m.role, text: m.text }; })));

      const res = await fetch('http://localhost:5050/api/voice/query', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        throw new Error('Server error: ' + res.status);
      }

      const data = await res.json();
      const time = formatTime();

      setMessages(function(prev) {
        return prev.concat([
          { role: 'user', text: data.transcript, time: time },
          { role: 'assistant', text: data.response, guardrail: data.guardrailTriggered, time: formatTime() }
        ]);
      });

      const audioSrc = 'data:audio/aiff;base64,' + data.audioBase64;
      const audio = new Audio(audioSrc);
      audio.play();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (showLanding) {
    return (
      <div className="landing">
        <div className="landing-content">
          <div className="landing-icon"><ClinicIcon /></div>
          <h1 className="landing-title">ClinicVoice AI</h1>
          <p className="landing-tagline">Your clinic's virtual reception, available anytime.</p>

          <div className="landing-features">
            <div className="landing-feature">
              <span className="feature-icon"><MicIcon /></span>
              <span>Ask by voice, get real answers about appointments, hours, and more</span>
            </div>
            <div className="landing-feature">
              <span className="feature-icon"><ShieldIcon /></span>
              <span>Built-in safety checks — never gives medical advice, always grounded in real clinic info</span>
            </div>
            <div className="landing-feature">
              <span className="feature-icon"><BoltIcon /></span>
              <span>Fast, natural conversation, powered by local AI</span>
            </div>
          </div>

          <button className="landing-enter-btn" onClick={function() { setShowLanding(false); }}>
            Talk to ClinicVoice
          </button>

          <p className="landing-disclaimer">
            For appointment and clinic information only. Not for medical advice or emergencies.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="header">
        <div className="brand">
          <div className="brand-icon"><ClinicIcon /></div>
          <div className="brand-text">
            <h1>ClinicVoice AI</h1>
            <div className="status-row">
              <span className="status-dot"></span>
              <span className="status-text">Online · Local RAG + LLM</span>
            </div>
          </div>
        </div>
      </div>

      {error && <div className="error-banner">Error: {error}</div>}

      {messages.length === 0 && !loading && (
        <div className="empty-state">
          <div className="empty-state-icon">💬</div>
          <div>Tap the mic below and ask a question</div>
        </div>
      )}

      <div className="conversation">
        {messages.map(function(msg, i) {
          const isUser = msg.role === 'user';
          const bubbleClass = isUser ? 'bubble user' : msg.guardrail ? 'bubble guardrail' : 'bubble assistant';
          const avatarClass = isUser ? 'avatar user' : msg.guardrail ? 'avatar guardrail' : 'avatar assistant';
          const avatarIcon = isUser ? '🙂' : msg.guardrail ? '🛡️' : '🤖';

          return (
            <div key={i} className={'message-group ' + msg.role}>
              <div className={avatarClass}>{avatarIcon}</div>
              <div className="bubble-wrap">
                <div className={bubbleClass}>{msg.text}</div>
                <div className="timestamp">{msg.time}</div>
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="message-group assistant">
            <div className="avatar assistant">🤖</div>
            <div className="bubble-wrap">
              <div className="typing-indicator">
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
              </div>
            </div>
          </div>
        )}

        <div ref={conversationEndRef}></div>
      </div>

      <div className="mic-bar">
        <div className="mic-bar-inner">
          <button
            className={isRecording ? 'mic-btn recording' : 'mic-btn'}
            onClick={isRecording ? stopRecording : startRecording}
            disabled={loading}
          >
            {isRecording ? '⏹' : '🎙'}
          </button>
          <span className="mic-hint">
            {isRecording ? 'Listening...' : loading ? 'Thinking...' : 'Tap to speak'}
          </span>
        </div>
      </div>
    </div>
  );
}

export default App;
