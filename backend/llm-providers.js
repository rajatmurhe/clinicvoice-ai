// LLM provider layer: Groq (default) and Amazon Bedrock behind one interface.
//
// Every provider normalizes to { text, provider, modelId, usageTokens } or
// throws a ProviderError carrying a sanitized category (never the prompt,
// never credentials, never a raw stack). The caller (llm-cloud.js) turns any
// ProviderError into the same safe reception-team fallback, so a provider
// being down, slow, denied or weird can never crash a patient request.
const { BedrockRuntimeClient, ConverseCommand } = require('@aws-sdk/client-bedrock-runtime');

const { getRequestId } = require('./request-context');

const GROQ_MODEL = 'openai/gpt-oss-20b';
const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';
const BEDROCK_MODEL_DEFAULT = 'amazon.nova-micro-v1:0'; // confirm availability before use, see scripts/bedrock-smoke.js
const PROVIDER_TIMEOUT_MS = 20000;

class ProviderError extends Error {
  constructor(category, detail) {
    super(category);
    this.category = category; // sanitized: 'timeout' | 'access_denied' | 'empty_response' | 'unexpected_shape' | 'unreachable' | 'invalid_provider'
    // detail is for logs only if it is itself safe; callers log category only.
    this.detailType = detail ? detail.constructor.name : null;
  }
}

function providerName() {
  const name = (process.env.LLM_PROVIDER || 'groq').toLowerCase();
  if (name !== 'groq' && name !== 'bedrock') {
    throw new ProviderError('invalid_provider');
  }
  return name;
}

function bedrockModelId() {
  return process.env.BEDROCK_MODEL_ID || BEDROCK_MODEL_DEFAULT;
}

async function callGroq(prompt) {
  const body = JSON.stringify({
    model: GROQ_MODEL,
    messages: [{ role: 'user', content: prompt }],
    temperature: 0.2,
    max_tokens: 300
  });

  let lastError = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const response = await fetch(GROQ_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + process.env.GROQ_API_KEY,
          'X-Request-ID': getRequestId() || '-'
        },
        body: body,
        signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS)
      });
      if (!response.ok && response.status >= 500 && attempt === 0) {
        lastError = new ProviderError('unreachable');
        await new Promise(function(resolve) { setTimeout(resolve, 400); });
        continue;
      }
      if (response.status === 401 || response.status === 403) {
        throw new ProviderError('access_denied');
      }
      if (!response.ok) {
        throw new ProviderError('unreachable');
      }
      const data = await response.json();
      const text = data && data.choices && data.choices[0] && data.choices[0].message
        ? data.choices[0].message.content : null;
      if (!text || !text.trim()) {
        throw new ProviderError('empty_response');
      }
      return {
        text: text.trim(),
        provider: 'groq',
        modelId: GROQ_MODEL,
        usageTokens: data.usage ? data.usage.total_tokens : null
      };
    } catch (err) {
      if (err instanceof ProviderError && err.category === 'access_denied') throw err;
      lastError = (err && err.name === 'TimeoutError') ? new ProviderError('timeout') : (err instanceof ProviderError ? err : new ProviderError('unreachable'));
      if (attempt === 0) {
        await new Promise(function(resolve) { setTimeout(resolve, 400); });
      }
    }
  }
  throw lastError || new ProviderError('unreachable');
}

function bedrockClient() {
  try {
    return new BedrockRuntimeClient({ region: process.env.AWS_REGION || 'us-east-1' });
  } catch (err) {
    throw new ProviderError('unexpected_shape');
  }
}

function parseBedrockOutput(output) {
  // Converse returns output.message.content[] blocks of { text } variants.
  // A missing output block is an unexpected shape; an output that carries no
  // text is an empty response. Both fall back safely, the categories just
  // read differently on the dashboard.
  if (!output || typeof output !== 'object') {
    throw new ProviderError('unexpected_shape');
  }
  if (!output.message || !Array.isArray(output.message.content)) {
    throw new ProviderError('empty_response');
  }
  const text = output.message.content
    .map(function(block) { return block && typeof block.text === 'string' ? block.text : ''; })
    .join('')
    .trim();
  if (!text) {
    throw new ProviderError('empty_response');
  }
  return text;
}

async function callBedrock(prompt) {
  const client = bedrockClient();
  const command = new ConverseCommand({
    modelId: bedrockModelId(),
    messages: [{ role: 'user', content: [{ text: prompt }] }],
    inferenceConfig: { maxTokens: 300, temperature: 0.2 }
  });

  const controller = new AbortController();
  const timer = setTimeout(function() { controller.abort(); }, PROVIDER_TIMEOUT_MS);
  let response;
  try {
    response = await client.send(command, { abortSignal: controller.signal });
  } catch (err) {
    const name = err && err.name;
    if (name === 'AbortError' || name === 'TimeoutError') throw new ProviderError('timeout');
    if (name === 'AccessDeniedException' || name === 'UnrecognizedClientException') {
      throw new ProviderError('access_denied');
    }
    if (name === 'ValidationException' || name === 'ModelStreamErrorException' || name === 'ThrottlingException') {
      throw new ProviderError('unreachable');
    }
    throw new ProviderError('unexpected_shape');
  } finally {
    clearTimeout(timer);
  }

  const text = parseBedrockOutput(response.output);
  return {
    text: text,
    provider: 'bedrock',
    modelId: response.metrics && response.metrics.modelId ? response.metrics.modelId : bedrockModelId(),
    usageTokens: response.usage && (response.usage.inputTokens + response.usage.outputTokens) || null
  };
}

async function generate(prompt) {
  const name = providerName();
  if (name === 'bedrock') return callBedrock(prompt);
  return callGroq(prompt);
}

module.exports = {
  generate,
  providerName,
  bedrockModelId,
  callGroq,
  callBedrock,
  parseBedrockOutput,
  ProviderError
};
