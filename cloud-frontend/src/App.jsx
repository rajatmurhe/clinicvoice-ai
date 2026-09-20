import { useState, useRef, useEffect } from 'react';
import './App.css';

const API_URL = 'https://clinicvoice-ai.onrender.com';
const AGENT_URL = 'https://clinicvoice-ai-agents.onrender.com';

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
  { icon: CalendarIcon, label: 'Ask about appointments', example: '"What are your opening hours?"' },
  { icon: CardIcon, label: 'Check accepted insurance', example: '"Do you accept Aetna?"' },
  { icon: ClockIcon, label: 'General clinic questions', example: '"Is there parking?"' },
];

function App() {
  const [isListening, setIsListening] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [messages, setMessages] = useState([]);

  const recognitionRef = useRef(null);
  const conversationEndRef = useRef(null);
  const sessionIdRef = useRef('cloud-' + Date.now());

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const formatTime = () => {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const startListening = () => {
    setError('');
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setError('Speech recognition is not supported in this browser. Please use Chrome.');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      sendQuery(transcript);
    };

    recognition.onerror = (event) => {
      setError('Speech recognition error: ' + event.error);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  };

  const stopListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setIsListening(false);
  };

  const speak = async (text) => {
    try {
      const res = await fetch(API_URL + '/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
      });

      if (!res.ok) {
        throw new Error('TTS failed');
      }

      const audioBlob = await res.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      audio.play();
    } catch (err) {
      console.error('TTS error, falling back to browser voice:', err);
      const utterance = new SpeechSynthesisUtterance(text);
      window.speechSynthesis.speak(utterance);
    }
  };

  const sendQuery = async (query) => {
    setLoading(true);
    const time = formatTime();

    setMessages(function(prev) {
      return prev.concat([{ role: 'user', text: query, time: time }]);
    });

    try {
      const res = await fetch(AGENT_URL + '/api/agent-query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query, session_id: sessionIdRef.current })
      });

      if (!res.ok) {
        throw new Error('Server error: ' + res.status);
      }

      const data = await res.json();

      setMessages(function(prev) {
        return prev.concat([
          { role: 'assistant', text: data.response, guardrail: data.guardrailTriggered, time: formatTime() }
        ]);
      });

      speak(data.response);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const orbState = isListening ? 'listening' : loading ? 'thinking' : '';
  const orbHint = isListening ? 'Listening...' : loading ? 'Thinking...' : 'Tap to speak';

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
                disabled={loading}
              >
                {isListening ? <StopIcon /> : <MicIcon />}
              </button>
            </div>
            <span className="voice-hint">{orbHint}</span>
          </div>

          {messages.length === 0 && !loading && (
            <div className="empty-state">
              <div className="empty-state-title">Ask a question to get started</div>
              <div className="empty-state-sub">Fully live, speech, AI, and hosting all run in the cloud</div>
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
                </div>
              </div>
            )}

            <div ref={conversationEndRef}></div>
          </div>
        </div>

        <div className="capabilities-panel">
          <div className="capabilities-title">What I can help with</div>
          <div className="capabilities-sub">Try asking about any of these.</div>
          <div className="capabilities-list">
            {CAPABILITIES.map(function(cap, i) {
              const Icon = cap.icon;
              return (
                <div className="capability-item" key={i}>
                  <div className="capability-icon"><Icon /></div>
                  <div>
                    <div className="capability-label">{cap.label}</div>
                    <div className="capability-example">{cap.example}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
