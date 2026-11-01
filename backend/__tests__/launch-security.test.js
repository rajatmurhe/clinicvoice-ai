process.env.CLINICVOICE_SERVICE_KEY = 'test-service-key-' + 'x'.repeat(32);
const nativeFetch = global.fetch;
const app = require('../server-cloud');
const {checkSafety} = require('../llm-cloud');
const cases = require('../../python-eval/cases/off_scope_unsafe.json');
let server, base;
beforeAll(async () => {
  server = await new Promise(resolve => {const s = app.listen(0, '127.0.0.1', () => resolve(s));});
  base = `http://127.0.0.1:${server.address().port}`;
});
afterAll(async () => {await new Promise(resolve => server.close(resolve));});
afterEach(() => {global.fetch = nativeFetch;});
const post = (route, body, headers = {}) => nativeFetch(base + route, {method: 'POST', headers: {'Content-Type':'application/json', ...headers}, body: JSON.stringify(body)});
test.each(cases.filter(c => c.id.startsWith('launch-safe-')))('$id passes Node safety', c => {
  expect(checkSafety(c.turns[0].q)).toBe(false);
});
test('unauthenticated paid routes do not call upstream', async () => {
  global.fetch = jest.fn();
  for (const path of ['/api/tts','/api/transcribe','/api/text-query','/api/router-classify','/api/agent-query']) {
    expect((await post(path, {text:'hello',query:'hello'})).status).toBe(401);
  }
  expect(global.fetch).not.toHaveBeenCalled();
});
test('session issuance rejects foreign origins and missing configuration', async () => {
  expect((await post('/api/session', {}, {Origin:'https://evil.example'})).status).toBe(403);
  const key = process.env.CLINICVOICE_SERVICE_KEY;
  delete process.env.CLINICVOICE_SERVICE_KEY;
  try {expect((await post('/api/session', {}, {Origin:'http://localhost:5050'})).status).toBe(503);}
  finally {process.env.CLINICVOICE_SERVICE_KEY = key;}
});
test('valid session works; tampered tokens cannot reach provider; internal routes reject browser tokens', async () => {
  const session = await post('/api/session', {}, {Origin:'http://localhost:5050'});
  expect(session.status).toBe(200);
  const {token} = await session.json();
  global.fetch = jest.fn().mockResolvedValue({ok:true,arrayBuffer:async()=>new ArrayBuffer(2)});
  const headers = {Authorization:'Bearer ' + token, 'X-Request-ID':'<img src=x>'};
  const good = await post('/api/tts', {text:'hello'}, headers);
  expect(good.status).toBe(200);
  expect(good.headers.get('X-Request-ID')).toMatch(/^[A-Za-z0-9-]{1,64}$/);
  expect((await post('/api/tts', {text:'hello'}, {Authorization:'Bearer ' + token + 'x'})).status).toBe(401);
  expect((await post('/api/text-query', {query:'hello'}, headers)).status).toBe(401);
  expect(global.fetch).toHaveBeenCalledTimes(1);
});
test('global budget rejects requests before spending', async () => {
  process.env.CLINICVOICE_REQUESTS_PER_HOUR = '0';
  global.fetch = jest.fn();
  try {
    expect((await post('/api/tts', {text:'hello'}, {Authorization:'Bearer ' + process.env.CLINICVOICE_SERVICE_KEY})).status).toBe(429);
    expect(global.fetch).not.toHaveBeenCalled();
  } finally {delete process.env.CLINICVOICE_REQUESTS_PER_HOUR;}
});

test('expired browser sessions cannot reach provider', async () => {
  const response = await post('/api/session', {}, {Origin:'http://localhost:5050'});
  const {token} = await response.json();
  global.fetch = jest.fn();
  const now = Date.now();
  const clock = jest.spyOn(Date, 'now').mockReturnValue(now + 16 * 60000);
  try {
    expect((await post('/api/tts', {text:'hello'}, {Authorization:'Bearer ' + token})).status).toBe(401);
    expect(global.fetch).not.toHaveBeenCalled();
  } finally {clock.mockRestore();}
});

test('gateway handles agent timeout without leaking internal details', async () => {
  const response = await post('/api/session', {}, {Origin:'http://localhost:5050'});
  const {token} = await response.json();
  global.fetch = jest.fn().mockRejectedValue(new Error('private upstream detail'));
  const result = await post('/api/agent-query', {query:'Book an appointment',session_id:'test'}, {Authorization:'Bearer '+token});
  expect(result.status).toBe(503);
  expect((await result.json()).error).toBe('The assistant is temporarily unavailable. Please try again.');
});
