const express = require('express');
const cors = require('cors');
const multer = require('multer');
const rateLimit = require('express-rate-limit');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { initRAG, retrieveContext } = require('./rag');
const { generateResponse } = require('./llm');
const { logInteraction } = require('./logger');
const { createHandler } = require('graphql-http/lib/use/express');
const { schema, root } = require('./graphql-schema');

const app = express();

const voiceLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 30,
  message: { error: 'Too many requests, please try again later.' }
});
app.use(cors());
app.use(express.json());

const upload = multer({
  dest: 'uploads/',
  limits: { fileSize: 10 * 1024 * 1024 }
});

app.all('/graphql', createHandler({ schema: schema, rootValue: root }));

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', message: 'Voice assistant backend running' });
});

app.post('/api/voice/query', voiceLimiter, upload.single('audio'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No audio file provided." });
    }
    const startTime = Date.now();
    const audioPath = req.file.path;
    const wavPath = audioPath + '.wav';

    const t1 = Date.now();
    execSync('ffmpeg -i "' + audioPath + '" -ar 16000 -ac 1 -c:a pcm_s16le "' + wavPath + '" -y 2>/dev/null');
    console.log('ffmpeg:', Date.now() - t1, 'ms');

    const t2 = Date.now();
    const whisperOutput = execSync(
      'whisper-cli -m ../models/ggml-tiny.en.bin -f "' + wavPath + '" -np -nt'
    ).toString().trim();
    console.log("whisper:", Date.now() - t2, "ms");

    const transcript = whisperOutput;
    console.log('Transcript:', transcript);

    var sessionId = req.body.sessionId || 'voice-default';

    const t3 = Date.now();
    const agentRes = await fetch('http://localhost:8000/api/agent-query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: transcript, session_id: sessionId })
    });
    const agentData = await agentRes.json();
    console.log('agent:', Date.now() - t3, 'ms', '| intent:', agentData.intent);

    const result = {
      response: agentData.response,
      guardrailTriggered: agentData.guardrailTriggered || false
    };

    const speechPath = 'uploads/' + Date.now() + '_response.aiff';
    const t5 = Date.now();
    execSync('say "' + result.response.replace(/"/g, '') + '" -o ' + speechPath);
    console.log('tts:', Date.now() - t5, 'ms');

    const audioData = fs.readFileSync(speechPath);
    const audioBase64 = audioData.toString('base64');

    fs.unlinkSync(audioPath);
    fs.unlinkSync(wavPath);
    fs.unlinkSync(speechPath);

    logInteraction({
      transcript: transcript,
      intent: agentData.intent,
      agent: agentData.agent,
      response: result.response,
      guardrailTriggered: result.guardrailTriggered,
      latencyMs: Date.now() - startTime
    });

    res.json({
      transcript: transcript,
      response: result.response,
      guardrailTriggered: result.guardrailTriggered,
      audioBase64: audioBase64
    });
  } catch (err) {
    console.error('Error:', err);
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/text-query', async (req, res) => {
  try {
    const query = req.body.query;
    if (!query) {
      return res.status(400).json({ error: 'No query provided.' });
    }

    var history = req.body.history || [];

    var retrievalQuery = query;
    var lastUserTurns = history.filter(function(h) { return h.role === 'user'; }).slice(-1);
    if (lastUserTurns.length > 0) {
      retrievalQuery = lastUserTurns[0].text + ' ' + query;
    }

    const context = await retrieveContext(retrievalQuery);
    const result = await generateResponse(query, context, history);

    res.json({
      query: query,
      response: result.response,
      guardrailTriggered: result.guardrailTriggered
    });
  } catch (err) {
    console.error('Error:', err);
    res.status(500).json({ error: err.message });
  }
});

app.use((err, req, res, next) => {
  if (err.code === 'LIMIT_FILE_SIZE') {
    return res.status(413).json({ error: 'Audio file too large. Maximum size is 10MB.' });
  }
  console.error('Unhandled error:', err);
  res.status(500).json({ error: 'Internal server error.' });
});

const PORT = 5050;

function warmUpModel() {
  fetch('http://localhost:11434/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'llama3.2:3b',
      prompt: 'Hello',
      stream: false,
      options: { num_predict: 5 }
    })
  }).then(() => {
    console.log('Model warmed up.');
  }).catch((err) => {
    console.log('Warm-up call failed (non-fatal):', err.message);
  });
}

initRAG().then(() => {
  app.listen(PORT, () => {
    console.log('Server running on http://localhost:' + PORT);
    warmUpModel();
  });
});
