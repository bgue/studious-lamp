// Search index over the elements of a model: name, IFC class, GlobalId, storey, material and property values.
// Built once per model (in idle time in the viewer, in one go in tests), then queried with a bounded top-K scan.
// A query of one or more terms (all must match) first finds the rows that contain its longest term with indexOf over
// chunk strings (all fields and property values of 512 rows each, lower case), then scores only those rows. When fewer
// than `keep` rows contain the term, one more cheap pass adds the rows where it is a subsequence of the name or class
// (the typo and abbreviation case). 100,000 rows: see tests/search-index.test.ts.

import type { ElementId, ElementRecord, SceneModel } from '../types';
import { TIER, isSubsequence, quickPositions, quickScore, termsOf } from './fuzzy';

export type Field = 'name' | 'class' | 'globalId' | 'storey' | 'material' | 'prop';

/** Weights of the fields: a hit in the name counts most. */
const W: Record<Field, number> = { name: 1, class: 0.85, globalId: 0.9, storey: 0.6, material: 0.5, prop: 0 };
const PROP_SCORE = 28;
const SEP = '\u0001';
const EOR = '\u0002';
const CHUNK_ROWS = 512;
/** Terms that may match as a subsequence (abbreviations such as rdct for Rectangular Duct). */
const ABBREVIATION = /^[a-z]{2,8}$/;
const SAMPLE_CHUNKS = 8;

interface Chunk {
  from: number;
  to: number;
  /** Fields and property values of the rows from..to, lower case, rows separated by EOR. */
  text: string;
  /** Start of each row in `text`, and the end of the last. */
  off: Int32Array;
}

export interface ElementHit {
  id: ElementId;
  score: number;
}

export interface SearchResult {
  /** Best hits, best first, at most `keep`. */
  hits: ElementHit[];
  /** Rows that matched. */
  total: number;
  /** Rows scanned (less than the model size while the index is still being built). */
  scanned: number;
}

export interface Explained {
  /** Text of the row title: the name, else the class, else the GlobalId. */
  label: string;
  labelPositions: number[];
  /** "IfcWall · Erdgeschoss". */
  sub: string;
  subPositions: number[];
  /** Where the match came from when it is not visible in label and sub: "GlobalId 2Xk…" or "Pset.Prop = value". */
  via: string;
  viaPositions: number[];
}

export class ElementIndex {
  readonly size: number;
  /** Rows built so far. */
  built = 0;
  private readonly els: readonly ElementRecord[];
  private readonly storeyName = new Map<number, string>();
  private readonly nameL: string[];
  private readonly classL: string[];
  private readonly gidL: string[];
  private readonly storeyL: string[];
  private readonly matL: string[];
  private readonly chunks: Chunk[] = [];
  /** Per row: bit k set when the letter 'a'+k occurs in the name or class. Rejects most subsequence tests in one operation. */
  private readonly letters: Int32Array;
  private cancelled = false;

  constructor(readonly model: SceneModel) {
    this.els = model.elements;
    this.size = model.elements.length;
    for (const s of model.storeys) this.storeyName.set(s.id, s.name);
    const n = this.size;
    this.letters = new Int32Array(n);
    this.nameL = new Array<string>(n);
    this.classL = new Array<string>(n);
    this.gidL = new Array<string>(n);
    this.storeyL = new Array<string>(n);
    this.matL = new Array<string>(n);
  }

  get ready(): boolean {
    return this.built >= this.size;
  }

  private storeyOf(e: ElementRecord): string {
    return e.storey === null ? '' : (this.storeyName.get(e.storey) ?? '');
  }

  /** Index rows [built, to) as one chunk (at most CHUNK_ROWS rows per call is the idle slice size). Returns the new `built`. */
  buildTo(to: number): number {
    while (this.built < Math.min(to, this.size)) this.buildChunk(Math.min(to, this.size, this.built + CHUNK_ROWS));
    return this.built;
  }

  private buildChunk(end: number): void {
    const from = this.built;
    const parts: string[] = new Array(end - from);
    const off = new Int32Array(end - from + 1);
    let len = 0;
    for (let i = from; i < end; i++) {
      const e = this.els[i]!;
      const name = e.name ? e.name.toLowerCase() : '';
      const cls = e.ifcClass.toLowerCase();
      const gid = e.globalId.toLowerCase();
      const st = this.storeyOf(e).toLowerCase();
      const mat = e.material ? e.material.toLowerCase() : '';
      this.nameL[i] = name;
      this.classL[i] = cls;
      this.gidL[i] = gid;
      this.storeyL[i] = st;
      this.matL[i] = mat;
      this.letters[i] = letterMask(name) | letterMask(cls);
      let props = '';
      const p = e.props;
      if (p) for (const k in p) props += String(p[k]) + SEP;
      const seg = name + SEP + cls + SEP + gid + SEP + st + SEP + mat + SEP + (props ? props.toLowerCase() : '');
      parts[i - from] = seg;
      off[i - from] = len;
      len += seg.length + 1;
    }
    off[end - from] = len;
    this.chunks.push({ from, to: end, text: parts.join(EOR), off });
    this.built = end;
  }

  /** Build everything now. */
  buildAll(): this {
    this.buildTo(this.size);
    return this;
  }

  /**
   * Build in idle time: slices of about `budgetMs`, between them the browser can paint and handle input. Resolves
   * when done or cancelled. `onProgress` runs after each slice.
   */
  buildIdle(opts: { budgetMs?: number; onProgress?: (built: number, size: number) => void } = {}): Promise<void> {
    const budget = opts.budgetMs ?? 8;
    return new Promise((resolve) => {
      const step = (deadline?: { timeRemaining(): number }): void => {
        if (this.cancelled || this.ready) {
          resolve();
          return;
        }
        const t0 = performance.now();
        const allowed = Math.max(2, Math.min(budget, deadline ? deadline.timeRemaining() : budget));
        while (this.built < this.size && performance.now() - t0 < allowed) this.buildTo(this.built + 512);
        opts.onProgress?.(this.built, this.size);
        if (this.ready || this.cancelled) resolve();
        else schedule(step);
      };
      schedule(step);
    });
  }

  cancel(): void {
    this.cancelled = true;
  }

  /** The term with the fewest hits in the first chunks (the longer one on a tie). */
  private rarest(terms: readonly string[]): string {
    if (terms.length === 1) return terms[0]!;
    let best = terms[0]!;
    let bestHits = Infinity;
    const n = Math.min(SAMPLE_CHUNKS, this.chunks.length);
    for (const t of terms) {
      let hits = 0;
      for (let k = 0; k < n; k++) {
        const text = this.chunks[k]!.text;
        for (let p = text.indexOf(t); p >= 0 && hits < 100000; p = text.indexOf(t, p + t.length)) hits++;
      }
      if (hits < bestHits || (hits === bestHits && t.length > best.length)) {
        best = t;
        bestHits = hits;
      }
    }
    return best;
  }

  /** The chunk text of one row (all fields and property values). */
  private rowText(i: number): string {
    let lo = 0;
    let hi = this.chunks.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (this.chunks[mid]!.from <= i) lo = mid;
      else hi = mid - 1;
    }
    const c = this.chunks[lo]!;
    return c.text.slice(c.off[i - c.from]!, c.off[i - c.from + 1]! - 1);
  }

  /** Score of one term for one row: the best field, -1 when nothing matches. */
  private termScore(t: string, i: number): number {
    let best = -1;
    const n = this.nameL[i]!;
    if (n) {
      const s = quickScore(t, n);
      if (s >= 0) best = s * W.name;
    }
    const c = quickScore(t, this.classL[i]!);
    if (c >= 0 && c * W.class > best) best = c * W.class;
    if (t.length >= 3) {
      const g = this.gidL[i]!;
      const idx = g.indexOf(t);
      if (idx >= 0) {
        const s = (idx === 0 ? TIER.prefix : TIER.substring) * W.globalId;
        if (s > best) best = s;
      }
    }
    const st = this.storeyL[i]!;
    if (st) {
      const s = quickScore(t, st, false);
      if (s >= 0 && s * W.storey > best) best = s * W.storey;
    }
    const m = this.matL[i]!;
    if (m) {
      const s = quickScore(t, m, false);
      if (s >= 0 && s * W.material > best) best = s * W.material;
    }
    if (best < 0 && t.length >= 2 && this.rowText(i).indexOf(t) >= 0) best = PROP_SCORE;
    return best;
  }

  /**
   * Rank the rows for the terms (all terms must match). Keeps the best `keep` rows and counts the rest.
   * Rows in `skip` are left out.
   */
  search(terms: readonly string[], keep = 200, skip?: ReadonlySet<ElementId>): SearchResult {
    const topIds: number[] = [];
    const topScores: number[] = [];
    let total = 0;
    const nt = terms.length;
    const limit = this.built;
    if (nt === 0) return { hits: [], total: 0, scanned: limit };
    let floor = -Infinity;

    const consider = (i: number): void => {
      if (skip && skip.has(i)) return;
      let sum = 0;
      for (let k = 0; k < nt; k++) {
        const s = this.termScore(terms[k]!, i);
        if (s < 0) return;
        sum += s;
      }
      total++;
      const score = sum / nt;
      if (topIds.length >= keep && score <= floor) return;
      // Insert in descending order; on equal scores the earlier row stays first.
      let pos = topIds.length;
      while (pos > 0 && topScores[pos - 1]! < score) pos--;
      topIds.splice(pos, 0, i);
      topScores.splice(pos, 0, score);
      if (topIds.length > keep) {
        topIds.pop();
        topScores.pop();
      }
      if (topIds.length >= keep) floor = topScores[topScores.length - 1]!;
    };

    // One letter: a prefix of the name or class only (the full pass would match nearly every row).
    if (nt === 1 && terms[0]!.length === 1) {
      const c = terms[0]!.charCodeAt(0);
      for (let i = 0; i < limit; i++) {
        if (this.nameL[i]!.charCodeAt(0) === c || this.classL[i]!.charCodeAt(0) === c) consider(i);
      }
      return { hits: topIds.map((id, k) => ({ id, score: topScores[k]! })), total, scanned: limit };
    }

    // The rarest term (by a sample of the first chunks) finds the candidates; the others are checked per candidate.
    const lead = this.rarest(terms);

    // Pass 1: rows that contain the lead term anywhere (fields or property values).
    const seen = new Set<number>();
    for (const c of this.chunks) {
      const text = c.text;
      const off = c.off;
      let row = 0;
      let p = text.indexOf(lead);
      while (p >= 0) {
        while (off[row + 1]! <= p) row++;
        const i = c.from + row;
        seen.add(i);
        consider(i);
        p = text.indexOf(lead, off[row + 1]!);
      }
    }

    // Pass 2: few rows contain the term and it looks like an abbreviation (letters only): add the rows where it is a
    // subsequence of the name or class.
    if (seen.size < keep && ABBREVIATION.test(lead)) {
      const nameL = this.nameL;
      const classL = this.classL;
      const letters = this.letters;
      const want = letterMask(lead);
      for (let i = 0; i < limit; i++) {
        if ((letters[i]! & want) !== want || seen.has(i)) continue;
        if (isSubsequence(lead, nameL[i]!) || isSubsequence(lead, classL[i]!)) consider(i);
      }
    }
    return { hits: topIds.map((id, k) => ({ id, score: topScores[k]! })), total, scanned: limit };
  }

  /** Text and highlight positions for the row of a hit. */
  explain(id: ElementId, terms: readonly string[]): Explained {
    const e = this.els[id]!;
    const label = e.name && e.name.trim() ? e.name : e.ifcClass;
    const labelPositions = highlight(terms, label);
    const storey = this.storeyOf(e);
    const sub = storey ? `${e.ifcClass} · ${storey}` : e.ifcClass;
    const subPositions = highlight(terms, sub);
    let via = '';
    let viaPositions: number[] = [];
    const visible = `${label} ${sub}`.toLowerCase();
    const missing = terms.filter((t) => !visible.includes(t) && !isSubsequence(t, visible));
    if (missing.length > 0) {
      const gid = e.globalId.toLowerCase();
      if (missing.some((t) => gid.includes(t))) {
        via = `GlobalId ${e.globalId}`;
        viaPositions = highlight(terms, via);
      } else if (e.material && missing.some((t) => e.material!.toLowerCase().includes(t))) {
        via = `Material ${e.material}`;
        viaPositions = highlight(terms, via);
      } else if (e.props) {
        for (const k in e.props) {
          const v = String(e.props[k]);
          if (missing.some((t) => v.toLowerCase().includes(t))) {
            via = `${k} = ${v}`;
            viaPositions = highlight(terms, via);
            break;
          }
        }
      }
    }
    return { label, labelPositions, sub, subPositions, via, viaPositions };
  }
}

/** Bit k is set when the letter 'a'+k occurs in the text (lower case). */
function letterMask(text: string): number {
  let m = 0;
  for (let i = 0; i < text.length; i++) {
    const k = text.charCodeAt(i) - 97;
    if (k >= 0 && k < 26) m |= 1 << k;
  }
  return m;
}

function highlight(terms: readonly string[], text: string): number[] {
  const set = new Set<number>();
  for (const t of terms) for (const p of quickPositions(t, text)) set.add(p);
  return [...set].sort((a, b) => a - b);
}

function schedule(step: (d?: { timeRemaining(): number }) => void): void {
  const w = globalThis as unknown as { requestIdleCallback?: (cb: (d: { timeRemaining(): number }) => void, o?: { timeout: number }) => number };
  if (typeof w.requestIdleCallback === 'function') w.requestIdleCallback((d) => step(d), { timeout: 120 });
  else setTimeout(() => step(), 4);
}

/** Terms of a text query (lower case). Re-exported so callers need one import. */
export { termsOf };
