import { useState, useRef, useEffect } from 'react';
import './App.css';

const API_URL = 'https://clinicvoice-ai.onrender.com';

function App() {
  const [isListening, setIsListening] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [messages, setMessages] = useState([]);

  const recognitionRef = useRef(null);
  const conversationEndRef = useRef(null);

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
      const res = await fetch(API_URL + '/api/text-query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query })
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

  return (
    <div className="app-shell">
      <div className="header">
        <div className="brand">
          <div className="brand-icon">☁️</div>
          <div className="brand-text">
            <h1>ClinicVoice AI</h1>
            <div className="status-row">
              <span className="status-dot"></span>
              <span className="status-text">Live · Groq + Render (fully cloud-hosted)</span>
            </div>
          </div>
        </div>
      </div>

      {error && <div className="error-banner">Error: {error}</div>}

      {messages.length === 0 && !loading && (
        <div className="empty-state">
          <div className="empty-state-icon">☁️</div>
          <div>Tap the mic below and ask a question</div>
          <div className="empty-state-sub">Fully live — speech, AI, and hosting all run in the cloud</div>
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
            className={isListening ? 'mic-btn recording' : 'mic-btn'}
            onClick={isListening ? stopListening : startListening}
            disabled={loading}
          >
            {isListening ? '🔴' : '🎙'}
          </button>
          <span className="mic-hint">
            {isListening ? 'Listening...' : loading ? 'Thinking...' : 'Tap to speak'}
          </span>
        </div>
      </div>
    </div>
  );
}

export default App;
