const { getAllFaqs } = require('./db');

const OLLAMA_HOST = process.env.OLLAMA_HOST || 'http://localhost:11434';
const EMBED_MODEL = 'all-minilm';

let faqs = [];
let faqEmbeddings = [];

function cosineSimilarity(a, b) {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

async function getOllamaEmbedding(text) {
  const res = await fetch(OLLAMA_HOST + '/api/embeddings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: EMBED_MODEL, prompt: text })
  });

  if (!res.ok) {
    throw new Error('Ollama embedding failed: ' + res.statusText);
  }

  const data = await res.json();
  return data.embedding;
}

async function initRAG() {
  console.log('Loading embedding model via Ollama...');
  faqs = getAllFaqs();

  for (const faq of faqs) {
    const embedding = await getOllamaEmbedding(faq.question);
    faqEmbeddings.push(embedding);
  }
  console.log('RAG system ready.');
}

async function retrieveContext(query, topK = 2) {
  const queryEmbedding = await getOllamaEmbedding(query);

  const scored = faqs.map(function(faq, i) {
    return {
      faq: faq,
      score: cosineSimilarity(queryEmbedding, faqEmbeddings[i])
    };
  });

  scored.sort(function(a, b) { return b.score - a.score; });
  return scored.slice(0, topK);
}

module.exports = { initRAG, retrieveContext, cosineSimilarity };
