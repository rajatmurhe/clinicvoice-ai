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

// Unicode aware: keeps Devanagari (and any other script) instead of stripping
// it, so Hindi and Marathi queries can match their translated FAQ variants.
function tokenize(text) {
  return text.toLowerCase().replace(/[^\p{L}\p{N}\p{M}\s]/gu, ' ').split(/\s+/).filter(function(t) {
    return t && !STOPWORDS.has(t);
  }).map(stem);
}

function trigrams(text) {
  const cleaned = text.toLowerCase().replace(/[^\p{L}\p{N}\p{M}]+/gu, ' ').replace(/\s+/g, ' ').trim();
  if (cleaned.length < 3) return new Set(cleaned ? [cleaned] : []);
  const grams = new Set();
  for (let i = 0; i + 3 <= cleaned.length; i++) {
    grams.add(cleaned.slice(i, i + 3));
  }
  return grams;
}

function jaccard(a, b) {
  if (a.size === 0 || b.size === 0) return 0;
  let intersection = 0;
  for (const g of a) {
    if (b.has(g)) intersection++;
  }
  return intersection / (a.size + b.size - intersection);
}

// BM25 over document token lists (one list per FAQ).
function bm25Scores(queryTokens, docs, k1, b) {
  const N = docs.length;
  const avgdl = docs.reduce(function(sum, d) { return sum + d.length; }, 0) / Math.max(N, 1);
  const df = new Map();
  docs.forEach(function(doc) {
    const seen = new Set(doc);
    for (const t of seen) df.set(t, (df.get(t) || 0) + 1);
  });
  return docs.map(function(doc) {
    const tf = new Map();
    doc.forEach(function(t) { tf.set(t, (tf.get(t) || 0) + 1); });
    let score = 0;
    for (const t of new Set(queryTokens)) {
      if (!df.has(t)) continue;
      const idf = Math.log(1 + (N - df.get(t) + 0.5) / (df.get(t) + 0.5));
      const f = tf.get(t) || 0;
      if (!f) continue;
      score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * (doc.length / Math.max(avgdl, 1))));
    }
    return score;
  });
}

const HYBRID_BM25_WEIGHT = 0.6;
const HYBRID_TRIGRAM_WEIGHT = 0.4;
const DISAGREEMENT_PENALTY = 0.85;

function hybridScores(query, faqs) {
  const queryTokens = tokenize(query);
  const queryGrams = trigrams(query);

  const docs = faqs.map(function(faq) {
    const q = tokenize(faq.question);
    const hi = faq.question_hi ? tokenize(faq.question_hi) : [];
    const mr = faq.question_mr ? tokenize(faq.question_mr) : [];
    const a = tokenize(faq.answer);
    return [].concat(q, q, q, hi, hi, hi, mr, mr, mr, a);
  });

  const bm25 = bm25Scores(queryTokens, docs, 1.5, 0.75);
  const maxBm25 = Math.max.apply(null, bm25);

  const scored = faqs.map(function(faq, i) {
    const bm25Norm = maxBm25 > 0 ? bm25[i] / maxBm25 : 0;

    let gramSim = jaccard(queryGrams, trigrams(faq.question));
    if (faq.question_hi) gramSim = Math.max(gramSim, jaccard(queryGrams, trigrams(faq.question_hi)));
    if (faq.question_mr) gramSim = Math.max(gramSim, jaccard(queryGrams, trigrams(faq.question_mr)));

    return {
      faq: faq,
      bm25: bm25Norm,
      trigram: gramSim,
      score: HYBRID_BM25_WEIGHT * bm25Norm + HYBRID_TRIGRAM_WEIGHT * gramSim
    };
  });

  // Cross check: when the two methods disagree on the best FAQ, neither is
  // trustworthy, so the winner's confidence is reduced.
  let bestBm25 = 0;
  let bestTrigram = 0;
  scored.forEach(function(s, i) {
    if (s.bm25 > scored[bestBm25].bm25) bestBm25 = i;
    if (s.trigram > scored[bestTrigram].trigram) bestTrigram = i;
  });
  if (bestBm25 !== bestTrigram && scored.length > 1) {
    scored[bestBm25].score *= DISAGREEMENT_PENALTY;
    scored[bestTrigram].score *= DISAGREEMENT_PENALTY;
  }

  return scored;
}

async function retrieveContext(query, topK = 2) {
  const faqs = getAllFaqs();
  const scored = hybridScores(query, faqs);
  scored.sort(function(a, b) { return b.score - a.score; });
  return scored.slice(0, topK);
}

module.exports = { retrieveContext, hybridScores, tokenize, trigrams };
