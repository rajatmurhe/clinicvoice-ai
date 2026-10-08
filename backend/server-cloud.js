const express = require('express');
const cors = require('cors');
const { createHandler } = require('graphql-http/lib/use/express');
const { schema, root } = require('./graphql-schema');
const { seedFromJson } = require('./db');
const { retrieveContext } = require('./rag-cloud');
const { generateResponse } = require('./llm-cloud');
const { runWithRequestId } = require('./request-context');

const app = express();
app.use(cors({ exposedHeaders: ['X-Request-ID'] }));
app.use(express.json());

seedFromJson();

// One request id per request: inherited from the caller (frontend or Python
// service) or generated here, echoed back, and attached to every log line.
app.use(function(req, res, next) {
  const requestId = (req.headers['x-request-id'] || '').toString().slice(0, 64) ||
    require('crypto').randomBytes(6).toString('hex');
  res.setHeader('X-Request-ID', requestId);
  const start = Date.now();
  res.on('finish', function() {
    if (req.path === '/api/health') return;
    process.stdout.write(JSON.stringify({
      ts: new Date().toISOString(),
      request_id: requestId,
      route: req.path,
      method: req.method,
      status: res.statusCode,
      latency_ms: Date.now() - start
    }) + '\n');
  });
  runWithRequestId(requestId, next);
});

// Small per IP sliding window for the LLM and TTS endpoints so one caller
// cannot spam the paid APIs.
const hits = new Map();
function rateLimit(maxPerMinute) {
  return function(req, res, next) {
    const key = req.ip || 'unknown';
    const now = Date.now();
    const bucket = (hits.get(key) || []).filter(function(t) { return now - t < 60000; });
    if (bucket.length >= maxPerMinute) {
      hits.set(key, bucket);
      return res.status(429).json({ error: 'Too many requests. Please wait a moment and try again.' });
    }
    bucket.push(now);
    hits.set(key, bucket);
    next();
  };
}

app.all('/graphql', createHandler({ schema: schema, rootValue: root }));

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', message: 'ClinicVoice AI FAQ API (cloud) running' });
});

app.get('/', (req, res) => {
  res.json({
    message: 'ClinicVoice AI - Cloud FAQ API',
    note: 'This is the GraphQL/SQLite FAQ API only. The full voice/LLM pipeline runs locally (depends on Ollama, whisper.cpp).',
    graphql: '/graphql',
    health: '/api/health'
  });
});

app.post('/api/text-query', rateLimit(60), async (req, res) => {
  try {
    const query = req.body.query;
    if (!query) {
      return res.status(400).json({ error: 'No query provided.' });
    }
    const context = await retrieveContext(query);
    const result = await generateResponse(query, context);
    res.json({
      query: query,
      response: result.response,
      guardrailTriggered: result.guardrailTriggered,
      usage_tokens: result.usage_tokens || null,
      degraded: result.error === 'llm_unreachable'
    });
  } catch (err) {
    process.stderr.write(JSON.stringify({
      ts: new Date().toISOString(),
      route: '/api/text-query',
      level: 'error',
      error_type: err.name,
      message: err.message
    }) + '\n');
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/tts', rateLimit(60), async (req, res) => {
  try {
    const text = req.body.text;
    if (!text) {
      return res.status(400).json({ error: 'No text provided.' });
    }

    const response = await fetch('https://api.groq.com/openai/v1/audio/speech', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + process.env.GROQ_API_KEY
      },
      body: JSON.stringify({
        model: 'canopylabs/orpheus-v1-english',
        voice: 'hannah',
        input: text,
        response_format: 'wav'
      }),
      signal: AbortSignal.timeout(30000)
    });

    if (!response.ok) {
      const errText = await response.text();
      process.stderr.write(JSON.stringify({
        ts: new Date().toISOString(),
        route: '/api/tts',
        level: 'error',
        error_type: 'tts_upstream_error',
        message: errText.slice(0, 200)
      }) + '\n');
      // The text of the reply still exists on the frontend, so a missing audio
      // clip degrades to a 503 with a clear type instead of an opaque error.
      return res.status(503).json({ error: 'Text to speech is temporarily unavailable. The answer is shown as text.', error_type: 'tts_unavailable' });
    }

    const audioBuffer = await response.arrayBuffer();
    res.set('Content-Type', 'audio/wav');
    res.send(Buffer.from(audioBuffer));
  } catch (err) {
    process.stderr.write(JSON.stringify({
      ts: new Date().toISOString(),
      route: '/api/tts',
      level: 'error',
      error_type: err.name,
      message: err.message
    }) + '\n');
    res.status(503).json({ error: 'Text to speech is temporarily unavailable. The answer is shown as text.', error_type: 'tts_unavailable' });
  }
});

const PORT = process.env.PORT || 5050;
app.listen(PORT, () => {
  console.log('Cloud FAQ API running on port ' + PORT);
});
