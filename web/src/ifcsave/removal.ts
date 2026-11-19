// Planning the removal of elements from a STEP file (design 2.3, 2.4): which lines go, which are rewritten, which elements stay and why.
// Pure over a StepIndex and the file bytes. Relations are edited at the text level (references are dropped from lists, the rest of the
// line stays byte for byte), so strings in a rewritten relation are never re-encoded.

import type { StepIndex } from './stepIndex';

export interface RemovalOptions {
  /** Remove a wall even when a door or window that stays stands in one of its openings (the filler then stands in no wall). */
  removeHostsAnyway: boolean;
}

export interface KeptElement {
  expressId: number;
  because: string;
}

export interface RemovalStats {
  /** Express ids asked for that the file does not have. */
  missing: number;
  /** Elements removed, as asked. */
  removed: number;
  /** Lines removed with them: openings, projections, ports. */
  cascaded: number;
  /** Relationship lines deleted outright, and lines whose references were trimmed. */
  relationsDeleted: number;
  relationsTrimmed: number;
  /** Door or window fills cut where the opening stays. */
  fillsCut: number;
  /** Lines of geometry, placement, property data that nothing uses any more. */
  swept: number;
  /** All lines removed, the old Xray block not counted. */
  linesDeleted: number;
  /** Lines of an earlier Xray block that were dropped with it. */
  blockLinesDropped: number;
}

export interface RemovalPlan {
  /** 1 for every row that is not written (including the lines of an old Xray block). */
  deleted: Uint8Array;
  /** Express ids of the lines removed (the old block's lines not included). */
  delete: Set<number>;
  /** Express id -> the new statement text (`#id=TYPE(...);`). */
  rewrite: Map<number, string>;
  /** Express ids of the elements removed, and of the openings and ports that went with them. */
  removed: number[];
  cascaded: number[];
  kept: KeptElement[];
  /** Notes for the report (the file holds something the rules do not cover). */
  warnings: string[];
  stats: RemovalStats;
}

// ---------------------------------------------------------------- text helpers

export function latin1Decode(b: Uint8Array, from: number, to: number): string {
  let s = '';
  for (let i = from; i < to; i += 8192) s += String.fromCharCode(...b.subarray(i, Math.min(to, i + 8192)));
  return s;
}
export function latin1Encode(s: string): Uint8Array {
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i) & 0xff;
  return out;
}

/** Index of the `)` that closes the `(` at `open`, skipping strings; -1 when unbalanced. */
function matchParen(t: string, open: number): number {
  let d = 0;
  for (let i = open; i < t.length; i++) {
    const c = t.charCodeAt(i);
    if (c === 39) {
      i++;
      while (i < t.length && t.charCodeAt(i) !== 39) i++;
    } else if (c === 40) d++;
    else if (c === 41 && --d === 0) return i;
  }
  return -1;
}

/** Split at the commas of depth 0, strings and nested parentheses respected. */
function splitTop(t: string): string[] {
  const out: string[] = [];
  let d = 0;
  let from = 0;
  for (let i = 0; i < t.length; i++) {
    const c = t.charCodeAt(i);
    if (c === 39) {
      i++;
      while (i < t.length && t.charCodeAt(i) !== 39) i++;
    } else if (c === 40) d++;
    else if (c === 41) d--;
    else if (c === 44 && d === 0) {
      out.push(t.slice(from, i));
      from = i + 1;
    }
  }
  out.push(t.slice(from));
  return out;
}

/** The top-level arguments of a statement `#id=TYPE(a,b,...);` as text. */
export function argTexts(stmt: string): string[] {
  const p = stmt.indexOf('(');
  if (p < 0) return [];
  const q = matchParen(stmt, p);
  return splitTop(stmt.slice(p + 1, q < 0 ? stmt.length : q));
}

/** Express ids referenced by an argument text (a `#n` or a list of them). */
export function refIds(arg: string): number[] {
  const out: number[] = [];
  for (let i = 0; i < arg.length; i++) {
    const c = arg.charCodeAt(i);
    if (c === 39) {
      i++;
      while (i < arg.length && arg.charCodeAt(i) !== 39) i++;
    } else if (c === 35) {
      let v = 0;
      let k = i + 1;
      while (k < arg.length && arg.charCodeAt(k) >= 48 && arg.charCodeAt(k) <= 57) v = v * 10 + arg.charCodeAt(k++) - 48;
      if (k > i + 1) out.push(v);
      i = k - 1;
    }
  }
  return out;
}

export interface Trimmed {
  text: string;
  /** A single-valued argument is one of the dropped ids. */
  single: boolean;
  /** A list that held references now holds none. */
  emptied: boolean;
  changed: boolean;
}

/** Drop the references for which `drop(id)` is true from the lists of a statement. Everything else is left byte for byte. */
export function trimRefs(stmt: string, drop: (id: number) => boolean): Trimmed {
  const p = stmt.indexOf('(');
  const q = p < 0 ? -1 : matchParen(stmt, p);
  if (p < 0 || q < 0) return { text: stmt, single: false, emptied: false, changed: false };
  const args = splitTop(stmt.slice(p + 1, q));
  let single = false;
  let emptied = false;
  let changed = false;
  const out = args.map((a) => {
    const t = a.trim();
    if (t.charCodeAt(0) === 35) {
      const ids = refIds(t);
      if (ids.length === 1 && drop(ids[0]!)) single = true;
      return a;
    }
    if (t.charCodeAt(0) !== 40) return a;
    const close = matchParen(t, 0);
    if (close < 0) return a;
    const items = splitTop(t.slice(1, close));
    let had = false;
    const keep = items.filter((it) => {
      const s = it.trim();
      if (s.charCodeAt(0) !== 35) return true;
      had = true;
      const ids = refIds(s);
      return !(ids.length === 1 && drop(ids[0]!));
    });
    if (!had || keep.length === items.length) return a;
    changed = true;
    if (keep.length === 0 || (keep.length === 1 && keep[0]!.trim() === '')) emptied = true;
    const lead = a.slice(0, a.length - a.trimStart().length);
    return `${lead}(${keep.map((k) => k.trim()).join(',')})`;
  });
  return { text: changed ? `${stmt.slice(0, p + 1)}${out.join(',')}${stmt.slice(q)}` : stmt, single, emptied, changed };
}

// ---------------------------------------------------------------- classes

const SPATIAL = new Set(['IFCPROJECT', 'IFCSITE', 'IFCBUILDING', 'IFCBUILDINGSTOREY', 'IFCSPACE', 'IFCFACILITY', 'IFCFACILITYPART', 'IFCBRIDGE', 'IFCROAD', 'IFCRAILWAY', 'IFCMARINEFACILITY']);
/** Lines the orphan sweep never deletes, however few lines refer to them. */
const KEEP = new Set([
  'IFCPERSON', 'IFCORGANIZATION', 'IFCPERSONANDORGANIZATION', 'IFCAPPLICATION', 'IFCCLASSIFICATION',
  'IFCUNITASSIGNMENT', 'IFCSIUNIT', 'IFCCONVERSIONBASEDUNIT', 'IFCCONVERSIONBASEDUNITWITHOFFSET', 'IFCDERIVEDUNIT', 'IFCMONETARYUNIT', 'IFCMEASUREWITHUNIT', 'IFCDIMENSIONALEXPONENTS',
  'IFCGEOMETRICREPRESENTATIONCONTEXT', 'IFCGEOMETRICREPRESENTATIONSUBCONTEXT', 'IFCMAPCONVERSION', 'IFCPROJECTEDCRS', 'IFCCOORDINATEREFERENCESYSTEM',
]);
/** Rooted lines (they carry a GlobalId) that may be swept: the property data of a removed element. */
const SWEEPABLE_ROOTED = new Set(['IFCPROPERTYSET', 'IFCELEMENTQUANTITY']);

const F_REL = 1, F_AGG = 2, F_VOIDS = 4, F_FILLS = 8, F_PROJECTS = 16, F_PORT2EL = 32, F_STYLED = 64, F_LAYER = 128;
function flagsOf(name: string): number {
  let f = 0;
  if (name.startsWith('IFCREL')) f |= F_REL;
  if (name === 'IFCRELAGGREGATES' || name === 'IFCRELNESTS') f |= F_AGG;
  if (name === 'IFCRELVOIDSELEMENT') f |= F_VOIDS;
  if (name === 'IFCRELFILLSELEMENT') f |= F_FILLS;
  if (name === 'IFCRELPROJECTSELEMENT') f |= F_PROJECTS;
  if (name === 'IFCRELCONNECTSPORTTOELEMENT') f |= F_PORT2EL;
  if (name === 'IFCSTYLEDITEM') f |= F_STYLED;
  if (name === 'IFCPRESENTATIONLAYERASSIGNMENT' || name === 'IFCPRESENTATIONLAYERWITHSTYLE') f |= F_LAYER;
  return f;
}

const describe = (ix: StepIndex, r: number): string => `#${ix.id[r]} ${ix.typeOf(r)}`;

// ---------------------------------------------------------------- the plan

export function planRemoval(ix: StepIndex, bytes: Uint8Array, remove: readonly number[], o: RemovalOptions): RemovalPlan {
  const n = ix.count;
  const flagOfType = ix.typeNames.map(flagsOf);
  const flags = (r: number): number => flagOfType[ix.type[r]!]!;
  const stmt = (r: number): string => latin1Decode(bytes, ix.offset[r]!, ix.offset[r]! + ix.length[r]!);
  const blk = ix.block;
  const inBlock = (r: number): boolean => !!blk && ix.offset[r]! >= blk.begin && ix.offset[r]! < blk.end;

  const argCache = new Map<number, string[]>();
  const argsOf = (r: number): string[] => {
    let a = argCache.get(r);
    if (!a) argCache.set(r, (a = argTexts(stmt(r))));
    return a;
  };
  const refOf = (r: number, i: number): number => {
    const a = argsOf(r)[i];
    if (a === undefined) return -1;
    const ids = refIds(a);
    return ids.length === 1 && a.trim().startsWith('#') ? ix.rowOf(ids[0]!) : -1;
  };
  const refRows = (r: number, i: number): number[] => {
    const a = argsOf(r)[i];
    return a === undefined ? [] : refIds(a).map((id) => ix.rowOf(id)).filter((x) => x >= 0);
  };
  const isPort = (r: number): boolean => ix.typeOf(r) === 'IFCDISTRIBUTIONPORT';
  const styledItem = (r: number): number => refOf(r, 0);

  const isRooted = (r: number): boolean => {
    let p = ix.offset[r]!;
    const end = p + Math.min(ix.length[r]!, 96);
    while (p < end && bytes[p] !== 40) p++;
    return bytes[p + 1] === 39 && bytes[p + 24] === 39;
  };
  const sweepable = (t: number): boolean => {
    const name = ix.typeOf(t);
    if (KEEP.has(name) || SPATIAL.has(name) || name === '') return false;
    if (flags(t) & F_REL) return false;
    return !isRooted(t) || SWEEPABLE_ROOTED.has(name);
  };
  const weakEdge = (r: number, t: number): boolean => {
    const f = flags(r);
    return (f & F_LAYER) !== 0 || ((f & F_STYLED) !== 0 && styledItem(r) === t);
  };
  const strongCache = new Map<number, number>();
  const strongCount = (t: number): number => {
    const hit = strongCache.get(t);
    if (hit !== undefined) return hit;
    let c = 0;
    for (let k = ix.invStart[t]!; k < ix.invStart[t + 1]!; k++) {
      const r = ix.inv[k]!;
      if (!inBlock(r) && !weakEdge(r, t)) c++;
    }
    strongCache.set(t, c);
    return c;
  };

  const seedSet = new Set<number>();
  const kept: KeptElement[] = [];
  let missing = 0;
  for (const id of remove) {
    const r = ix.rowOf(id);
    if (r < 0) missing++;
    else if (SPATIAL.has(ix.typeOf(r))) kept.push({ expressId: id, because: 'part of the spatial structure' });
    else seedSet.add(r);
  }
  const seeds = [...seedSet].sort((a, b) => a - b);
  const forced = new Set<number>(ix.ourNamedRows);
  const vetoed = new Map<number, string>();

  interface Attempt {
    del: Uint8Array;
    rewrite: Map<number, string>;
    D: Map<number, number>;
    newVetoes: Map<number, string>;
    relsDeleted: number;
    swept: number;
    warnings: string[];
  }

  const attempt = (): Attempt => {
    // ---- A: which elements go, which stay
    let D = new Map<number, number>();
    for (;;) {
      D = new Map<number, number>();
      const live = seeds.filter((s) => !vetoed.has(s));
      for (const s of live) D.set(s, s);
      for (const f of forced) D.set(f, f);
      const openings: Array<[number, number]> = [];
      for (const s of live) {
        const sid = ix.id[s]!;
        for (let k = ix.invStart[s]!; k < ix.invStart[s + 1]!; k++) {
          const r = ix.inv[k]!;
          if (inBlock(r)) continue;
          const f = flags(r);
          if (f & F_VOIDS) {
            if (refOf(r, 4) === s) { const op = refOf(r, 5); if (op >= 0) { D.set(op, s); openings.push([s, op]); } }
          } else if (f & F_PROJECTS) {
            if (refOf(r, 4) === s) { const ft = refOf(r, 5); if (ft >= 0) D.set(ft, s); }
          } else if (f & F_PORT2EL) {
            if (refOf(r, 5) === s) { const pt = refOf(r, 4); if (pt >= 0) D.set(pt, s); }
          } else if (f & F_AGG) {
            if (refOf(r, 4) === s) for (const part of refRows(r, 5)) if (isPort(part)) D.set(part, s);
          }
        }
        void sid;
      }
      const fresh = new Map<number, string>();
      for (const s of live) {
        let why = '';
        for (let k = ix.invStart[s]!; k < ix.invStart[s + 1]! && !why; k++) {
          const r = ix.inv[k]!;
          if (inBlock(r) || D.has(r) || r === s) continue;
          const f = flags(r);
          if (f & F_AGG && refOf(r, 4) === s) {
            if (refRows(r, 5).some((part) => !D.has(part))) why = 'has parts';
          } else if (!(f & F_REL)) why = `referenced by ${describe(ix, r)}`;
        }
        if (!why && !o.removeHostsAnyway) {
          for (const [host, op] of openings) {
            if (host !== s) continue;
            for (let k = ix.invStart[op]!; k < ix.invStart[op + 1]! && !why; k++) {
              const r = ix.inv[k]!;
              if (!(flags(r) & F_FILLS) || refOf(r, 4) !== op) continue;
              const filler = refOf(r, 5);
              if (filler >= 0 && !D.has(filler)) why = 'hosts a door or window';
            }
          }
        }
        if (why) fresh.set(s, why);
      }
      if (fresh.size === 0) break;
      for (const [s, why] of fresh) vetoed.set(s, why);
    }

    // ---- B: delete, repair the relations, sweep what nothing uses any more
    const del = new Uint8Array(n);
    if (blk) for (let r = 0; r < n; r++) if (inBlock(r)) del[r] = 1;
    const cause = new Int32Array(n).fill(-1);
    const queue: number[] = [];
    for (const [r, c] of D) { del[r] = 1; cause[r] = c; queue.push(r); }
    const rewrite = new Map<number, string>();
    const dec = new Map<number, number>();
    const dangling: Array<{ cause: number; by: number; target: number }> = [];
    let relsDeleted = 0;
    let swept = 0;
    const dropped = (id: number): boolean => { const r = ix.rowOf(id); return r >= 0 && del[r] === 1; };
    // Relations are edited once per round, after the queue is empty: a storey's relation that lists thousands of elements is parsed once,
    // not once per removed element.
    const pending = new Map<number, number>();
    for (;;) {
      while (queue.length > 0) {
        const d = queue.pop()!;
        for (let k = ix.fwdStart[d]!; k < ix.fwdStart[d + 1]!; k++) {
          const t = ix.fwd[k]!;
          if (del[t] || weakEdge(d, t)) continue;
          const c = (dec.get(t) ?? 0) + 1;
          dec.set(t, c);
          if (sweepable(t)) {
            const sc = strongCount(t);
            if (sc > 0 && sc - c <= 0) { del[t] = 1; cause[t] = cause[d]!; swept++; queue.push(t); }
          }
        }
        for (let k = ix.invStart[d]!; k < ix.invStart[d + 1]!; k++) {
          const r = ix.inv[k]!;
          if (del[r]) continue;
          const f = flags(r);
          if ((f & F_STYLED) && styledItem(r) === d) {
            del[r] = 1; cause[r] = cause[d]!; swept++; queue.push(r);
          } else if (f & (F_LAYER | F_REL)) {
            if (!pending.has(r)) pending.set(r, cause[d]!);
          } else dangling.push({ cause: cause[d]!, by: r, target: d });
        }
      }
      if (pending.size === 0) break;
      for (const [r, c] of pending) {
        if (del[r]) continue;
        const t = trimRefs(rewrite.get(r) ?? stmt(r), dropped);
        if (t.single || t.emptied) {
          del[r] = 1; cause[r] = c; rewrite.delete(r); queue.push(r);
          if (flags(r) & F_REL) relsDeleted++; else swept++;
        } else if (t.changed) rewrite.set(r, t.text);
      }
      pending.clear();
    }
    const newVetoes = new Map<number, string>();
    const warnings: string[] = [];
    for (const dg of dangling) {
      if (seedSet.has(dg.cause) && !vetoed.has(dg.cause)) newVetoes.set(dg.cause, `referenced by ${describe(ix, dg.by)}`);
      else warnings.push(`${describe(ix, dg.by)} still refers to the removed ${describe(ix, dg.target)}`);
    }
    return { del, rewrite, D, newVetoes, relsDeleted, swept, warnings };
  };

  let res = attempt();
  for (let round = 0; res.newVetoes.size > 0 && round < 100; round++) {
    for (const [s, why] of res.newVetoes) vetoed.set(s, why);
    res = attempt();
  }

  // ---- the result
  const deleted = res.del;
  const del = new Set<number>();
  const removed: number[] = [];
  const cascaded: number[] = [];
  let blockLines = 0;
  let fillsCut = 0;
  for (let r = 0; r < n; r++) {
    if (!deleted[r]) continue;
    if (inBlock(r)) { blockLines++; continue; }
    del.add(ix.id[r]!);
    if (flags(r) & F_FILLS) {
      const op = refOf(r, 4);
      if (op >= 0 && !deleted[op]) fillsCut++;
    }
  }
  for (const [r, c] of res.D) {
    if (forced.has(r)) continue;
    (r === c ? removed : cascaded).push(ix.id[r]!);
  }
  removed.sort((a, b) => a - b);
  cascaded.sort((a, b) => a - b);
  for (const [s, why] of vetoed) kept.push({ expressId: ix.id[s]!, because: why });
  kept.sort((a, b) => a.expressId - b.expressId);
  const rewriteById = new Map<number, string>();
  for (const [r, t] of res.rewrite) if (!deleted[r]) rewriteById.set(ix.id[r]!, t);
  const warnings = [...res.warnings];
  if (ix.typeNames.includes('IFCSTRUCTURALANALYSISMODEL')) warnings.push('The file holds a structural analysis model: its relations are not handled and are only trimmed.');
  if (ix.typeNames.includes('IFCRELSEQUENCE')) warnings.push('The file holds IfcRelSequence relations: they are only trimmed.');
  return {
    deleted, delete: del, rewrite: rewriteById, removed, cascaded, kept, warnings,
    stats: {
      missing, removed: removed.length, cascaded: cascaded.length, relationsDeleted: res.relsDeleted, relationsTrimmed: rewriteById.size,
      fillsCut, swept: res.swept, linesDeleted: del.size, blockLinesDropped: blockLines,
    },
  };
}
