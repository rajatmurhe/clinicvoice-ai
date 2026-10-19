const { getRequestId } = require('./request-context');
const providers = require('./llm-providers');
const tracing = require('./langfuse-tracing');

const BLOCKED_PATTERNS_INPUT = [
  /diagnos/i, /\bprescrib/i, /medication/i, /dose/i, /dosage/i, /how much .* (should|can|could)\s+(i|we|you|he|she|they)?\s*(take|dose)\b/i,
  /is it (cancer|serious|an emergency)/i, /chest pain/i, /cant breathe/i,
  /symptoms of/i, /what disease/i, /am i dying/i, /nhs number/i, /date of birth/i, /social security/i, /verify your identity/i,
  /\bmedicine\b/i, /\bsurgery\b/i, /sore throat|throat is sore/i,
  /\bantibiotic/i, /side effects/i, /\bdizzy\b/i, /\bfever\b/i, /\brash\b/i,
  /what (could it be|is wrong with me)/i,
  /how (do|to) i (treat|cure)/i, /is it safe to/i,
  /\d+\s?mg\b/i,
  /ignore (all|your|the|previous|my) (previous )?(instructions|rules|guidelines|safety)/i,
  /forget your (rules|instructions)/i, /new instructions/i,
  /system prompt|you are now/i, /pretend (you are|to be)|act as/i,
  /(patient|appointment|booking) list/i,
  /appointment details|patient details|patient data|patient records/i,
  /medical records (of|for)/i,
  /(phone number|address|date of birth) of (the )?patient/i,
  /(show|read|give|tell) me (the )?waitlist/i,
  /today'?s bookings/i, /share the clinic schedule|clinic schedule with me/i,
  /skip (the )?(verification|questions)/i,
  /look me up by (name|phone)|look up (my|the) records/i,
  /(do not|don.?t) need to verify/i,
  /allowed to give medical advice|give medical advice/i,
  /खुराक|डोस/i, /निदान/i,
  /कौन स[ीा] दवा|कोणत[ेी] औषध|कोणत्या औषध/i,
  /कितन[ीा] दवा|कितनी खुराक/i,
  /क्या बीमारी|कौन सी बीमारी|मेरी बीमारी|काय आजार|माझा आजार/i,
  /मुझे क्या हुआ/i,
  /दूसरे मरीज़|दुसऱ्या रुग्णाचा|मरीज़ का डेटा|रुग्णाची माहिती/i,
  /मरीज़ों की लिस्ट|रुग्णांची यादी/i
];

// Kept in sync with EMERGENCY_PATTERNS in python-agents/safety.py. These get a
// dedicated emergency message instead of the generic block, in both layers.
const EMERGENCY_PATTERNS = [
  /chest pain/i, /can.?t breathe|cannot breathe/i, /heart attack/i,
  /\bstroke\b/i, /severe bleeding/i, /unconscious/i, /\bsuicid/i,
  /kill myself/i, /end my life/i, /overdos/i,
  /छाती में दर्द|छातीत दुखत/i, /सांस (नहीं|लेने में)|सांस घेता येत नाही|दम बांधत नाही/i,
  /हृदयाचा झटका|हार्ट अटैक/i, /खूप रक्तस्राव|बहुत खून/i
];

const BLOCKED_RESPONSE = 'I am not able to answer clinical or medical questions like that. Please contact the clinic directly or, if this is an emergency, call your local emergency number.';

const EMERGENCY_RESPONSE = 'This sounds like it could be a medical emergency. Please hang up and call your local emergency number, or go to the nearest emergency room right away. I have flagged this call for our team to review.';

const LLM_FALLBACK_RESPONSE = 'I am having trouble reaching the assistant service right now. Please call our reception team and they will help you directly.';

const BLOCKED_PATTERNS_OUTPUT = [
  /you should take/i, /take \d+/i, /recommended dose/i, /i diagnose/i, /you have (cancer|a disease)/i,
  /nhs number/i, /date of birth/i, /social security/i, /verify your identity/i, /please confirm your (date of birth|id)/i
];

const GREETING_ONLY_PATTERN = /^((hi|hello|hey|good morning|good afternoon|good evening)[\s,!.]*)?(my name is [a-z ]+[.!]?|i(.?m| am) [a-z ]+[.!]?)?[\s,!.]*(i(.?m| am) (studying|a student)( at| in) [a-z ]+[.!]?)?[\s,!.]*$/i;

const CONFIDENCE_THRESHOLD = parseFloat(process.env.CLINICVOICE_CONFIDENCE_THRESHOLD || '0.35');

// Evasion resistant second pass, kept in sync with safety.py: invisible
// characters and letter spacing defeat the plain patterns, so both layers
// also check a squeezed copy of the text against high confidence literals.
const INVISIBLE_CHARS = /[\u200b-\u200f\u202a-\u202e\u00ad\ufeff\u2060'\u2019]/g;

const SQUEEZED_BLOCKED = [
  'diagnos', 'prescrib', 'medication', 'dosage', 'symptomsof', 'whatdisease',
  'amidying', 'nhsnumber', 'dateofbirth', 'socialsecurity', 'verifyyouridentity',
  'chestpain', 'cantbreathe', 'cannotbreathe', 'sorethroat', 'throatisore',
  'antibiotic', 'sideeffects', 'surgery', 'medicine', 'overdos',
  'ignoreallprevious', 'forgetyourrules', 'newinstructions', 'systemprompt',
  'patientlist', 'appointmentlist', 'bookinglist', 'patientdata',
  'patientrecords', 'appointmentdetails', 'patientdetails'
];

const SQUEEZED_EMERGENCY = [
  'chestpain', 'heartattack', 'cantbreathe', 'cannotbreathe', 'severebleeding',
  'killmyself', 'endmylife', 'suicid', 'overdos', 'stroke',
  'छातीमेंदर्द', 'छातीतदुखत', 'हृदयाचाझटका', 'हार्टअटैक'
];

function squeezeText(query) {
  return query.replace(/\s+/g, '').replace(INVISIBLE_CHARS, '');
}

function checkSqueezed(list, query) {
  const squeezed = squeezeText(query);
  return list.some(function(word) {
    return squeezed.toLowerCase().indexOf(word.toLowerCase()) !== -1;
  });
}

function checkSafety(query) {
  return BLOCKED_PATTERNS_INPUT.some(function(pattern) { return pattern.test(query); }) ||
    checkSqueezed(SQUEEZED_BLOCKED, query);
}

function checkEmergency(query) {
  return EMERGENCY_PATTERNS.some(function(pattern) { return pattern.test(query); }) ||
    checkSqueezed(SQUEEZED_EMERGENCY, query);
}

function checkOutputSafety(text) {
  return BLOCKED_PATTERNS_OUTPUT.some(function(pattern) { return pattern.test(text); });
}

// Decides everything that can be decided before the LLM call: emergency path,
// input blocklist, greeting short circuit, and the retrieval confidence
// threshold. Used by the live path and by eval-retrieval.js so offline
// evaluation measures exactly the same pre-LLM decisions the deployed service
// makes.
function decidePreLLM(query, context) {
  const top = context && context[0] ? context[0] : null;
  const topScore = top ? top.score : 0;
  const topFaqId = top ? top.faq.id : null;

  if (checkEmergency(query)) {
    return {
      kind: 'emergency',
      response: EMERGENCY_RESPONSE,
      topScore: topScore,
      topFaqId: topFaqId
    };
  }

  if (checkSafety(query)) {
    return {
      kind: 'block',
      response: BLOCKED_RESPONSE,
      topScore: topScore,
      topFaqId: topFaqId
    };
  }

  if (GREETING_ONLY_PATTERN.test(query.trim())) {
    return {
      kind: 'greeting',
      response: 'Hello! How can I help you today?',
      topScore: topScore,
      topFaqId: topFaqId
    };
  }

  if (topScore < CONFIDENCE_THRESHOLD) {
    return {
      kind: 'fallback',
      response: "I don't have that information available. Please call our reception team and they'll be happy to help.",
      topScore: topScore,
      topFaqId: topFaqId
    };
  }

  return { kind: 'llm', topScore: topScore, topFaqId: topFaqId };
}

async function generateResponse(query, context, options = {}) {
  const trace = options.trace || null;
  const pre = decidePreLLM(query, context);

  const inputValidation = tracing.startChild(trace, 'faq-input-and-retrieval-validation', {
    input: tracing.contentValue(query, { redacted: true, character_count: query.length }),
    output: {
      decision: pre.kind,
      retrieval_score: pre.topScore,
      confidence_threshold: CONFIDENCE_THRESHOLD,
      top_faq_id: pre.topFaqId,
      input_safety_passed: pre.kind !== 'block' && pre.kind !== 'emergency',
      retrieval_confident: pre.topScore >= CONFIDENCE_THRESHOLD,
      answer_generation_allowed: pre.kind === 'llm'
    },
    metadata: { validator: 'input-safety-plus-retrieval-confidence' }
  }, 'guardrail');
  tracing.endObservation(inputValidation);

  if (pre.kind !== 'llm') {
    return {
      response: pre.response,
      guardrailTriggered: pre.kind === 'block' || pre.kind === 'emergency'
    };
  }

  const contextText = context.map(function(c) {
    return "Q: " + c.faq.question + "\nA: " + c.faq.answer;
  }).join("\n\n");

  const prompt = "You are a helpful clinic reception assistant. Answer the patients question using ONLY the information below. If the answer isnt in the information provided, say you dont have that information and suggest they call reception. NEVER ask the patient for personal identifying information such as date of birth, NHS number, or ID numbers. NEVER invent policies, procedures, verification steps, or factual claims that are not explicitly stated in the information above. If asked about something not covered in the information, clearly say you do not have that information rather than guessing or making up an answer. Respond in the same language the patient used. If they wrote in Hindi, respond in Hindi. If they wrote in Marathi, respond in Marathi. Otherwise respond in English.\n\nInformation:\n" + contextText + "\n\nPatient question: " + query + "\n\nAnswer in 1-2 short sentences, in a friendly natural tone suitable for speaking aloud:";

  // Provider layer (Groq default, Gemini fallback). Any provider failure is
  // a sanitized category here, never a raw error, and the patient gets the
  // same safe reception-team fallback whichever provider is configured.
  let result;
  const providerStarted = Date.now();
  const generation = tracing.startChild(trace, 'faq-answer-generation', {
    input: tracing.contentValue(prompt, { redacted: true, character_count: prompt.length }),
    metadata: { provider_selection: process.env.LLM_PROVIDER || 'groq', failover_enabled: true }
  });
  const providerAttempts = new Map();
  try {
    result = await providers.generate(prompt, {
      onAttempt: function(attempt) {
        if (attempt.phase === 'start') {
          providerAttempts.set(attempt.provider, tracing.startChild(generation, attempt.provider + '-generation', {
            model: attempt.modelId,
            input: tracing.contentValue(prompt, { redacted: true, character_count: prompt.length }),
            metadata: { provider: attempt.provider }
          }, 'generation'));
          return;
        }
        const attemptObservation = providerAttempts.get(attempt.provider);
        tracing.updateObservation(attemptObservation, {
          ...(attempt.status === 'success' ? {
            output: tracing.contentValue(attempt.response || '', { redacted: true, character_count: (attempt.response || '').length }),
            ...(attempt.usageDetails && Object.keys(attempt.usageDetails).length ? { usageDetails: attempt.usageDetails } : {})
          } : {
            level: 'ERROR',
            statusMessage: attempt.errorCategory || 'provider_error',
            output: { error_category: attempt.errorCategory || 'provider_error' }
          }),
          metadata: {
            provider: attempt.provider,
            provider_latency_ms: attempt.latencyMs,
            total_tokens: attempt.usageTokens ?? null
          }
        });
        tracing.endObservation(attemptObservation);
      }
    });
    result.provider_latency_ms = Date.now() - providerStarted;
  } catch (err) {
    tracing.updateObservation(generation, {
      level: 'ERROR',
      statusMessage: err instanceof providers.ProviderError ? err.category : 'provider_unreachable',
      metadata: { provider_latency_ms: Date.now() - providerStarted }
    });
    tracing.endObservation(generation);
    // The LLM being down must never surface as a 500 or a stack trace. A clear
    // fallback with a human handoff keeps the assistant usable.
    return {
      response: LLM_FALLBACK_RESPONSE,
      guardrailTriggered: false,
      error: 'llm_unreachable',
      error_category: err instanceof providers.ProviderError ? err.category : 'unreachable',
      provider: process.env.LLM_PROVIDER || 'groq',
      provider_latency_ms: Date.now() - providerStarted
    };
  }

  tracing.updateObservation(generation, {
    output: tracing.contentValue(result.text, { redacted: true, character_count: result.text.length }),
    metadata: {
      provider: result.provider,
      provider_latency_ms: result.provider_latency_ms,
      total_tokens: result.usageTokens,
      provider_attempt_count: (result.attempts || []).length
    }
  });
  tracing.endObservation(generation);

  if (checkOutputSafety(result.text)) {
    const outputValidation = tracing.startChild(trace, 'faq-output-safety-validation', {
      output: { passed: false, decision: 'blocked' },
      metadata: { validator: 'generated-answer-safety' }
    }, 'guardrail');
    tracing.endObservation(outputValidation);
    return {
      response: "I am not able to help with that. Please contact the clinic directly.",
      guardrailTriggered: true
    };
  }

  const outputValidation = tracing.startChild(trace, 'faq-output-safety-validation', {
    output: { passed: true, decision: 'accepted' },
    metadata: { validator: 'generated-answer-safety' }
  }, 'guardrail');
  tracing.endObservation(outputValidation);

  return {
    response: result.text,
    guardrailTriggered: false,
    provider: result.provider,
    model_id: result.modelId,
    provider_latency_ms: result.provider_latency_ms,
    usage_tokens: result.usageTokens
  };
}

module.exports = { generateResponse, checkSafety, checkEmergency, decidePreLLM, CONFIDENCE_THRESHOLD };
