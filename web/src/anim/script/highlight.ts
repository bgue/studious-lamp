// Light syntax colouring for the script editor: one line of text to a list of coloured pieces. Pure.

import type { ScriptDiagnostic } from './diagnostics';
import { STATEMENT_WORDS } from './parser';

export type HlClass = 'kw' | 'opt' | 'str' | 'num' | 'com' | 'op' | 'el' | '';

export interface HlPiece {
  text: string;
  cls: HlClass;
  /** The piece lies in the marked range of an error or a warning. */
  mark?: 'error' | 'warning';
}

const KEYWORDS = new Set<string>(STATEMENT_WORDS);
const OPTIONS = new Set(['date', 'milestone', 'around', 'by', 'from', 'box', 'storey', 'storeys', 'radial', 'planned', 'actual', 'variance', 'to', 'over', 'ease', 'margin', 'fading', 'for', 'with', 'about', 'into', 'times', 'preset', 'view', 'each', 'in', 'seconds', 'second', 'degrees', 'degree', 'linear', 'out', 'in', 'sets', 'nothing']);
const ELEMENTS = new Set(['active', 'completed', 'critical', 'where', 'class', 'classes', 'everything', 'selection', 'the', 'it', 'elements', 'element']);
const COND = new Set(['and', 'or', 'not', 'like', 'between', 'is', 'null', 'true', 'false', 'on', 'off']);

const RE = /(--.*|#(?![0-9a-fA-F]{6}(?![A-Za-z0-9_])).*)|(#[0-9a-fA-F]{6}(?![A-Za-z0-9_]))|("(?:[^"]|"")*"?|“[^”]*”?)|(\d+\.?\d*|\.\d+)|([A-Za-z_][A-Za-z0-9_.]*)|([=<>!+\-*/&(),]+)|(\s+)|(.)/gy;

/** Pieces of one line. `first` marks the statement word: it is the first word of the line. */
export function highlightLine(text: string): HlPiece[] {
  const out: HlPiece[] = [];
  let first = true;
  RE.lastIndex = 0;
  for (let m = RE.exec(text); m; m = RE.exec(text)) {
    const s = m[0];
    if (m[1] !== undefined) out.push({ text: s, cls: 'com' });
    else if (m[2] !== undefined) {
      out.push({ text: s, cls: 'num' });
      first = false;
    } else if (m[3] !== undefined) {
      out.push({ text: s, cls: 'str' });
      first = false;
    } else if (m[4] !== undefined) {
      out.push({ text: s, cls: 'num' });
      first = false;
    } else if (m[5] !== undefined) {
      const w = s.toLowerCase();
      let cls: HlClass = '';
      if (first && KEYWORDS.has(w)) cls = 'kw';
      else if (OPTIONS.has(w)) cls = 'opt';
      else if (ELEMENTS.has(w)) cls = 'el';
      else if (COND.has(w)) cls = 'op';
      out.push({ text: s, cls });
      first = false;
    } else if (m[6] !== undefined) {
      out.push({ text: s, cls: 'op' });
      first = false;
    } else out.push({ text: s, cls: '' });
    if (m.index + s.length >= text.length) break;
  }
  return out;
}

/** Split pieces at the columns of diagnostics of this line (1-based, end exclusive) and mark them. */
export function markPieces(pieces: HlPiece[], diags: readonly ScriptDiagnostic[]): HlPiece[] {
  if (diags.length === 0) return pieces;
  const out: HlPiece[] = [];
  let col = 1;
  for (const p of pieces) {
    let start = 0;
    const cuts = new Set<number>();
    for (const d of diags) {
      for (const c of [d.col, d.end]) {
        const rel = c - col;
        if (rel > 0 && rel < p.text.length) cuts.add(rel);
      }
    }
    for (const rel of [...cuts].sort((a, b) => a - b).concat([p.text.length])) {
      const text = p.text.slice(start, rel);
      if (text) {
        const c0 = col + start;
        const hit = diags.filter((d) => c0 >= d.col && c0 < d.end);
        const mark = hit.some((d) => d.severity === 'error') ? 'error' : hit.length ? 'warning' : undefined;
        out.push(mark ? { text, cls: p.cls, mark } : { text, cls: p.cls });
      }
      start = rel;
    }
    col += p.text.length;
  }
  return out;
}
