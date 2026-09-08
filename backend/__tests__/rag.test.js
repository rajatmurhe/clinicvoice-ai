const { cosineSimilarity } = require('../rag');

describe('cosineSimilarity', () => {
  test('identical vectors have similarity 1', () => {
    const a = [1, 0, 0];
    const b = [1, 0, 0];
    expect(cosineSimilarity(a, b)).toBeCloseTo(1.0);
  });

  test('orthogonal vectors have similarity 0', () => {
    const a = [1, 0, 0];
    const b = [0, 1, 0];
    expect(cosineSimilarity(a, b)).toBeCloseTo(0.0);
  });

  test('opposite vectors have similarity -1', () => {
    const a = [1, 0, 0];
    const b = [-1, 0, 0];
    expect(cosineSimilarity(a, b)).toBeCloseTo(-1.0);
  });

  test('similar-direction vectors score highly', () => {
    const a = [1, 1, 0];
    const b = [2, 2, 0];
    expect(cosineSimilarity(a, b)).toBeCloseTo(1.0);
  });
});
