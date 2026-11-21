// The animation script docs: the formal grammar and the coordinator guide. Every ```xrayanim block of the two pages must
// compile with the real compiler, every keyword of the language must appear in the grammar, and the limits table must
// state the values the code uses.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { compileScript, LIMITS } from '../src/anim/script/compiler';
import type { CompileOptions } from '../src/anim/script/compiler';
import { STATEMENT_WORDS, MODE_WORDS, MAX_NESTING } from '../src/anim/script/parser';
import { MAX_SOURCE_CHARS, MAX_SOURCE_LINES } from '../src/anim/script/lexer';
import { KEYWORDS as QUERY_KEYWORDS } from '../src/query/lexer';
import { WEB } from './revision-helpers';

const GRAMMAR = 'docs-features/animation-script-grammar.md';
const GUIDE = 'docs-features/animation-script-guide.md';
const read = (f: string): string => readFileSync(resolve(WEB, f), 'utf8');

/** The fenced blocks marked xrayanim of a page, with the line they start on. */
function xrayBlocks(text: string): Array<{ code: string; line: number }> {
  const out: Array<{ code: string; line: number }> = [];
  const re = /^```xrayanim\n([\s\S]*?)^```$/gm;
  for (const m of text.matchAll(re)) {
    const line = text.slice(0, m.index).split('\n').length;
    out.push({ code: m[1]!, line });
  }
  return out;
}

/** The fenced blocks of language ebnf of a page. */
function ebnfText(text: string): string {
  return [...text.matchAll(/^```ebnf\n([\s\S]*?)^```$/gm)].map((m) => m[1]).join('\n');
}

// Example compile options: a fake model with three elements and two selection sets. Without a model `repeat for each`
// cannot run, so the examples are compiled against these names. Setting paths are not checked (a warning, not an error).
const FAKE_MODEL: CompileOptions = { resolve: () => ['g1', 'g2', 'g3'], setNames: () => ['Pumps', 'Walls'] };

describe('animation script docs: every example compiles', () => {
  for (const page of [GRAMMAR, GUIDE]) {
    it(`${page}: every xrayanim block compiles with zero errors`, () => {
      const blocks = xrayBlocks(read(page));
      expect(blocks.length, 'at least one example block').toBeGreaterThan(0);
      for (const b of blocks) {
        const r = compileScript(b.code, FAKE_MODEL);
        const errors = r.errors.filter((e) => e.severity === 'error');
        expect(errors, `${page} line ${b.line}:\n${b.code}`).toEqual([]);
        expect(r.score, `${page} line ${b.line}`).not.toBeNull();
      }
    });
  }

  it('the guide has between six and eight recipes, each a complete script', () => {
    const recipes = read(GUIDE).match(/^### 11\.\d+ .+$/gm) ?? [];
    expect(recipes.length).toBeGreaterThanOrEqual(6);
    expect(recipes.length).toBeLessThanOrEqual(8);
    expect(xrayBlocks(read(GUIDE)).length).toBeGreaterThanOrEqual(recipes.length + 3);
  });

  it('the first script of the guide is three lines of statements plus a comment', () => {
    const first = xrayBlocks(read(GUIDE))[0]!.code.split('\n').filter((l) => l.trim() !== '' && !l.trim().startsWith('--'));
    expect(first).toHaveLength(3);
  });
});

/** Words of the language that the grammar must show as quoted keywords. The statement, mode and criteria words come from the
 *  source; the others are the option, unit, element and loop words that the parser matches by name. */
const PARSER_WORDS = [
  'to', 'view', 'preset', 'over', 'ease', 'margin', 'fading', 'for', 'with', 'about', 'into', 'times', 'time', 'in', 'each',
  'linear', 'out', 'inout', 'inoutsine', 's', 'sec', 'secs', 'second', 'seconds', 'degree', 'degrees', 'deg',
  'where', 'class', 'classes', 'set', 'sets', 'the', 'selection', 'everything', 'it', 'elements', 'element', 'nothing', 'none',
  'index', 'true', 'false', 'on', 'off', 'yes', 'no', 'end', 'together',
];

describe('animation script grammar: keywords and limits', () => {
  const grammar = read(GRAMMAR);
  const ebnf = ebnfText(grammar);

  it('quotes every keyword of the language in an ebnf block', () => {
    const keywords = new Set<string>([...STATEMENT_WORDS, ...MODE_WORDS, ...QUERY_KEYWORDS.values(), ...PARSER_WORDS].map((w) => w.toLowerCase()));
    const missing = [...keywords].filter((w) => !new RegExp(`"${w}"`, 'i').test(ebnf));
    expect(missing).toEqual([]);
  });

  it('lists no stale keyword: each word of the explicit list is in the parser, lexer or compiler source', () => {
    const src = ['parser.ts', 'lexer.ts', 'compiler.ts'].map((f) => read(`src/anim/script/${f}`)).join('\n') + read('src/query/parser.ts');
    const query = new Set([...QUERY_KEYWORDS].map((w) => w.toLowerCase()));
    const stale = PARSER_WORDS.filter((w) => !query.has(w) && !src.includes(`'${w}'`));
    expect(stale).toEqual([]);
  });

  it('states the limits of the code', () => {
    // A value may be written with a space as thousands separator (20 000) or with none (20000).
    const values = [LIMITS.maxIterations, LIMITS.maxSteps, LIMITS.maxCues, LIMITS.maxDuration, MAX_SOURCE_CHARS, MAX_SOURCE_LINES, MAX_NESTING];
    for (const v of values) {
      const pattern = String(v).replace(/\B(?=(\d{3})+$)/g, '[ ,\u00a0]?');
      expect(new RegExp(pattern).test(grammar), String(v)).toBe(true);
    }
  });

  it('has the timing table and the criteria rules', () => {
    expect(grammar).toMatch(/Each statement starts when the one before it has ended/);
    expect(grammar).toMatch(/## 8\. Criteria/);
    expect(grammar).toMatch(/Stop words: over ease margin fading for with about/);
  });
});

describe('links and pointers', () => {
  it('the reference links both new pages', () => {
    const ref = read('docs-features/animation-script.md');
    expect(ref).toContain('animation-script-grammar.md');
    expect(ref).toContain('animation-script-guide.md');
  });
  it('the README names both pages in one line', () => {
    const lines = read('../README.md').split('\n').filter((l) => l.includes('animation-script-grammar.md') && l.includes('animation-script-guide.md'));
    expect(lines).toHaveLength(1);
  });
});
