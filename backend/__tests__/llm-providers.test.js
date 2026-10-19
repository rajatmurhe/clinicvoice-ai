// Provider selection and normalization tests. Everything here is mocked: CI
// never needs a Groq key or Gemini key. Live behavior is spot-checked manually.
const realFetch = global.fetch;

function loadModules() {
  const providers = require('../llm-providers');
  const llmCloud = require('../llm-cloud');
  return { providers, llmCloud };
}

afterEach(function() {
  global.fetch = realFetch;
  delete process.env.LLM_PROVIDER;
  delete process.env.GEMINI_API_KEY;
  delete process.env.GROQ_API_KEY;
  jest.restoreAllMocks();
  jest.resetModules();
});

function groqOk() {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: function() {
      return Promise.resolve({
        choices: [{ message: { content: '  We are open 9am to 6pm.  ' } }],
        usage: { prompt_tokens: 50, completion_tokens: 37, total_tokens: 87 }
      });
    }
  });
}

function geminiOk() {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: function() {
      return Promise.resolve({
        candidates: [{ content: { parts: [{ text: '  We are open 9am to 6pm.  ' }] } }],
        usageMetadata: { promptTokenCount: 70, candidatesTokenCount: 50, totalTokenCount: 120 }
      });
    }
  });
}

describe('provider selection', function() {
  test('groq is the default when LLM_PROVIDER is unset', async function() {
    jest.resetModules();
    const { providers } = loadModules();
    global.fetch = jest.fn().mockReturnValue(groqOk());
    process.env.GROQ_API_KEY = 'test';
    const result = await providers.generate('hello');
    expect(result.provider).toBe('groq');
    expect(result.modelId).toBe('openai/gpt-oss-20b');
    expect(result.usageDetails).toEqual({ promptTokens: 50, completionTokens: 37, totalTokens: 87 });
  });

  test('gemini is selected when LLM_PROVIDER=gemini', async function() {
    process.env.LLM_PROVIDER = 'gemini';
    process.env.GEMINI_API_KEY = 'test';
    jest.resetModules();
    const { providers } = loadModules();
    global.fetch = jest.fn().mockReturnValue(geminiOk());
    const result = await providers.generate('hello');
    expect(result.provider).toBe('gemini');
  });

  test('an unknown provider setting fails predictably', async function() {
    process.env.LLM_PROVIDER = 'openai';
    const { providers } = loadModules();
    await expect(providers.generate('hello')).rejects.toMatchObject({ category: 'invalid_provider' });
  });
});

describe('gemini response normalization', function() {
  beforeEach(function() {
    process.env.GEMINI_API_KEY = 'test';
    process.env.LLM_PROVIDER = 'gemini';
    jest.resetModules();
  });

  test('a valid gemini response normalizes to the shared shape', async function() {
    const { providers } = loadModules();
    global.fetch = jest.fn().mockReturnValue(geminiOk());
    const result = await providers.generate('hello');
    expect(result.provider).toBe('gemini');
    expect(result.text).toBe('We are open 9am to 6pm.');
    expect(result.usageDetails).toEqual({ promptTokens: 70, completionTokens: 50, totalTokens: 120 });
  });

  test('an empty candidate is an empty_response error', async function() {
    const { providers } = loadModules();
    global.fetch = jest.fn().mockResolvedValue({
      ok: true, status: 200,
      json: function() { return Promise.resolve({ candidates: [] }); }
    });
    await expect(providers.generate('hello')).rejects.toMatchObject({ category: 'empty_response' });
  });
});

describe('the safety pipeline stays in front of every provider', function() {
  function contextWith(score) {
    return [{ faq: { id: 3, question: 'What are your opening hours?', answer: 'Nine to six.' }, score: score }];
  }

  test('a blocked question never reaches any provider', async function() {
    global.fetch = jest.fn();
    const { llmCloud } = loadModules();
    const result = await llmCloud.generateResponse('What dosage of paracetamol is safe?', contextWith(0.9));
    expect(result.guardrailTriggered).toBe(true);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('a provider failure returns the reception fallback, not a crash', async function() {
    const { llmCloud } = loadModules();
    global.fetch = jest.fn().mockRejectedValue(new Error('network down'));
    process.env.LLM_PROVIDER = 'groq';
    process.env.GROQ_API_KEY = 'bad';
    const result = await llmCloud.generateResponse('What are your opening hours?', contextWith(0.9));
    expect(result.response).toMatch(/reception team/);
    expect(result.guardrailTriggered).toBe(false);
  });

  test('the output safety check still blocks a bad generated answer, whichever provider made it', async function() {
    const { llmCloud } = loadModules();
    global.fetch = jest.fn().mockReturnValue(Promise.resolve({
      ok: true, status: 200,
      json: function() {
        return Promise.resolve({
          choices: [{ message: { content: 'You should take 500mg of paracetamol twice a day.' } }],
          usage: { total_tokens: 50 }
        });
      }
    }));
    process.env.GROQ_API_KEY = 'test';
    const result = await llmCloud.generateResponse('What are your opening hours?', contextWith(0.9));
    expect(result.guardrailTriggered).toBe(true);
    expect(result.response).toMatch(/not able to help/);
  });

  test('pre-LLM decisions are provider independent', function() {
    const { llmCloud } = loadModules();
    const pre = llmCloud.decidePreLLM('What are your opening hours?', contextWith(0.9));
    expect(pre.kind).toBe('llm');
    expect(llmCloud.decidePreLLM('hello', contextWith(0)).kind).toBe('greeting');
  });
});

describe('bounded transient failover', () => {
  beforeEach(() => {
    process.env.GROQ_API_KEY = 'test-groq';
    process.env.GEMINI_API_KEY = 'test-gemini';
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });
  test.each([429, 500, 503])('Groq %s falls back to Gemini once', async status => {
    global.fetch = jest.fn().mockResolvedValueOnce({ok: false, status}).mockReturnValueOnce(geminiOk());
    const result = await loadModules().providers.generate('hello');
    expect(result.provider).toBe('gemini');
    expect(result.usageTokens).toBe(120);
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.fetch.mock.calls[1][0]).not.toContain('test-gemini');
  });
  test('each provider attempt exposes bounded tracing metadata for a failover run', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({ok: false, status: 503}).mockReturnValueOnce(geminiOk());
    const events = [];
    const result = await loadModules().providers.generate('hello', { onAttempt: event => events.push(event) });
    expect(result.attempts.map(attempt => attempt.provider)).toEqual(['groq', 'gemini']);
    expect(events.map(event => [event.phase, event.provider])).toEqual([
      ['start', 'groq'], ['end', 'groq'], ['start', 'gemini'], ['end', 'gemini']
    ]);
    expect(events[1].errorCategory).toBe('server_error');
    expect(events[3].usageDetails).toEqual({ promptTokens: 70, completionTokens: 50, totalTokens: 120 });
  });
  test('Gemini timeout falls back to Groq', async () => {
    process.env.LLM_PROVIDER = 'gemini';
    global.fetch = jest.fn().mockRejectedValueOnce(Object.assign(new Error(), {name: 'TimeoutError'})).mockReturnValueOnce(groqOk());
    expect((await loadModules().providers.generate('hello')).provider).toBe('groq');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
  test.each([400, 401, 403, 404])('HTTP %s does not fail over', async status => {
    global.fetch = jest.fn().mockResolvedValue({ok: false, status});
    await expect(loadModules().providers.generate('hello')).rejects.toBeInstanceOf(Error);
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
  test('Gemini safety refusal does not fail over', async () => {
    process.env.LLM_PROVIDER = 'gemini';
    global.fetch = jest.fn().mockResolvedValue({ok: true, json: async () => ({promptFeedback: {blockReason: 'SAFETY'}})});
    await expect(loadModules().providers.generate('hello')).rejects.toMatchObject({category: 'content_blocked'});
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
  test('both providers down terminates after two calls', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('offline'));
    await expect(loadModules().providers.generate('hello')).rejects.toMatchObject({category: 'unreachable'});
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
  test('unconfigured secondary is never contacted', async () => {
    delete process.env.GEMINI_API_KEY;
    global.fetch = jest.fn().mockRejectedValue(new Error('offline'));
    await expect(loadModules().providers.generate('hello')).rejects.toMatchObject({category: 'unreachable'});
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
