// Batch safety check for the red team harness: reads {"queries":[{"id":..,"q":..}]}
// on stdin and reports whether the Node blocklist (llm-cloud.checkSafety) blocks
// each one. No LLM call, no network.
const { checkSafety } = require('./llm-cloud');

let input = '';
process.stdin.on('data', function(chunk) { input += chunk; });
process.stdin.on('end', function() {
  const payload = JSON.parse(input);
  const results = (payload.queries || []).map(function(item) {
    return { id: item.id, blocked: checkSafety(item.q) };
  });
  process.stdout.write(JSON.stringify({ results: results }));
});
