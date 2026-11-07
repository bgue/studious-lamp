// Matching shared by the command palette (src/ui/palette.ts) and the search bar (src/ui/awesomeBar.ts). Pure, no DOM.
//   fuzzyScore: subsequence match with word-start, consecutive and prefix bonuses and the matched positions. Exact, but
//               O(query x text^2): for labels (commands, settings, presets), not for 100,000 element rows.
//   quickScore / quickPositions: the cheap tiers (equal, prefix, word start, substring, subsequence) the element index
//               runs over every row.

export interface FuzzyMatch {
  score: number;
  /** Indices of the matched characters in the text. */
  positions: number[];
}

const isWordStart = (t: string, i: number): boolean => {
  if (i === 0) return true;
  const p = t[i - 1]!;
  const c = t[i]!;
  return !/[a-z0-9]/i.test(p) || (p === p.toLowerCase() && c !== c.toLowerCase());
};

/** Subsequence match of `query` in `text` (case-insensitive). Higher is better; null when it does not match. */
export function fuzzyScore(query: string, text: string): FuzzyMatch | null {
  const q = query.toLowerCase().replace(/\s+/g, '');
  const t = text.toLowerCase();
  if (q.length === 0) return { score: 0, positions: [] };
  if (q.length > t.length) return null;
  const n = q.length;
  const m = t.length;
  const NEG = -1e9;
  // best[i][j]: best score matching q[0..i] with q[i] placed at text index j.
  const best: number[][] = Array.from({ length: n }, () => new Array<number>(m).fill(NEG));
  const from: number[][] = Array.from({ length: n }, () => new Array<number>(m).fill(-1));
  for (let i = 0; i < n; i++) {
    for (let j = i; j < m; j++) {
      if (t[j] !== q[i]) continue;
      const here = 1 + (isWordStart(text, j) ? 10 : 0) + (j === 0 ? 6 : 0);
      if (i === 0) {
        best[i]![j] = here - Math.min(j, 6) * 0.5;
        continue;
      }
      let bs = NEG;
      let bk = -1;
      for (let k = i - 1; k < j; k++) {
        const prev = best[i - 1]![k]!;
        if (prev <= NEG / 2) continue;
        const s = prev + (k === j - 1 ? 8 : -Math.min((j - k - 1) * 3, 15));
        if (s > bs) {
          bs = s;
          bk = k;
        }
      }
      if (bk >= 0) {
        best[i]![j] = bs + here;
        from[i]![j] = bk;
      }
    }
  }
  let bj = -1;
  let bs = NEG;
  for (let j = 0; j < m; j++) {
    if (best[n - 1]![j]! > bs) {
      bs = best[n - 1]![j]!;
      bj = j;
    }
  }
  if (bj < 0) return null;
  const positions: number[] = [];
  for (let i = n - 1, j = bj; i >= 0; i--) {
    positions.unshift(j);
    j = from[i]![j]!;
  }
  let score = bs - m * 0.1;
  if (t === q) score += 60;
  else if (t.startsWith(q)) score += 30;
  else if (t.includes(q)) score += 15;
  return { score, positions };
}

/** Split a query into lower-case terms on whitespace. */
export function termsOf(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean);
}

/** True when `t` (lower case) starts a word of `s` (lower case) at index `i`: after a non-alphanumeric character. */
export function isBoundary(s: string, i: number): boolean {
  if (i === 0) return true;
  const c = s.charCodeAt(i - 1);
  const alnum = (c >= 48 && c <= 57) || (c >= 97 && c <= 122) || c > 127;
  return !alnum;
}

/** True when the characters of `t` occur in `s` in order. */
export function isSubsequence(t: string, s: string): boolean {
  let j = 0;
  for (let i = 0; i < s.length && j < t.length; i++) if (s.charCodeAt(i) === t.charCodeAt(j)) j++;
  return j === t.length;
}

/** Scores of the tiers, best first. Exported for the tests. */
export const TIER = { equal: 120, prefix: 100, word: 80, substring: 58, subsequence: 30 } as const;

/**
 * Cheap match of one term against one lower-case string. Tiers: equal, prefix, word start, substring, then (when
 * `fuzzy` is set and the term has 2 letters or more) subsequence. Shorter strings rank above longer ones inside a tier.
 * Returns -1 when the term does not match.
 */
export function quickScore(t: string, s: string, fuzzy = true): number {
  const n = s.length;
  if (n === 0 || t.length === 0) return -1;
  const idx = s.indexOf(t);
  const lenPenalty = Math.min(n, 80) * 0.1;
  if (idx >= 0) {
    if (idx === 0) return (n === t.length ? TIER.equal : TIER.prefix) - lenPenalty;
    if (isBoundary(s, idx)) return TIER.word - lenPenalty;
    // The first hit is inside a word; a later hit after a space still counts as a word start.
    if (s.indexOf(` ${t}`) >= 0) return TIER.word - lenPenalty - 1;
    return TIER.substring - Math.min(idx, 20) * 0.5 - lenPenalty;
  }
  if (fuzzy && t.length >= 2 && isSubsequence(t, s)) return TIER.subsequence - lenPenalty;
  return -1;
}

/** Matched character positions of a term in a text, for highlighting: the substring when there is one, else a greedy subsequence. */
export function quickPositions(t: string, text: string): number[] {
  const lower = text.toLowerCase();
  const idx = lower.indexOf(t);
  if (idx >= 0) return Array.from({ length: t.length }, (_, k) => idx + k);
  const out: number[] = [];
  let j = 0;
  for (let i = 0; i < lower.length && j < t.length; i++) {
    if (lower.charCodeAt(i) === t.charCodeAt(j)) {
      out.push(i);
      j++;
    }
  }
  return j === t.length ? out : [];
}

/** Union of the positions of several terms, sorted, without duplicates. */
export function termPositions(terms: readonly string[], text: string): number[] {
  const set = new Set<number>();
  for (const t of terms) for (const p of quickPositions(t, text)) set.add(p);
  return [...set].sort((a, b) => a - b);
}
