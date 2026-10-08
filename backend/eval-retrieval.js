// Offline FAQ evaluation: runs retrieval plus the pre-LLM decision pipeline
// (input blocklist, greeting short circuit, confidence threshold) without ever
// calling the LLM. Input comes from stdin as JSON:
//   { "cases": [ { "id": "...", "query": "...", "expect": "answer|fallback|block|greeting", "faq_id": 3 } ] }
// Output goes to stdout as JSON with per-case decisions and a summary.
const { seedFromJson, getAllFaqs } = require('./db');
const { retrieveContext } = require('./rag-cloud');
const { decidePreLLM } = require('./llm-cloud');

async function main() {
  let input = '';
  for await (const chunk of process.stdin) {
    input += chunk;
  }

  const payload = JSON.parse(input);
  const cases = payload.cases || [];

  // db.js logs a refresh line on stdout; silence it so stdout is pure JSON.
  const originalLog = console.log;
  console.log = function() {};
  seedFromJson();
  console.log = originalLog;
  const faqs = getAllFaqs();

  const results = [];
  let decisionCorrect = 0;
  let answerRetrieved = 0;
  let answerTotal = 0;

  for (const c of cases) {
    const context = await retrieveContext(c.query, 1);
    const pre = decidePreLLM(c.query, context);
    const decision = pre.kind === 'llm' ? 'answer' : pre.kind;

    const correct = decision === c.expect;
    if (correct) decisionCorrect++;

    let hit = null;
    if (c.expect === 'answer') {
      answerTotal++;
      if (decision === 'answer') {
        answerRetrieved++;
        hit = c.faq_id != null ? pre.topFaqId === c.faq_id : null;
      } else {
        hit = false;
      }
    }

    results.push({
      id: c.id,
      query: c.query,
      expect: c.expect,
      expected_faq_id: c.faq_id != null ? c.faq_id : null,
      decision: decision,
      top_faq_id: pre.topFaqId,
      top_score: Math.round(pre.topScore * 10000) / 10000,
      decision_correct: correct,
      hit_at_1: hit
    });
  }

  const faqAnswerCases = results.filter(function(r) { return r.expect === 'answer'; });
  const scoredFaqCases = faqAnswerCases.filter(function(r) { return r.hit_at_1 !== null; });

  const summary = {
    total_cases: cases.length,
    faqs_in_index: faqs.length,
    decision_accuracy: cases.length ? Math.round((decisionCorrect / cases.length) * 1000) / 10 : null,
    faq_answer_cases: faqAnswerCases.length,
    retrieval_answer_rate: faqAnswerCases.length
      ? Math.round((answerRetrieved / faqAnswerCases.length) * 1000) / 10
      : null,
    hit_at_1: scoredFaqCases.length
      ? Math.round((scoredFaqCases.filter(function(r) { return r.hit_at_1; }).length / scoredFaqCases.length) * 1000) / 10
      : null
  };

  process.stdout.write(JSON.stringify({ summary: summary, results: results }, null, 2));
}

main().catch(function(err) {
  process.stderr.write(String(err && err.stack ? err.stack : err) + '\n');
  process.exit(1);
});
