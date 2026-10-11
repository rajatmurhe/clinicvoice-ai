// Each jest worker gets its own SQLite file so parallel suites do not
// fight over one database.
process.env.FAQ_DB_PATH = require('node:os').tmpdir() +
  '/faq-test-' + (process.env.JEST_WORKER_ID || '0') + '.db';
const { hybridScores, tokenize } = require('../rag-cloud');

// getAllFaqs reads the SQLite file; give the unit tests an in-memory index.
const FAQS = [
  { id: 3, question: 'What are your clinic opening hours?', question_hi: 'क्लिनिक के समय क्या हैं?', question_mr: 'क्लिनिकचे वेळापत्रक काय आहे?', answer: 'Open Monday to Friday 9am to 6pm.' },
  { id: 13, question: 'Is parking available at the clinic?', question_hi: 'क्लिनिक में पार्किंग है?', question_mr: 'क्लिनिकमध्ये पार्किंग आहे का?', answer: 'Free patient parking behind the building.' },
  { id: 27, question: 'Do you offer vaccinations?', question_hi: 'क्या टीकाकरण उपलब्ध है?', question_mr: 'लसीकरण उपलब्ध आहे का?', answer: 'We offer routine vaccinations.' }
];

function top(query) {
  const scored = hybridScores(query, FAQS).slice().sort(function(a, b) { return b.score - a.score; });
  return scored[0];
}

describe('hybrid retrieval', () => {
  test('exact English question matches its FAQ', () => {
    expect(top('What are your clinic opening hours?').faq.id).toBe(3);
  });

  test('English paraphrase matches the hours FAQ', () => {
    const t = top('What time do you open on Saturday?');
    expect(t.faq.id).toBe(3);
    expect(t.score).toBeGreaterThanOrEqual(0.35);
  });

  test('Hindi question matches through the translated variant', () => {
    expect(top('क्लिनिक के समय क्या हैं?').faq.id).toBe(3);
  });

  test('Marathi question matches through the translated variant', () => {
    expect(top('क्लिनिकचे वेळापत्रक काय आहे?').faq.id).toBe(3);
  });

  test('parking stays parking in Hindi', () => {
    expect(top('क्लिनिक में पार्किंग है?').faq.id).toBe(13);
  });

  test('unrelated query scores below the threshold', () => {
    expect(top('What is the capital of France?').score).toBeLessThan(0.35);
  });

  test('tokenizer keeps Devanagari instead of stripping it', () => {
    expect(tokenize('क्लिनिक के समय')).toContain('क्लिनिक');
  });
});
