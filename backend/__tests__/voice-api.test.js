const nativeFetch = global.fetch;
const app = require('../server-cloud');
let server, base;
beforeAll(async () => {
  server = await new Promise(resolve => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  base = `http://127.0.0.1:${server.address().port}`;
});
afterAll(async () => { await new Promise(resolve => server.close(resolve)); });
afterEach(() => { global.fetch = nativeFetch; });
const post = (path, body) => nativeFetch(base + path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});

test.each([null, 123, {}, '   '])('invalid text input returns 400: %p', async query => {
  const response = await post('/api/text-query', {query});
  expect(response.status).toBe(400);
});
test('short recording is rejected without contacting the provider', async () => {
  global.fetch = jest.fn();
  expect((await post('/api/transcribe', {audio:'data:audio/wav;base64,YQ=='})).status).toBe(400);
  expect(global.fetch).not.toHaveBeenCalled();
});
test('normal recording over 100KB transcribes and preserves MP4 format and language', async () => {
  global.fetch = jest.fn().mockResolvedValue({ok:true,json:async()=>({text:'Hello clinic'})});
  const audio = 'data:audio/mp4;base64,' + Buffer.alloc(160000, 1).toString('base64');
  const response = await post('/api/transcribe', {audio,language:'mr'});
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({text:'Hello clinic'});
  const form = global.fetch.mock.calls[0][1].body;
  expect(form.get('file').name).toBe('speech.m4a');
  expect(form.get('file').type).toBe('audio/mp4');
  expect(form.get('language')).toBe('mr');
});
test('provider timeout returns a usable transcription fallback', async () => {
  global.fetch = jest.fn().mockRejectedValue(Object.assign(new Error('timeout'),{name:'TimeoutError'}));
  const response = await post('/api/transcribe', {audio:Buffer.alloc(1000).toString('base64')});
  expect(response.status).toBe(503);
  expect((await response.json()).error).toMatch(/type your question/);
});
test('oversized recording returns JSON instead of an HTML error page', async () => {
  const response = await post('/api/transcribe', {audio:'a'.repeat(10*1024*1024)});
  expect(response.status).toBe(413);
  expect((await response.json()).error).toMatch(/shorter/);
});
test('malformed JSON returns 400', async () => {
  const response = await nativeFetch(base+'/api/transcribe', {method:'POST',headers:{'Content-Type':'application/json'},body:'{'});
  expect(response.status).toBe(400);
  expect((await response.json()).error).toMatch(/JSON/);
});
