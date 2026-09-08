const fs = require('fs');
const path = require('path');

const LOG_FILE = path.join(__dirname, 'logs', 'pipeline.log');

function logInteraction(entry) {
  const logEntry = {
    timestamp: new Date().toISOString(),
    transcript: entry.transcript,
    topRetrievalScore: entry.topRetrievalScore,
    retrievedQuestion: entry.retrievedQuestion,
    response: entry.response,
    guardrailTriggered: entry.guardrailTriggered,
    latencyMs: entry.latencyMs
  };
  fs.appendFileSync(LOG_FILE, JSON.stringify(logEntry) + '\n');
}

module.exports = { logInteraction };
