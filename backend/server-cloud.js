const express = require('express');
const cors = require('cors');
const { createHandler } = require('graphql-http/lib/use/express');
const { schema, root } = require('./graphql-schema');
const { seedFromJson, FAQ_RETRIEVAL_SQL } = require('./db');
const { retrieveContext } = require('./rag-cloud');
const { generateResponse } = require('./llm-cloud');
const { runWithRequestId } = require('./request-context');
const tracing = require('./langfuse-tracing');

const app = express();
app.use(cors({ exposedHeaders: ['X-Request-ID'] }));
// Audio uses base64 JSON; normal recordings exceed Express's 100 KB default.
app.use('/api/transcribe', express.json({ limit: '10mb' }));
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

app.post('/api/router-classify', rateLimit(120), async (req, res) => {
  // Hybrid router endpoint: classifies a low-confidence message for the
  // Python orchestrator. Returns the regex-safe fallback on any LLM problem.
  const query = req.body?.query;
  const INTENTS = ['booking', 'refill', 'insurance', 'intake', 'escalation', 'faq'];
  if (!query) {
    return res.status(400).json({ error: 'No query provided.' });
  }
  try {
    const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + process.env.GROQ_API_KEY,
        'X-Request-ID': (req.headers['x-request-id'] || '').toString().slice(0, 64) || '-'
      },
      body: JSON.stringify({
        model: 'openai/gpt-oss-20b',
        messages: [
          { role: 'user', content: 'Classify this clinic reception message into exactly one intent: booking, refill, insurance, intake, escalation, or faq. A booking message is about making, moving, checking or cancelling appointments. Refill is about requesting more of an existing medicine. Intake is describing a symptom or test result to pass to a clinician. Escalation is anger or asking for a human. Everything else is faq. Answer with the single word intent only.\n\nMessage: ' + query }
        ],
        temperature: 0,
        max_tokens: 10
      }),
      signal: AbortSignal.timeout(8000)
    });
    if (!response.ok) {
      return res.json({ intent: 'faq', fallback: true });
    }
    const data = await response.json();
    const intent = (data.choices[0].message.content || '').trim().toLowerCase();
    res.json({ intent: INTENTS.includes(intent) ? intent : 'faq', fallback: !INTENTS.includes(intent) });
  } catch (err) {
    res.json({ intent: 'faq', fallback: true });
  }
});

app.post('/api/transcribe', rateLimit(60), async (req, res) => {
  // Server side speech to text for browsers without the Web Speech API
  // (Safari, Brave): the push to talk fallback records audio and posts it here.
  try {
    if (!req.body || typeof req.body.audio !== 'string' || !req.body.audio) {
      return res.status(400).json({ error: 'No audio provided.' });
    }
    const base64Data = String(req.body.audio).replace(/^data:[^,]+,/, '');
    const audioBuffer = Buffer.from(base64Data, 'base64');
    if (audioBuffer.length < 800) {
      return res.status(400).json({ error: 'Recording too short.' });
    }

    const mime = /^data:(audio\/[^;,]+)/.exec(req.body.audio)?.[1] || 'audio/webm';
    const extension = { 'audio/mp4': 'm4a', 'audio/wav': 'wav', 'audio/ogg': 'ogg', 'audio/mpeg': 'mp3' }[mime] || 'webm';
    const form = new FormData();
    form.append('file', new Blob([audioBuffer], { type: mime }), 'speech.' + extension);
    form.append('model', 'whisper-large-v3-turbo');
    form.append('response_format', 'json');
    form.append('temperature', '0');
    if (['en', 'hi', 'mr'].includes(req.body.language)) form.append('language', req.body.language);

    const response = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + process.env.GROQ_API_KEY,
        'X-Request-ID': (req.headers['x-request-id'] || '').toString().slice(0, 64) || '-'
      },
      body: form,
      signal: AbortSignal.timeout(20000)
    });

    if (!response.ok) {
      const errText = await response.text();
      process.stderr.write(JSON.stringify({
        ts: new Date().toISOString(),
        route: '/api/transcribe',
        level: 'error',
        error_type: 'stt_upstream_error',
        message: errText.slice(0, 200)
      }) + '\n');
      return res.status(503).json({ error: 'Speech to text is temporarily unavailable. Please type your question instead.', error_type: 'stt_unavailable' });
    }

    const data = await response.json();
    res.json({ text: (data.text || '').trim() });
  } catch (err) {
    process.stderr.write(JSON.stringify({
      ts: new Date().toISOString(),
      route: '/api/transcribe',
      level: 'error',
      error_type: err.name,
      message: err.message
    }) + '\n');
    res.status(503).json({ error: 'Speech to text is temporarily unavailable. Please type your question instead.', error_type: 'stt_unavailable' });
  }
});

app.post('/api/text-query', rateLimit(60), async (req, res) => {
  let trace = null;
  try {
    const query = req.body?.query;
    if (typeof query !== "string" || !query.trim() || query.length > 10000) {
      return res.status(400).json({ error: 'No query provided.' });
    }
    const clinicId = req.body.clinic_id || 'default';
    trace = tracing.startFaqTrace({
      requestId: res.getHeader('X-Request-ID') || '-',
      clinicId,
      query
    });
    const retrievalStarted = Date.now();
    const retrieval = tracing.startChild(trace, 'faq-sql-retrieval', {
      input: {
        sql_template: FAQ_RETRIEVAL_SQL,
        bind_parameters: ['clinic_id (redacted)'],
        ...(tracing.traceContent ? { question: query } : {})
      },
      metadata: { retrieval: 'hybrid-bm25-and-character-trigram', top_k: 2 }
    }, 'retriever');
    let context;
    try {
      context = await retrieveContext(query, 2, clinicId);
    } catch (error) {
      tracing.updateObservation(retrieval, { level: 'ERROR', statusMessage: error && error.name ? error.name : 'retrieval_failed' });
      tracing.endObservation(retrieval);
      throw error;
    }
    tracing.updateObservation(retrieval, {
      output: {
        result_count: context.length,
        matches: context.map(function(item) { return { faq_id: item.faq.id, score: item.score }; })
      },
      metadata: { latency_ms: Date.now() - retrievalStarted }
    });
    tracing.endObservation(retrieval);

    const result = await generateResponse(query, context, { trace });
    tracing.updateObservation(trace, {
      output: tracing.contentValue(result.response, { redacted: true, character_count: result.response.length }),
      metadata: {
        provider: result.provider || 'pre-decision',
        model_id: result.model_id || null,
        usage_tokens: result.usage_tokens ?? null,
        guardrail: result.guardrailTriggered || false,
        degraded: result.error === 'llm_unreachable'
      }
    });
    tracing.endObservation(trace);
    trace = null;
    // Structured provider log: names, model id, latency and token counts only.
    // The prompt and the answer never go to the log line.
    process.stdout.write(JSON.stringify({
      ts: new Date().toISOString(),
      request_id: res.getHeader('X-Request-ID') || '-',
      event: 'llm_answer',
      provider: result.provider || 'pre-decision',
      model_id: result.model_id || null,
      provider_latency_ms: result.provider_latency_ms != null ? result.provider_latency_ms : null,
      usage_tokens: result.usage_tokens || null,
      guardrail: result.guardrailTriggered || false,
      error_category: result.error_category || null
    }) + '\n');
    res.json({
      query: query,
      response: result.response,
      guardrailTriggered: result.guardrailTriggered,
      provider: result.provider || null,
      model_id: result.model_id || null,
      usage_tokens: result.usage_tokens || null,
      degraded: result.error === 'llm_unreachable'
    });
  } catch (err) {
    tracing.updateObservation(trace, {
      level: 'ERROR',
      statusMessage: err && err.name ? err.name : 'faq_request_failed'
    });
    tracing.endObservation(trace);
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
    const text = req.body?.text;
    if (typeof text !== "string" || !text.trim() || text.length > 10000) {
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

// Keep malformed/oversized requests actionable for the voice client.
app.use((err, req, res, next) => {
  if (err.type === 'entity.too.large') return res.status(413).json({ error: 'Recording too large. Please record a shorter message.' });
  if (err.type === 'entity.parse.failed') return res.status(400).json({ error: 'Invalid JSON request.' });
  next(err);
});

if (require.main === module) {
  const PORT = process.env.PORT || 5050;
  const server = app.listen(PORT, () => console.log('Cloud FAQ API running on port ' + PORT));
  ['SIGINT', 'SIGTERM'].forEach(function(signal) {
    process.once(signal, function() {
      server.close(function() {
        tracing.shutdown().finally(function() { process.exit(0); });
      });
    });
  });
}
module.exports = app;
