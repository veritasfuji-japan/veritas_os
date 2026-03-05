import { describe, expect, it } from 'vitest';

import { getBodySizeBytes } from './route';

describe('getBodySizeBytes', () => {
  it('returns ASCII length as bytes', () => {
    expect(getBodySizeBytes('abcd')).toBe(4);
  });

  it('counts multibyte UTF-8 characters correctly', () => {
    expect(getBodySizeBytes('あ')).toBe(3);
    expect(getBodySizeBytes('😀')).toBe(4);
  });
});
