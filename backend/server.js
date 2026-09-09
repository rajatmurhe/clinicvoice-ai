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

    var history = [];
    if (req.body.history) {
      try {
        history = JSON.parse(req.body.history);
      } catch (e) {
        history = [];
      }
    }

    var retrievalQuery = transcript;
    var lastUserTurns = history.filter(function(h) { return h.role === 'user'; }).slice(-1);
    if (lastUserTurns.length > 0) {
      retrievalQuery = lastUserTurns[0].text + ' ' + transcript;
    }

    const t3 = Date.now();
    const context = await retrieveContext(retrievalQuery);
    console.log("retrieval:", Date.now() - t3, "ms");
    const t4 = Date.now();
    const result = await generateResponse(transcript, context, history);
    console.log("llm:", Date.now() - t4, "ms");

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
      topRetrievalScore: context[0] ? context[0].score : null,
      retrievedQuestion: context[0] ? context[0].faq.question : null,
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

initRAG().then(() => {
  app.listen(PORT, () => {
    console.log('Server running on http://localhost:' + PORT);
  });
});
