import { useState, useRef, useEffect } from 'react';
import './App.css';

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [messages, setMessages] = useState([]);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const conversationEndRef = useRef(null);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const formatTime = () => {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const startRecording = async () => {
    setError('');
    audioChunksRef.current = [];

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    mediaRecorderRef.current = mediaRecorder;

    mediaRecorder.ondataavailable = (e) => {
      audioChunksRef.current.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
      await sendAudio(audioBlob);
      stream.getTracks().forEach(track => track.stop());
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

  const sendAudio = async (audioBlob) => {
    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.webm');

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

  return (
    <div className="app-shell">
      <div className="header">
        <div className="brand">
          <div className="brand-icon">🩺</div>
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
