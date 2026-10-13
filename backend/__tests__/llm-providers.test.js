// Provider selection and normalization tests. Everything here is mocked: CI
// never needs a Groq key or AWS credentials. Live behavior is covered by the
// manual scripts (scripts/bedrock-smoke.js, scripts/provider-comparison.js).
jest.mock('@aws-sdk/client-bedrock-runtime');

// Each test loads the modules fresh after setting env, so the provider module
// captures the same mocked client this test configures.
function loadModules() {
  const sdk = require('@aws-sdk/client-bedrock-runtime');
  const providers = require('../llm-providers');
  const llmCloud = require('../llm-cloud');
  return { sdk, providers, llmCloud };
}

const realFetch = global.fetch;

afterEach(function() {
  global.fetch = realFetch;
  delete process.env.LLM_PROVIDER;
  jest.restoreAllMocks();
});

function groqOk() {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: function() {
      return Promise.resolve({
        choices: [{ message: { content: '  We are open 9am to 6pm.  ' } }],
        usage: { total_tokens: 87 }
      });
    }
  });
}

function bedrockOk() {
  return {
    output: { message: { content: [{ text: 'We are open 9am to 6pm.' }] } },
    usage: { inputTokens: 400, outputTokens: 12 },
    metrics: { modelId: 'amazon.nova-micro-v1:0' }
  };
}

describe('provider selection', function() {
  test('groq is the default when LLM_PROVIDER is unset', async function() {
    const { sdk, providers } = loadModules();
    global.fetch = jest.fn().mockReturnValue(groqOk());
    const result = await providers.generate('hello');
    expect(result.provider).toBe('groq');
    expect(result.modelId).toBe('openai/gpt-oss-20b');
    expect(sdk.BedrockRuntimeClient).not.toHaveBeenCalled();
  });

  test('bedrock is selected when LLM_PROVIDER=bedrock', async function() {
    process.env.LLM_PROVIDER = 'bedrock';
    const { sdk, providers } = loadModules();
    const send = jest.fn().mockResolvedValue(bedrockOk());
    sdk.BedrockRuntimeClient.mockImplementation(function() { return { send: send }; });
    const result = await providers.generate('hello');
    expect(result.provider).toBe('bedrock');
    expect(send).toHaveBeenCalledTimes(1);
    expect(global.fetch).toBe(realFetch); // groq untouched
  });

  test('an unknown provider setting fails predictably', async function() {
    process.env.LLM_PROVIDER = 'openai';
    const { providers } = loadModules();
    await expect(providers.generate('hello')).rejects.toMatchObject({ category: 'invalid_provider' });
  });
});

describe('bedrock response normalization', function() {
  function withSend(sendMock) {
    process.env.LLM_PROVIDER = 'bedrock';
    const { sdk } = loadModules();
    sdk.BedrockRuntimeClient.mockImplementation(function() { return { send: sendMock }; });
    return loadModules();
  }

  test('a valid converse response normalizes to the shared shape', async function() {
    const { providers } = withSend(jest.fn().mockResolvedValue(bedrockOk()));
    const result = await providers.generate('hello');
    expect(result).toEqual({
      text: 'We are open 9am to 6pm.',
      provider: 'bedrock',
      modelId: 'amazon.nova-micro-v1:0',
      usageTokens: 412
    });
  });

  test('a missing or empty output is an empty_response error', async function() {
    const { providers } = withSend(jest.fn().mockResolvedValue({ output: { message: { content: [] } } }));
    await expect(providers.generate('hello')).rejects.toMatchObject({ category: 'empty_response' });
  });

  test('a timeout abort maps to a timeout error', async function() {
    const { providers } = withSend(jest.fn().mockRejectedValue(Object.assign(new Error('aborted'), { name: 'AbortError' })));
    await expect(providers.generate('hello')).rejects.toMatchObject({ category: 'timeout' });
  });

  test('an access denied response maps to access_denied', async function() {
    const { providers } = withSend(jest.fn().mockRejectedValue(Object.assign(new Error('denied'), { name: 'AccessDeniedException' })));
    await expect(providers.generate('hello')).rejects.toMatchObject({ category: 'access_denied' });
  });

  test('an unexpected response shape maps to unexpected_shape', async function() {
    const { providers } = withSend(jest.fn().mockResolvedValue({ completely: 'wrong' }));
    await expect(providers.generate('hello')).rejects.toMatchObject({ category: 'unexpected_shape' });
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
    process.env.LLM_PROVIDER = 'bedrock';
    const { sdk, llmCloud } = loadModules();
    sdk.BedrockRuntimeClient.mockImplementation(function() {
      return { send: jest.fn().mockRejectedValue(Object.assign(new Error('denied'), { name: 'AccessDeniedException' })) };
    });
    const result = await llmCloud.generateResponse('What are your opening hours?', contextWith(0.9));
    expect(result.response).toMatch(/reception team/);
    expect(result.error_category).toBe('access_denied');
    expect(result.guardrailTriggered).toBe(false);
  });

  test('the output safety check still blocks a bad generated answer, whichever provider made it', async function() {
    process.env.LLM_PROVIDER = 'bedrock';
    const { sdk, llmCloud } = loadModules();
    sdk.BedrockRuntimeClient.mockImplementation(function() {
      return {
        send: jest.fn().mockResolvedValue({
          output: { message: { content: [{ text: 'You should take 500mg of paracetamol twice a day.' }] } },
          usage: { inputTokens: 10, outputTokens: 10 }
        })
      };
    });
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
