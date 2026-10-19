describe('optional Langfuse tracing', function() {
  afterEach(function() {
    delete process.env.LANGFUSE_ENABLED;
    delete process.env.LANGFUSE_PUBLIC_KEY;
    delete process.env.LANGFUSE_SECRET_KEY;
    delete process.env.LANGFUSE_TRACE_CONTENT;
    jest.resetModules();
  });

  test('tracing stays off without explicit enablement and credentials', function() {
    process.env.LANGFUSE_ENABLED = 'true';
    jest.isolateModules(function() {
      const tracing = require('../langfuse-tracing');
      expect(tracing.enabled).toBe(false);
      expect(tracing.startFaqTrace({ query: 'sensitive question' })).toBeNull();
      expect(tracing.contentValue('sensitive question', { redacted: true })).toEqual({ redacted: true });
    });
  });

  test('content recording requires its own explicit opt-in', function() {
    process.env.LANGFUSE_TRACE_CONTENT = 'false';
    jest.isolateModules(function() {
      const tracing = require('../langfuse-tracing');
      expect(tracing.traceContent).toBe(false);
      expect(tracing.contentValue('sensitive question', { redacted: true })).toEqual({ redacted: true });
    });
  });
});
