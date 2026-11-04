import { describe, expect, it } from 'vitest';
import { CONTROL_HELP, FOLDER_HELP, GLOSSARY, HELP } from '../src/ui/helpText';
import { fillEntry, popoverLines } from '../src/ui/help';

/** Split into sentences. A full stop inside a number (0.5) is not followed by a space, so it stays. */
function sentences(text: string): string[] {
  return text.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);
}
const words = (s: string): number => s.split(/\s+/).filter(Boolean).length;

// Words that end in "ing" and are not gerunds, if a sentence ever needs to start with one.
const NOT_GERUNDS = new Set<string>([]);
const startsWithGerund = (s: string): boolean => {
  const w = s.split(/\s+/)[0]!.replace(/[^A-Za-z]/g, '');
  return /ing$/i.test(w) && w.length > 4 && !NOT_GERUNDS.has(w.toLowerCase());
};

const SPELLED = /\b(one|two|three|four|five|six|seven|eight|nine|ten)\b/i;
// The Use line is an instruction: it must not open with a noun phrase.
const NOT_IMPERATIVE_START = /^(the|this|it|a|an|there|you|your|they|these)\b/i;

describe('help texts', () => {
  const entries = Object.entries(HELP);

  it('covers the folders and the controls (no key lost in the merge)', () => {
    expect(entries.length).toBe(Object.keys(FOLDER_HELP).length + Object.keys(CONTROL_HELP).length);
    expect(entries.length).toBeGreaterThan(100);
  });

  it('has the four fields on every entry', () => {
    for (const [key, e] of entries) {
      for (const f of ['intent', 'impact', 'use', 'ref'] as const) {
        expect(typeof e[f], `${key}.${f}`).toBe('string');
        expect(e[f].trim().length, `${key}.${f}`).toBeGreaterThan(0);
      }
    }
  });

  it('keeps every sentence at 20 words or fewer', () => {
    for (const [key, e] of entries) {
      for (const f of ['intent', 'impact', 'use'] as const) {
        for (const s of sentences(e[f])) expect(words(s), `${key}.${f}: ${s}`).toBeLessThanOrEqual(20);
      }
    }
    for (const g of GLOSSARY) for (const s of sentences(g.definition)) expect(words(s), `glossary ${g.term}: ${s}`).toBeLessThanOrEqual(20);
  });

  it('starts no sentence with a gerund', () => {
    for (const [key, e] of entries) {
      for (const f of ['intent', 'impact', 'use'] as const) {
        for (const s of sentences(e[f])) expect(startsWithGerund(s), `${key}.${f}: ${s}`).toBe(false);
      }
    }
  });

  it('has no "e.g.", no "etc" and no parentheses', () => {
    const texts = [
      ...entries.flatMap(([k, e]) => [`${k}|${e.intent}`, `${k}|${e.impact}`, `${k}|${e.use}`, `${k}|${e.ref}`]),
      ...GLOSSARY.map((g) => `${g.term}|${g.definition}`),
    ];
    for (const t of texts) {
      expect(t, t).not.toMatch(/e\.g\./i);
      expect(t, t).not.toMatch(/\betc\b/i);
      expect(t.slice(t.indexOf('|') + 1), t).not.toMatch(/[()]/);
    }
  });

  it('ends every sentence with a full stop and spells counts as digits', () => {
    for (const [key, e] of entries) {
      for (const f of ['intent', 'use'] as const) {
        expect(e[f], `${key}.${f}`).toMatch(/[.]$/);
        expect(e[f], `${key}.${f}`).not.toMatch(SPELLED);
      }
      expect(e.impact, `${key}.impact`).toMatch(/[.]$/);
    }
  });

  it('opens each Use line with a verb, not a noun phrase', () => {
    for (const [key, e] of entries) expect(e.use, key).not.toMatch(NOT_IMPERATIVE_START);
  });

  it('starts every Ref with "Report:" and names a report section', () => {
    const sections = [
      'Purpose', 'Design rationale', 'Terminology', 'Algorithm 1', 'Algorithm 2', 'Rendering in Bonsai/Blender',
      'Parameters and defaults', 'Worked example', 'Limitations and extensions', 'Onboarding checklist',
      'Appendix A', 'Appendix B', 'Appendix C', 'Appendix D', 'Appendix E', 'Appendix F', 'Appendix G', 'Appendix H', 'Appendix I', 'Appendix J', 'Appendix K', 'Appendix L',
    ];
    for (const [key, e] of entries) {
      expect(e.ref, key).toMatch(/^Report: /);
      expect(sections.some((s) => e.ref.startsWith(`Report: ${s}`)), `${key}: ${e.ref}`).toBe(true);
    }
  });

  it('has a text for the settings named in the task', () => {
    const must = [
      'Classification (Alg 1)/bufferBase', 'Sightlines (Alg 2)/occluderScope', 'Sightlines (Alg 2)/farWeight',
      'Sightlines (Alg 2)/layerWeighting', 'Sightlines (Alg 2)/layerFalloff', 'Sightlines (Alg 2)/layerBudget',
      'Rendering/order-independent ghosts', 'Rendering/depthWeight', 'Rendering/OIT antialiasing', 'Export / import/Export JSON', 'Panel dock/Collapse toggle', 'Class styles/*', 'Class styles/*/alphaMax',
      'Class styles/*/alphaMin', 'Class styles/*/floor', 'Class styles/*/hidden', 'Class styles/*/color',
      'Sidebar/Filter box', 'Sidebar/Eye icon', 'Sidebar/Bucket dot', 'Sidebar/Collapse toggle',
      'Open model', 'Open model/Open IFC or glb file', 'Open model/Cancel load', 'Open model/Load status',
    ];
    // lookup is loose, so camelCase and display names both work
    return import('../src/ui/help').then(({ lookupHelp }) => {
      for (const k of must) expect(lookupHelp(k), k).toBeDefined();
    });
  });

  it('uses {class} only in the class style entries', () => {
    for (const [key, e] of entries) {
      if (/\{class\}/.test(`${e.intent}${e.impact}${e.use}${e.ref}`)) expect(key.startsWith('Class styles/*'), key).toBe(true);
    }
  });

  it('defines the required glossary terms', () => {
    const need = ['alpha', 'occluder', 'sightline', 'focus', 'context', 'host', 'near', 'far', 'buffer', 'ghost', 'edge pass', 'bloom',
      'depth of field', 'order-independent transparency', 'storey', 'tier', 'pin', 'floor', 'explode', 'sweep', 'keyframe'];
    const have = new Set(GLOSSARY.map((g) => g.term));
    for (const t of need) expect(have.has(t), t).toBe(true);
  });
});

// ------------------------------------------------------------------ Impact: plain-language effect

/** Crude stemmer: strips plural and verb endings and the final e, then undoubles a final consonant. Both sides use it. */
function stem(word: string): string {
  let w = word.toLowerCase();
  for (let i = 0; i < 5; i++) {
    const before = w;
    if (w.endsWith('ies') && w.length > 4) w = `${w.slice(0, -3)}y`;
    else if (w.endsWith('ing') && w.length > 5) w = w.slice(0, -3);
    else if (w.endsWith('ed') && w.length > 4) w = w.slice(0, -2);
    else if (w.endsWith('es') && w.length > 4) w = w.slice(0, -2);
    else if (w.endsWith('est') && w.length > 5) w = w.slice(0, -3);
    else if (w.endsWith('er') && w.length > 4) w = w.slice(0, -2);
    else if (w.endsWith('ly') && w.length > 4) w = w.slice(0, -2);
    else if (w.endsWith('s') && !w.endsWith('ss') && w.length > 3) w = w.slice(0, -1);
    else if (w.endsWith('e') && w.length > 3) w = w.slice(0, -1);
    else if (/([b-df-hj-np-tv-z])\1$/.test(w) && w.length > 3) w = w.slice(0, -1);
    if (w === before) break;
  }
  return w;
}

/** Lower-case words of a text. A hyphen or a camelCase boundary separates words. */
function wordsOf(text: string): string[] {
  return text
    .replace(/\{class\}/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .toLowerCase()
    .split(/[^a-z]+/)
    .filter(Boolean);
}

// Technical words that Impact must never use (exact forms; "smooth" stays allowed, "smoothing" is banned).
const EXTRA_BANNED = [
  'opacity', 'transparency', 'transparent', 'ray', 'sample', 'weight', 'weighting', 'exponent', 'smoothing', 'composite',
  'pass', 'shader', 'gpu', 'depth', 'blend', 'bvh', 'algorithm', 'parameter', 'threshold', 'gamma', 'ifc', 'wboit', 'msaa',
  'ssao', 'ao', 'dof', 'fps', 'json', 'url', 'localstorage',
];
const EXTRA_FORMS = new Set<string>();
for (const w of EXTRA_BANNED) {
  const base = w.endsWith('e') ? w.slice(0, -1) : w;
  for (const f of [w, `${w}s`, `${w}es`, `${w}d`, `${w}ed`, `${w}ing`, `${base}ing`, `${base}ed`]) EXTRA_FORMS.add(f);
}
EXTRA_FORMS.delete('smoothed');

const singleTerms = new Set(GLOSSARY.filter((g) => !/[\s-]/.test(g.term)).map((g) => stem(g.term)));
const phraseTerms = GLOSSARY.filter((g) => /[\s-]/.test(g.term)).map((g) => ` ${wordsOf(g.term).join(' ')} `);

// Function words in a key ("Stages of the last load") never count as the name of the control.
const FUNCTION_WORDS = new Set(['the', 'and', 'for', 'from', 'with', 'all', 'not', 'off']);

/** Words of the entry key (folder title and control name) that Impact must not repeat. Tokens under 3 letters are ignored. */
function keyWords(key: string): Set<string> {
  return new Set(wordsOf(key).filter((w) => w.length >= 3 && !FUNCTION_WORDS.has(w)).map(stem));
}

/** Every banned word found in an Impact text, for the failure message. */
function bannedIn(key: string, text: string): string[] {
  const own = keyWords(key);
  const toks = wordsOf(text);
  const hits: string[] = [];
  for (const t of toks) {
    const st = stem(t);
    if (singleTerms.has(st)) hits.push(`${t} (glossary)`);
    else if (EXTRA_FORMS.has(t)) hits.push(`${t} (technical)`);
    else if (t.length >= 3 && own.has(st)) hits.push(`${t} (own name)`);
  }
  const flat = ` ${toks.join(' ')} `;
  for (const p of phraseTerms) if (flat.includes(p)) hits.push(`${p.trim()} (glossary phrase)`);
  return hits;
}

const PASSIVE = /\b(?:is|are|was|were|be|been|being)\s+(?:\w+ed|\w+en|made|done|shown|given|set|put|held|kept|drawn|run|lit)\b/i;

describe('help texts: Impact line', () => {
  const entries = Object.entries(HELP);

  it('exists on every entry, with at least 6 words and no empty text', () => {
    for (const [key, e] of entries) {
      expect(typeof e.impact, key).toBe('string');
      expect(words(e.impact), `${key}: ${e.impact}`).toBeGreaterThanOrEqual(6);
    }
  });

  it('differs from the Intent and from the Use line', () => {
    for (const [key, e] of entries) {
      expect(e.impact.trim().toLowerCase(), key).not.toBe(e.intent.trim().toLowerCase());
      expect(e.impact.trim().toLowerCase(), key).not.toBe(e.use.trim().toLowerCase());
    }
  });

  it('keeps every sentence at 20 words or fewer', () => {
    for (const [key, e] of entries) for (const s of sentences(e.impact)) expect(words(s), `${key}: ${s}`).toBeLessThanOrEqual(20);
  });

  it('has no parentheses, no "e.g." and no "etc."', () => {
    for (const [key, e] of entries) {
      expect(e.impact, key).not.toMatch(/[()]/);
      expect(e.impact, key).not.toMatch(/e\.g\./i);
      expect(e.impact, key).not.toMatch(/\betc\b/i);
    }
  });

  it('uses no glossary term, no technical word and no word of its own control or folder name', () => {
    const bad = entries.map(([key, e]) => ({ key, hits: bannedIn(key, e.impact) })).filter((x) => x.hits.length > 0);
    expect(bad.map((x) => `${x.key}: ${x.hits.join(', ')}`)).toEqual([]);
  });

  it('uses the active voice and the present tense', () => {
    for (const [key, e] of entries) {
      expect(e.impact, key).not.toMatch(PASSIVE);
      expect(e.impact, key).not.toMatch(/\b(?:will|would|was|were|shall)\b/i);
    }
  });

  it('puts the checker to work: it catches a glossary term, a technical word and an own-name word', () => {
    expect(bannedIn('Display/edgeAlpha', 'The alpha value drops.')).toContain('alpha (glossary)');
    expect(bannedIn('Display/edgeAlpha', 'Ghosted walls and pinned slabs.')).toEqual(['ghosted (glossary)', 'pinned (glossary)']);
    expect(bannedIn('Display/edgeAlpha', 'The opacity falls and the rays blend.')).toEqual(['opacity (technical)', 'rays (technical)', 'blend (technical)']);
    expect(bannedIn('Classification (Alg 1)/bufferBase', 'The base grows.')).toEqual(['base (own name)']);
    expect(bannedIn('Display/edgeAlpha', 'The depth of field blurs.')).toContain('depth of field (glossary phrase)');
    expect(bannedIn('Display/edgeAlpha', 'The outline looks smooth and clearer.')).toEqual([]);
  });

  it('keeps the vocabulary short: no word of 13 letters or more', () => {
    for (const [key, e] of entries) for (const w of wordsOf(e.impact)) expect(w.length, `${key}: ${w}`).toBeLessThan(13);
  });
});

describe('popover lines', () => {
  it('lists Intent, Impact, Use, Ref in this order, each with the text of the entry', () => {
    const e = HELP['Classification (Alg 1)/bufferBase']!;
    const lines = popoverLines(e);
    expect(lines.map((l) => l.label)).toEqual(['Intent', 'Impact', 'Use', 'Ref']);
    expect(lines.map((l) => l.text)).toEqual([e.intent, e.impact, e.use, e.ref]);
    expect(lines.map((l) => l.cls)).toEqual(['hp-intent', 'hp-impact', 'hp-use', 'hp-ref']);
  });

  it('fills the {class} placeholder in the Impact line too', () => {
    const e = { intent: 'a {class}', impact: 'b {class}', use: 'c {class}', ref: 'd {class}' };
    expect(fillEntry(e, 'IfcSlab')).toEqual({ intent: 'a IfcSlab', impact: 'b IfcSlab', use: 'c IfcSlab', ref: 'd IfcSlab' });
    expect(fillEntry(HELP['Class styles/*']!, 'IfcSlab').impact).toContain('IfcSlab');
  });
});
