// The prompt and readout of d3 (src/classify/providers/d3Format.ts) against the golden prompts that the OFFICIAL d3_format.py and the
// chat template of vllm-sr/d3-edge (revision bee5e872) produced (bench/d3/golden_prompts.py): byte for byte.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { D3_CODES, D3_MAX_OPTIONS, d3Answer, d3Options, d3Probabilities, d3Render, d3UserPrompt, pyJsonDumps } from '../src/classify/providers/d3Format';
import type { Question } from '../src/classify/jevAdapter';

interface Golden { request: string; key: string; state: unknown; question: Question; prompt: string }
const golden = JSON.parse(readFileSync(fileURLToPath(new URL('./fixtures/d3-golden-prompts.json', import.meta.url)), 'utf8')) as Golden[];
const config = JSON.parse(readFileSync(fileURLToPath(new URL('./fixtures/d3-decision-config-codes.json', import.meta.url)), 'utf8')) as { codes: string[] };

describe('d3 answer codes', () => {
  it('are the 255 codes of decision_config.json, not plain A..ZZ', () => {
    expect(D3_CODES).toHaveLength(D3_MAX_OPTIONS);
    expect([...D3_CODES]).toEqual(config.codes);
    expect(D3_CODES.slice(0, 3)).toEqual(['A', 'B', 'C']);
    expect(D3_CODES).not.toContain('BQ'); // a code that is not one token of the tokenizer is skipped
    expect(new Set(D3_CODES).size).toBe(255);
  });
});

describe('d3 prompts match the official ones', () => {
  it('has golden prompts for text, JSON, unicode, many options, none descriptions and score levels', () => {
    expect(golden.length).toBeGreaterThanOrEqual(12);
    expect(golden.some((g) => g.question.type === 'score')).toBe(true);
    expect(golden.some((g) => g.question.type === 'choice' && Object.keys(g.question.criteria).length === 60)).toBe(true);
  });
  for (const g of golden) {
    it(`${g.request} / ${g.key}`, () => {
      expect(d3Render(g.state as never, g.question)).toBe(g.prompt);
    });
  }
});

describe('python-compatible JSON text', () => {
  it('uses ", " and ": " separators, keeps unicode, writes small floats as Python does', () => {
    expect(pyJsonDumps({ a: 1, b: [1, 2], c: 'x' })).toBe('{"a": 1, "b": [1, 2], "c": "x"}');
    expect(pyJsonDumps({ k: 'Wand über 中文' })).toBe('{"k": "Wand über 中文"}');
    expect(pyJsonDumps(1e-7)).toBe('1e-07');
    expect(pyJsonDumps(0.00001)).toBe('1e-05');
    expect(pyJsonDumps(0.0001)).toBe('0.0001');
    expect(pyJsonDumps(3.5)).toBe('3.5');
    expect(pyJsonDumps({ a: null, b: undefined, c: true })).toBe('{"a": null, "c": true}');
  });
});

describe('d3 options and readout', () => {
  it('a choice shows "key: description", or the key alone with no description', () => {
    const q: Question = { type: 'choice', instructions: 'x', criteria: { a: 'Alpha', b: 'Beta' } };
    expect(d3Options(q)).toEqual({ keys: ['a', 'b'], texts: ['a: Alpha', 'b: Beta'] });
  });
  it('a yes/no question has the options false and true with the default descriptions', () => {
    expect(d3Options({ type: 'noul', instructions: 'Is it?' })).toEqual({ keys: ['false', 'true'], texts: ['No / false', 'Yes / true'] });
  });
  it('rejects a question with more options than codes', () => {
    const criteria = Object.fromEntries(Array.from({ length: 256 }, (_, i) => [`k${i}`, 'x']));
    expect(() => d3UserPrompt('s', { type: 'choice', instructions: 'x', criteria })).toThrow(/1 to 255/);
  });
  it('masks the logits beyond the options and normalises over the options', () => {
    const p = d3Probabilities([1, 2, 3, 99, 99], 3);
    expect(p).toHaveLength(3);
    expect(p.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 12);
    expect(p[2]).toBeGreaterThan(p[1]!);
  });
  it('gives the answer with probabilities, the raw logits and, for a yes/no, the log-odds', () => {
    const q: Question = { type: 'choice', instructions: 'x', criteria: { a: 'A', b: 'B', c: 'C' } };
    const a = d3Answer(q, [0, 2, 1]);
    expect(a).toMatchObject({ type: 'choice', choice: 'b' });
    if (a.type === 'choice') {
      expect(Object.values(a.probabilities).reduce((x, y) => x + y, 0)).toBeCloseTo(1, 12);
      expect(a.confidence).toBeCloseTo(a.probabilities['b']!, 12);
      expect(a.logits).toEqual({ a: 0, b: 2, c: 1 });
    }
    const y = d3Answer({ type: 'noul', instructions: 'x' }, [1, 3]);
    expect(y).toMatchObject({ type: 'noul', logit: 2 });
    if (y.type === 'noul') expect(y.noul).toBeCloseTo(1 / (1 + Math.exp(-2)), 12);
  });
});
