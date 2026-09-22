const { getAllFaqs } = require('./db');

const STOPWORDS = new Set([
  'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
  'what', 'when', 'where', 'who', 'why', 'how', 'which',
  'about', 'do', 'does', 'did', 'i', 'you', 'it', 'to', 'for', 'of',
  'in', 'on', 'at', 'and', 'or', 'my', 'your', 'me', 'can', 'will',
  'that', 'this', 'there', 'have', 'has', 'need', 'want'
]);

function stem(word) {
  if (word.length > 5 && word.endsWith('ing')) return word.slice(0, -3);
  if (word.length > 4 && word.endsWith('ed')) return word.slice(0, -2);
  if (word.length > 3 && word.endsWith('es')) return word.slice(0, -2);
  if (word.length > 3 && word.endsWith('s') && !word.endsWith('ss')) return word.slice(0, -1);
  return word;
}

function tokenize(text) {
  return text.toLowerCase().replace(/[^a-z0-9\s]/g, '').split(/\s+/).filter(function(t) {
    return t && !STOPWORDS.has(t);
  }).map(stem);
}

function scoreOverlap(queryTokens, faqTokens) {
  const querySet = new Set(queryTokens);
  const faqSet = new Set(faqTokens);
  let overlap = 0;
  for (const t of querySet) {
    if (faqSet.has(t)) overlap++;
  }
  const queryRatio = overlap / Math.max(querySet.size, 1);
  const faqRatio = overlap / Math.max(faqSet.size, 1);
  return (queryRatio + faqRatio) / 2;
}

async function retrieveContext(query, topK = 2) {
  const faqs = getAllFaqs();
  const queryTokens = tokenize(query);

  const scored = faqs.map(function(faq) {
    const questionTokens = tokenize(faq.question);
    const answerTokens = tokenize(faq.answer);
    const questionScore = scoreOverlap(queryTokens, questionTokens);
    const answerScore = scoreOverlap(queryTokens, answerTokens);
    return {
      faq: faq,
      score: (questionScore * 0.75) + (answerScore * 0.25)
    };
  });

  scored.sort(function(a, b) { return b.score - a.score; });
  return scored.slice(0, topK);
}

module.exports = { retrieveContext };
