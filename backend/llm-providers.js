// Provider errors contain categories only: never prompts, credentials or bodies.
const { getRequestId } = require('./request-context');
const GROQ_MODEL = 'openai/gpt-oss-20b';
const PROVIDER_TIMEOUT_MS = 8000; // Two providers fit the FAQ caller's 20s budget.
const TRANSIENT = new Set(['timeout', 'unreachable', 'rate_limited', 'server_error']);

class ProviderError extends Error {
  constructor(category) { super(category); this.category = category; }
}

function providerName() {
  const name = (process.env.LLM_PROVIDER || 'groq').trim().toLowerCase();
  if (!['groq', 'gemini'].includes(name)) throw new ProviderError('invalid_provider');
  return name;
}

async function request(url, headers, body) {
  try {
    const response = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify(body), signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS)
    });
    if ([401, 403].includes(response.status)) throw new ProviderError('access_denied');
    if (response.status === 429) throw new ProviderError('rate_limited');
    if (response.status === 408) throw new ProviderError('timeout');
    if (response.status >= 500) throw new ProviderError('server_error');
    if (!response.ok) throw new ProviderError('invalid_request');
    try { return await response.json(); }
    catch { throw new ProviderError('unexpected_shape'); }
  } catch (err) {
    if (err instanceof ProviderError) throw err;
    if (['TimeoutError', 'AbortError'].includes(err?.name)) throw new ProviderError('timeout');
    throw new ProviderError('unreachable');
  }
}

async function callGroq(prompt) {
  if (!process.env.GROQ_API_KEY) throw new ProviderError('missing_credentials');
  const data = await request('https://api.groq.com/openai/v1/chat/completions', {
    Authorization: 'Bearer ' + process.env.GROQ_API_KEY,
    'X-Request-ID': getRequestId() || '-'
  }, { model: GROQ_MODEL, messages: [{ role: 'user', content: prompt }], temperature: 0.2, max_tokens: 300 });
  const text = data?.choices?.[0]?.message?.content;
  if (typeof text !== 'string' || !text.trim()) throw new ProviderError('empty_response');
  const usage = data.usage || {};
  return {
    text: text.trim(), provider: 'groq', modelId: GROQ_MODEL,
    usageTokens: usage.total_tokens ?? null,
    usageDetails: {
      ...(Number.isFinite(usage.prompt_tokens) ? { promptTokens: usage.prompt_tokens } : {}),
      ...(Number.isFinite(usage.completion_tokens) ? { completionTokens: usage.completion_tokens } : {}),
      ...(Number.isFinite(usage.total_tokens) ? { totalTokens: usage.total_tokens } : {})
    }
  };
}

async function callGemini(prompt) {
  if (!process.env.GEMINI_API_KEY) throw new ProviderError('missing_credentials');
  const model = process.env.GEMINI_MODEL || 'gemini-3.8-flash';
  const data = await request(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`, {
    'x-goog-api-key': process.env.GEMINI_API_KEY
  }, {
    contents: [{ role: 'user', parts: [{ text: prompt }] }],
    generationConfig: { temperature: 0.2, maxOutputTokens: 1024, thinkingConfig: model.startsWith("gemini-2.5") ? { thinkingBudget: 0 } : { thinkingLevel: "low" } }
  });
  const candidate = data?.candidates?.[0];
  if (data?.promptFeedback?.blockReason || ['SAFETY', 'RECITATION', 'PROHIBITED_CONTENT', 'BLOCKLIST', 'SPII'].includes(candidate?.finishReason)) {
    throw new ProviderError('content_blocked');
  }
  const parts = candidate?.content?.parts;
  const text = Array.isArray(parts) ? parts.filter(p => !p.thought && typeof p.text === 'string').map(p => p.text).join('') : '';
  if (!text.trim()) throw new ProviderError('empty_response');
  const usage = data.usageMetadata || {};
  return {
    text: text.trim(), provider: 'gemini', modelId: model,
    usageTokens: usage.totalTokenCount ?? null,
    usageDetails: {
      ...(Number.isFinite(usage.promptTokenCount) ? { promptTokens: usage.promptTokenCount } : {}),
      ...(Number.isFinite(usage.candidatesTokenCount) ? { completionTokens: usage.candidatesTokenCount } : {}),
      ...(Number.isFinite(usage.totalTokenCount) ? { totalTokens: usage.totalTokenCount } : {})
    }
  };
}

async function generate(prompt, options = {}) {
  const primary = providerName();
  const secondary = primary === 'groq' ? 'gemini' : 'groq';
  const calls = { groq: callGroq, gemini: callGemini };
  const attempts = [];
  async function call(name) {
    const started = Date.now();
    const modelId = name === 'groq' ? GROQ_MODEL : (process.env.GEMINI_MODEL || 'gemini-3.8-flash');
    try { if (options.onAttempt) options.onAttempt({ phase: 'start', provider: name, modelId }); } catch (_) { /* telemetry is best effort */ }
    try {
      const result = await calls[name](prompt);
      const attempt = {
        provider: name,
        modelId: result.modelId,
        latencyMs: Date.now() - started,
        usageTokens: result.usageTokens,
        usageDetails: result.usageDetails
      };
      attempts.push(attempt);
      try { if (options.onAttempt) options.onAttempt({ phase: 'end', status: 'success', ...attempt, response: result.text }); } catch (_) { /* telemetry is best effort */ }
      return { ...result, attempts };
    } catch (err) {
      const attempt = {
        provider: name,
        modelId,
        latencyMs: Date.now() - started,
        errorCategory: err instanceof ProviderError ? err.category : 'unreachable'
      };
      attempts.push(attempt);
      try { if (options.onAttempt) options.onAttempt({ phase: 'end', status: 'error', ...attempt }); } catch (_) { /* telemetry is best effort */ }
      err.attempts = attempts;
      throw err;
    }
  }
  try { return await call(primary); }
  catch (err) {
    // Never route authentication, request, or safety failures to another vendor.
    if (!TRANSIENT.has(err.category) || !process.env[secondary === 'groq' ? 'GROQ_API_KEY' : 'GEMINI_API_KEY']) throw err;
    console.warn(`[LLM-FAILOVER] ${primary}: ${err.category}; trying ${secondary}`);
    return call(secondary);
  }
}

module.exports = { generate, providerName, callGroq, callGemini, ProviderError };
