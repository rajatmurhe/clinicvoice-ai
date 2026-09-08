const BLOCKED_PATTERNS = [
  /diagnos/i, /prescri/i, /medication/i, /dose/i, /dosage/i, /how much .* (take|dose)/i,
  /is it (cancer|serious|an emergency)/i, /chest pain/i, /cant breathe/i,
  /symptoms of/i, /what disease/i, /am i dying/i, /nhs number/i, /date of birth/i, /social security/i, /verify your identity/i
];

const GREETING_ONLY_PATTERN = /^((hi|hello|hey|good morning|good afternoon|good evening)[\s,!.]*)?(my name is [a-z ]+[.!]?|i(.?m| am) [a-z ]+[.!]?)?[\s,!.]*(i(.?m| am) (studying|a student)( at| in) [a-z ]+[.!]?)?[\s,!.]*$/i;

function checkSafety(query) {
  return BLOCKED_PATTERNS.some(function(pattern) { return pattern.test(query); });
}

async function generateResponse(query, context) {
  if (checkSafety(query)) {
    return {
      response: "I am not able to answer clinical or medical questions like that. Please contact the clinic directly or, if this is an emergency, call your local emergency number.",
      guardrailTriggered: true
    };
  }

  if (GREETING_ONLY_PATTERN.test(query.trim())) {
    return {
      response: "Hello! How can I help you today?",
      guardrailTriggered: false
    };
  }

  const topScore = context[0] ? context[0].score : 0;
  const CONFIDENCE_THRESHOLD = 0.35;

  if (topScore < CONFIDENCE_THRESHOLD) {
    return {
      response: "I don't have that information available. Please call our reception team and they'll be happy to help.",
      guardrailTriggered: false
    };
  }

  const contextText = context.map(function(c) {
    return "Q: " + c.faq.question + "\nA: " + c.faq.answer;
  }).join("\n\n");

  const prompt = "You are a helpful clinic reception assistant. Answer the patients question using ONLY the information below. If the answer isnt in the information provided, say you dont have that information and suggest they call reception. NEVER ask the patient for personal identifying information such as date of birth, NHS number, or ID numbers. NEVER invent policies, procedures, verification steps, or factual claims that are not explicitly stated in the information above. If asked about something not covered in the information, clearly say you do not have that information rather than guessing or making up an answer.\n\nInformation:\n" + contextText + "\n\nPatient question: " + query + "\n\nAnswer in 1-2 short sentences, in a friendly natural tone suitable for speaking aloud:";

  const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + process.env.GROQ_API_KEY
    },
    body: JSON.stringify({
      model: 'openai/gpt-oss-20b',
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.2,
      max_tokens: 300
    })
  });

  const data = await response.json();
  const generatedText = data.choices[0].message.content.trim();

  if (checkSafety(generatedText)) {
    return {
      response: "I am not able to help with that. Please contact the clinic directly.",
      guardrailTriggered: true
    };
  }

  return { response: generatedText, guardrailTriggered: false };
}

module.exports = { generateResponse, checkSafety };
