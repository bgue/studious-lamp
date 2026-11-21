// Errors and warnings of the animation script language: a message with line and column and, where one helps, a hint.
// Pure module. Lines and columns are 1-based; `end` is the column after the last character of the marked text.

export type Severity = 'error' | 'warning';

export interface ScriptDiagnostic {
  severity: Severity;
  line: number;
  col: number;
  end: number;
  message: string;
  hint?: string;
}

/** An error that stops the statement being read; the parser collects it and goes on with the next line. */
export class ScriptError extends Error {
  constructor(
    message: string,
    readonly line: number,
    readonly col: number,
    readonly end: number,
    readonly hint?: string,
  ) {
    super(message);
    this.name = 'ScriptError';
  }
  toDiagnostic(severity: Severity = 'error'): ScriptDiagnostic {
    const d: ScriptDiagnostic = { severity, line: this.line, col: this.col, end: Math.max(this.end, this.col + 1), message: this.message };
    if (this.hint) d.hint = this.hint;
    return d;
  }
}

/** "Line 3, column 5: message. Hint." for a log or a plain list. */
export function formatDiagnostic(d: ScriptDiagnostic): string {
  const where = d.line > 0 ? `Line ${d.line}, column ${d.col}: ` : '';
  const hint = d.hint ? ` ${d.hint}` : '';
  return `${where}${d.message}${hint}`;
}

/** Edit distance (Levenshtein) of two short words. */
export function editDistance(a: string, b: string): number {
  if (a === b) return 0;
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const cur = [i];
    for (let j = 1; j <= n; j++) {
      cur[j] = Math.min(prev[j]! + 1, cur[j - 1]! + 1, prev[j - 1]! + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[n]!;
}

/** The candidates closest to `word`, best first: a prefix or a small edit distance. Case-insensitive. */
export function nearest(word: string, candidates: Iterable<string>, max = 3): string[] {
  const w = word.toLowerCase();
  const scored: Array<{ c: string; s: number }> = [];
  for (const c of candidates) {
    const l = c.toLowerCase();
    let s: number;
    if (l === w) s = 0;
    else if (w.length >= 2 && (l.startsWith(w) || w.startsWith(l))) s = 0.5;
    else if (w.length >= 3 && l.slice(0, 3) === w.slice(0, 3)) s = 1;
    else {
      // dotted paths: compare the last segment as well, so `alphamax` finds `xray.alphaMax`
      const d = editDistance(w, l);
      const last = l.includes('.') ? editDistance(w, l.slice(l.lastIndexOf('.') + 1)) : d;
      s = Math.min(d, last + 0.25);
    }
    const limit = w.length <= 3 ? 1 : Math.max(2, Math.floor(w.length / 3) + 1);
    if (s <= limit) scored.push({ c, s });
  }
  scored.sort((a, b) => a.s - b.s || a.c.length - b.c.length || (a.c < b.c ? -1 : 1));
  return scored.slice(0, max).map((x) => x.c);
}

/** "Did you mean `fading`?" or "Did you mean `a`, `b` or `c`?"; empty when nothing is close. */
export function didYouMean(word: string, candidates: Iterable<string>, max = 3): string {
  const near = nearest(word, candidates, max);
  if (near.length === 0) return '';
  const q = near.map((n) => `\`${n}\``);
  return `Did you mean ${q.length === 1 ? q[0] : `${q.slice(0, -1).join(', ')} or ${q[q.length - 1]}`}?`;
}
