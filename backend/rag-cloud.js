const { getAllFaqs } = require('./db');

const STOPWORDS = new Set([
  'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
  'what', 'when', 'where', 'who', 'why', 'how', 'which',
  'about', 'do', 'does', 'did', 'i', 'you', 'it', 'to', 'for', 'of',
  'in', 'on', 'at', 'and', 'or', 'my', 'your', 'me', 'can', 'will',
  'that', 'this', 'there', 'have', 'has', 'need', 'want'
]);

function tokenize(text) {
  return text.toLowerCase().replace(/[^a-z0-9\s]/g, '').split(/\s+/).filter(function(t) {
    return t && !STOPWORDS.has(t);
  });
}

function scoreOverlap(queryTokens, faqTokens) {
  const querySet = new Set(queryTokens);
  const faqSet = new Set(faqTokens);
  let overlap = 0;
  for (const t of querySet) {
    if (faqSet.has(t)) overlap++;
  }
  return overlap / Math.max(querySet.size, 1);
}

async function retrieveContext(query, topK = 2) {
  const faqs = getAllFaqs();
  const queryTokens = tokenize(query);

  const scored = faqs.map(function(faq) {
    const faqTokens = tokenize(faq.question + ' ' + faq.answer);
    return {
      faq: faq,
      score: scoreOverlap(queryTokens, faqTokens)
    };
  });

  scored.sort(function(a, b) { return b.score - a.score; });
  return scored.slice(0, topK);
}

module.exports = { retrieveContext };
