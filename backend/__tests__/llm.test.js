const { checkSafety } = require('../llm');

describe('checkSafety (input/output guardrail)', () => {
  test('blocks direct medication dose questions', () => {
    expect(checkSafety('What dose of ibuprofen should I take?')).toBe(true);
  });

  test('blocks symptom questions', () => {
    expect(checkSafety('What are the symptoms of a heart attack?')).toBe(true);
  });

  test('blocks requests for identity verification details', () => {
    expect(checkSafety('Can you confirm your date of birth and NHS number?')).toBe(true);
  });

  test('allows normal FAQ questions', () => {
    expect(checkSafety('What are your opening hours?')).toBe(false);
  });

  test('allows booking requests', () => {
    expect(checkSafety('I would like to book an appointment')).toBe(false);
  });

  test('allows simple greetings', () => {
    expect(checkSafety('Hello, my name is Rajat')).toBe(false);
  });
});
