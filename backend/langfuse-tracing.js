// Optional Langfuse tracing for the FAQ pipeline. Content is excluded unless
// LANGFUSE_TRACE_CONTENT=true because clinic questions may contain health data.
let enabled = process.env.LANGFUSE_ENABLED === 'true' &&
  Boolean(process.env.LANGFUSE_PUBLIC_KEY && process.env.LANGFUSE_SECRET_KEY);
const traceContent = process.env.LANGFUSE_TRACE_CONTENT === 'true';

let sdk = null;
let startObservation = null;
if (enabled) {
  try {
    const { NodeSDK } = require('@opentelemetry/sdk-node');
    const { LangfuseSpanProcessor } = require('@langfuse/otel');
    ({ startObservation } = require('@langfuse/tracing'));
    sdk = new NodeSDK({ spanProcessors: [new LangfuseSpanProcessor()] });
    sdk.start();
  } catch (error) {
    // A telemetry exporter must never prevent the FAQ API from starting.
    process.stderr.write(JSON.stringify({
      event: 'langfuse_init_failed',
      error_type: error && error.name ? error.name : 'Error'
    }) + '\n');
    enabled = false;
  }
}

function contentValue(value, redactedValue) {
  return traceContent ? value : redactedValue;
}

function startFaqTrace({ requestId, clinicId, query }) {
  if (!enabled || !startObservation) return null;
  try {
    return startObservation('clinicvoice-faq-run', {
      input: contentValue(query, { redacted: true, character_count: query.length }),
      metadata: {
        request_id: requestId || null,
        clinic_id: clinicId || 'default',
        content_recording: traceContent
      }
    });
  } catch (_) {
    return null;
  }
}

function startChild(parent, name, attributes, asType) {
  if (!parent) return null;
  try {
    return asType
      ? parent.startObservation(name, attributes || {}, { asType })
      : parent.startObservation(name, attributes || {});
  } catch (_) {
    return null;
  }
}

function updateObservation(observation, attributes) {
  if (!observation) return;
  try { observation.update(attributes); } catch (_) { /* telemetry is best effort */ }
}

function endObservation(observation) {
  if (!observation) return;
  try { observation.end(); } catch (_) { /* telemetry is best effort */ }
}

async function shutdown() {
  if (sdk) {
    try { await sdk.shutdown(); } catch (_) { /* best effort during shutdown */ }
  }
}

module.exports = {
  enabled,
  traceContent,
  contentValue,
  startFaqTrace,
  startChild,
  updateObservation,
  endObservation,
  shutdown
};
