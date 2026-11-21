// The docs page, the reference, the help texts and the leak rule of the animation script feature.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { EXAMPLES } from '../src/anim/script/examples';
import { ELEMENT_HELP, STATEMENT_HELP, TIMING_NOTES, referenceMarkdown } from '../src/anim/script/scriptHelp';
import { STATEMENT_WORDS, parseScript } from '../src/anim/script/parser';
import { lookupHelp, SCRIPT_HELP_KEYS, SCRIPT_RULES, DOM_CANDIDATES } from '../src/ui/help';
import { WEB } from './revision-helpers';

const read = (f: string): string => readFileSync(resolve(WEB, f), 'utf8');
const walk = (dir: string): string[] => readdirSync(dir).flatMap((f) => { const p = resolve(dir, f); return statSync(p).isDirectory() ? walk(p) : p.endsWith('.ts') ? [p] : []; });

describe('statement reference', () => {
  it('covers every statement word, with a one-line description and a parseable example', () => {
    const first = new Set(STATEMENT_HELP.flatMap((s) => s.example.split('\n').map((l) => /^\s*(\w+)/.exec(l)?.[1]?.toLowerCase() ?? '')));
    for (const w of STATEMENT_WORDS.filter((x) => x !== 'end')) expect(first.has(w), w).toBe(true);
    expect(new Set(STATEMENT_HELP.map((s) => s.id)).size).toBe(STATEMENT_HELP.length);
    for (const s of STATEMENT_HELP) {
      expect(s.summary.includes('\n'), s.id).toBe(false);
      expect(s.summary.length, s.id).toBeGreaterThan(10);
      const r = parseScript(s.example);
      expect(r.errors, `${s.id}: ${s.example}`).toEqual([]);
      expect(r.program.body.length, s.id).toBeGreaterThan(0);
    }
    for (const e of ELEMENT_HELP) expect(parseScript(`select ${e.example}`).errors, e.example).toEqual([]);
  });
});

describe('docs-features/animation-script.md', () => {
  const doc = read('docs-features/animation-script.md');
  it('holds the generated statement list', () => {
    const m = /<!-- statements:start -->\n([\s\S]*?)\n<!-- statements:end -->/.exec(doc);
    expect(m, 'markers').not.toBeNull();
    expect(m![1]).toBe(referenceMarkdown());
  });
  it('states the timing rules and the limits of the reference', () => {
    expect(doc).toMatch(/Each starts when the one before it has ended/);
    for (const n of [/1 hour/, /5000 cues/, /500 times/]) expect(doc).toMatch(n);
    expect(TIMING_NOTES.length).toBeGreaterThan(3);
  });
  it('names the editor features and the leak rule', () => {
    for (const w of ['Problems', 'Run, Pause, Stop', 'Examples', 'Export', 'Import', '.xrayanim', 'xray.anim.', 'never']) expect(doc, w).toContain(w);
  });
  it('shows the example scripts of the menu by their titles', () => {
    expect(EXAMPLES.length).toBeGreaterThanOrEqual(3);
  });
  it('is linked from the README and from the right sidebar page', () => {
    expect(readFileSync(resolve(WEB, '../README.md'), 'utf8')).toContain('web/docs-features/animation-script.md');
    expect(read('docs-features/right-sidebar.md')).toContain('animation-script.md');
  });
});

describe('help for the Script tab', () => {
  it('has a text for every key, the rule hands the key through and the tab button has one', () => {
    for (const k of [...SCRIPT_HELP_KEYS, 'Right sidebar/Script tab']) expect(lookupHelp(k), k).toBeDefined();
    const fake = { getAttribute: (n: string) => (n === 'data-help-key' ? 'Script tab/Run' : null) } as unknown as Element;
    expect(SCRIPT_RULES[0]!.keys(fake, '')).toEqual(['Script tab/Run']);
    expect(SCRIPT_RULES[0]!.title(fake, '')).toBe('Run');
    expect(DOM_CANDIDATES).toContain('[data-help-key^="Script tab/"]');
  });
  it('names in the panel source only keys that the list holds, and every key is used', () => {
    const src = read('src/anim/scriptPanel.ts');
    const used = new Set<string>();
    for (const m of src.matchAll(/HELP\('([^']+)'\)/g)) used.add(`Script tab/${m[1]}`);
    for (const m of src.matchAll(/'(Script tab\/[^']+)'/g)) used.add(m[1]!);
    for (const k of used) expect(SCRIPT_HELP_KEYS, k).toContain(k);
    for (const k of SCRIPT_HELP_KEYS) expect([...used], k).toContain(k);
    const plugin = read('src/plugins/animScript.ts');
    expect(plugin).toContain("helpKey: 'Right sidebar/Script tab'");
    expect(plugin).toContain('order: 40');
    expect(plugin).toContain('width: 420');
  });
});

describe('leak rule: scripts are user text', () => {
  const files = walk(resolve(WEB, 'src'));
  const own = (p: string): boolean => /\/src\/anim\/(script\/|scriptPanel|scriptStore)/.test(p) || /\/src\/plugins\/animScript\.ts$/.test(p);

  it('no other module names the script storage or imports the script modules', () => {
    for (const f of files.filter((p) => !own(p))) {
      const text = readFileSync(f, 'utf8');
      expect(text.includes('xray.anim'), `${f} names the script store`).toBe(false);
      expect(/from '[./]*(?:anim\/)?script\//.test(text) || /from '[./]*anim\/script/.test(text), `${f} imports the script modules`).toBe(false);
    }
  });

  it('the params document, links, views, presets and packing never read the store or the script plugin', () => {
    for (const f of ['src/ui/params.ts', 'src/views/model.ts', 'src/views/capture.ts', 'src/presets/model.ts', 'src/presets/engine.ts', 'tools/xray-pack.mjs']) {
      const text = read(f);
      expect(text, f).not.toMatch(/scriptStore|__xrayScript|xray\.anim|animScript/);
    }
    // no params section is registered for scripts
    expect(read('src/plugins/animScript.ts')).not.toMatch(/registerParamSection/);
    expect(read('src/anim/scriptPanel.ts')).not.toMatch(/registerParamSection/);
  });

  it('the pure language modules use no storage, network, location, eval or DOM', () => {
    for (const f of files.filter((p) => /\/src\/anim\/script\//.test(p))) {
      const text = readFileSync(f, 'utf8').replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
      expect(/localStorage|sessionStorage|indexedDB|fetch\(|XMLHttpRequest|WebSocket|location\.|document\.|window\.|\beval\(|new Function|import\(/.test(text), `${f}`).toBe(false);
    }
  });

  it('the store module touches only the storage it is given', () => {
    const text = read('src/anim/scriptStore.ts').replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
    expect(/localStorage|sessionStorage|document\.|window\./.test(text)).toBe(false);
  });
});
