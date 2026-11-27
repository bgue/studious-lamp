import { describe, expect, it } from 'vitest';
import { isRangeInput } from '../src/plugins/flythrough';

describe('Escape while a slider has the focus', () => {
  it('treats a range input as taking no text, other inputs as before', () => {
    expect(isRangeInput({ tagName: 'INPUT', type: 'range' } as unknown as EventTarget)).toBe(true);
    expect(isRangeInput({ tagName: 'INPUT', type: 'RANGE' } as unknown as EventTarget)).toBe(true);
    expect(isRangeInput({ tagName: 'INPUT', type: 'text' } as unknown as EventTarget)).toBe(false);
    expect(isRangeInput({ tagName: 'TEXTAREA' } as unknown as EventTarget)).toBe(false);
    expect(isRangeInput(null)).toBe(false);
  });
});
