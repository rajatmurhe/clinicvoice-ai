const express = require('express');
const cors = require('cors');
const { createHandler } = require('graphql-http/lib/use/express');
const { schema, root } = require('./graphql-schema');
const { seedFromJson } = require('./db');
const { retrieveContext } = require('./rag-cloud');
const { generateResponse } = require('./llm-cloud');

const app = express();
app.use(cors());
app.use(express.json());

seedFromJson();

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

app.post('/api/text-query', async (req, res) => {
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
      guardrailTriggered: result.guardrailTriggered
    });
  } catch (err) {
    console.error('Error:', err);
    res.status(500).json({ error: err.message });
  }
});

const PORT = process.env.PORT || 5050;
app.listen(PORT, () => {
  console.log('Cloud FAQ API running on port ' + PORT);
});
