// Per-request context shared across async calls (used for request id logging).
const { AsyncLocalStorage } = require('node:async_hooks');

const storage = new AsyncLocalStorage();

function runWithRequestId(requestId, fn) {
  return storage.run(requestId, fn);
}

function getRequestId() {
  return storage.getStore() || null;
}

module.exports = { runWithRequestId, getRequestId };
