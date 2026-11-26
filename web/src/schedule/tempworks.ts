// Temporary works (scaffolding, falsework, formwork) for the 4D film. Pure: no three.js, no DOM.
//   rules (config.temporaryWorks)  ->  groups with their own timeline (plan.temporaryWorks, built by buildPlan)  ->  pieces (boxes)
//   the viewer draws as instanced meshes (src/anim/fourd/tempWorksLayer.ts).
// They are not elements of the IFC model: they exist only in the plan and the film. Design and limits: docs-features/4d-temporary-works.md.
//
// Frames: bboxes and pieces are in the IFC frame (Z up, metres) like FourDElement.bbox; the viewer converts (x, y, z) -> (x, z, -y).

import { compile, parseQuery, QueryError } from '../query';
import { FourDTable } from './model';
import type { FourDElement, FourDModel } from './model';
import { DAY } from './planTime';
import type { ElementTimeline, TempWorksConfig, TempWorksGroup, TempWorksKind, TempWorksRule, TempWorksSize } from './types';

export const TEMP_VERSION = 1 as const;
export const TEMP_KINDS: readonly TempWorksKind[] = ['scaffold', 'falsework', 'formwork'];
export const KIND_NAME: Record<TempWorksKind, string> = { scaffold: 'Scaffold', falsework: 'Falsework', formwork: 'Formwork' };

/** Default sizes in metres. */
export const TEMP_DEFAULTS: Required<TempWorksSize> = { offset: 0.3, width: 0.8, lift: 2.0, bay: 2.5, above: 1.0, spacing: 1.2, thickness: 0.05 };
/** Colours and opacity of the layer (scaffold yellow-orange, falsework blue, formwork plywood brown; semi-transparent). */
export const TEMP_COLOURS: Record<TempWorksKind, string> = { scaffold: '#f59e0b', falsework: '#2f7bd9', formwork: '#a9743f' };
export const TEMP_OPACITY: Record<TempWorksKind, number> = { scaffold: 0.78, falsework: 0.8, formwork: 0.6 };

const DEFAULT_TIMING: Record<TempWorksKind, { erectDays: number; strikeAfter: number; strikeDays: number }> = {
  scaffold: { erectDays: 2, strikeAfter: 1, strikeDays: 1 },
  falsework: { erectDays: 3, strikeAfter: 14, strikeDays: 1 },
  formwork: { erectDays: 1, strikeAfter: 3, strikeDays: 1 },
};

export const emptyTempWorks = (): TempWorksConfig => ({ version: TEMP_VERSION, rules: [] });

// ---------------------------------------------------------------- rules

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

const SIZE_KEYS: ReadonlyArray<keyof TempWorksSize> = ['offset', 'width', 'lift', 'bay', 'above', 'spacing', 'thickness'];

export interface ParsedTempWorks { config: TempWorksConfig | null; problems: string[] }

/** Read and check the `temporaryWorks` section (an object or JSON text). Rules that are wrong are listed in `problems` and left out. */
export function parseTempWorks(input: unknown): ParsedTempWorks {
  let v: unknown = input;
  if (typeof input === 'string') {
    try { v = JSON.parse(input); } catch (e) { return { config: null, problems: [`temporaryWorks: not JSON: ${e instanceof Error ? e.message : String(e)}`] }; }
  }
  if (!isObj(v)) return { config: null, problems: ['temporaryWorks: expected an object with "version" and "rules".'] };
  if (v.version !== TEMP_VERSION) return { config: null, problems: [`temporaryWorks: "version" must be ${TEMP_VERSION}${v.version === undefined ? ' (it is missing)' : `, not ${JSON.stringify(v.version)}`}.`] };
  if (!Array.isArray(v.rules)) return { config: null, problems: ['temporaryWorks: "rules" must be a list.'] };
  const problems: string[] = [];
  const rules: TempWorksRule[] = [];
  const ids = new Set<string>();
  v.rules.forEach((r, i) => {
    const at = `temporaryWorks.rules[${i}]`;
    if (!isObj(r)) { problems.push(`${at} is not an object`); return; }
    if (typeof r.kind !== 'string' || !(TEMP_KINDS as readonly string[]).includes(r.kind)) { problems.push(`${at}.kind must be scaffold, falsework or formwork`); return; }
    if (typeof r.for !== 'string' || !r.for.trim()) { problems.push(`${at}.for must be a criteria query`); return; }
    try { parseQuery(r.for); } catch (e) { problems.push(`${at}.for: ${e instanceof Error ? e.message : String(e)}`); return; }
    const rule: TempWorksRule = { kind: r.kind as TempWorksKind, for: r.for.trim() };
    if (r.id !== undefined) {
      if (typeof r.id !== 'string' || !/^[A-Za-z0-9_-]+$/.test(r.id)) { problems.push(`${at}.id must be letters, digits, - or _`); return; }
      if (ids.has(r.id)) { problems.push(`${at}.id "${r.id}" is used twice`); return; }
      ids.add(r.id);
      rule.id = r.id;
    }
    if (r.name !== undefined) { if (typeof r.name === 'string') rule.name = r.name; else problems.push(`${at}.name is not text`); }
    let bad = false;
    const timing = (key: 'erect' | 'strike', nums: string[], texts: string[]): Record<string, unknown> | undefined => {
      const t = r[key];
      if (t === undefined) return undefined;
      if (!isObj(t)) { problems.push(`${at}.${key} is not an object`); bad = true; return undefined; }
      const out: Record<string, unknown> = {};
      for (const k of nums) if (t[k] !== undefined) { if (num(t[k]) && (k !== 'duration' || (t[k] as number) >= 0)) out[k] = t[k]; else { problems.push(`${at}.${key}.${k} must be a number of days${k === 'duration' ? ' (0 or more)' : ''}`); bad = true; } }
      for (const k of texts) if (t[k] !== undefined) { if (typeof t[k] === 'string' && (t[k] as string).trim()) out[k] = (t[k] as string).trim(); else { problems.push(`${at}.${key}.${k} must be an activity code`); bad = true; } }
      return out;
    };
    const erect = timing('erect', ['daysBefore', 'duration'], ['activity']);
    const strike = timing('strike', ['daysAfter', 'duration'], ['activity', 'after']);
    if (r.size !== undefined) {
      if (!isObj(r.size)) { problems.push(`${at}.size is not an object`); bad = true; } else {
        const size: TempWorksSize = {};
        for (const k of SIZE_KEYS) if (r.size[k] !== undefined) { if (num(r.size[k]) && (r.size[k] as number) > 0) size[k] = r.size[k] as number; else { problems.push(`${at}.size.${k} must be a number above 0 (metres)`); bad = true; } }
        if (Object.keys(size).length) rule.size = size;
      }
    }
    if (bad) return;
    if (erect && Object.keys(erect).length) rule.erect = erect as TempWorksRule['erect'] & object;
    if (strike && Object.keys(strike).length) rule.strike = strike as TempWorksRule['strike'] & object;
    rules.push(rule);
  });
  return { config: { version: TEMP_VERSION, rules }, problems };
}

/** A rule with its id, name and sizes filled in. */
export interface ResolvedRule { id: string; kind: TempWorksKind; name: string; for: string; rule: TempWorksRule; size: Required<TempWorksSize> }

export function resolveRules(cfg: TempWorksConfig | undefined): ResolvedRule[] {
  if (!cfg) return [];
  return cfg.rules.map((rule, i) => ({
    id: rule.id ?? `tw${i + 1}`,
    kind: rule.kind,
    name: rule.name ?? KIND_NAME[rule.kind],
    for: rule.for,
    rule,
    size: { ...TEMP_DEFAULTS, ...(rule.size ?? {}) },
  }));
}

// ---------------------------------------------------------------- groups and timelines

export interface GroupContext {
  model: FourDModel;
  /** The plan's element timelines. */
  elements: readonly ElementTimeline[];
  /** Start and end of each activity in the plan's view (by activity code). */
  spans: ReadonlyMap<string, { start: number; end: number }>;
}

export interface GroupResult { groups: TempWorksGroup[]; problems: string[] }

/**
 * The groups of every rule: the permanent elements the rule selects, split by storey and by the activity that builds them, each with its
 * own erect and strike times. Elements without work of their own in the plan (existing) are not served.
 */
export function buildTempWorksGroups(cfg: TempWorksConfig | undefined, ctx: GroupContext): GroupResult {
  const rules = resolveRules(cfg);
  const groups: TempWorksGroup[] = [];
  const problems: string[] = [];
  if (!rules.length) return { groups, problems };
  const table = new FourDTable(ctx.model);
  const timeline = new Map(ctx.elements.map((e) => [e.globalId, e]));
  for (const r of rules) {
    let rows: number[] = [];
    try {
      const c = compile(parseQuery(r.for), table);
      for (let i = 0; i < table.size; i++) if (c.test(i)) rows.push(i);
    } catch (e) {
      if (e instanceof QueryError) { problems.push(`${r.id}: ${e.message}`); rows = []; } else throw e;
    }
    const byKey = new Map<string, { storey?: string; task: string; gids: string[]; start: number; end: number; zLo: number }>();
    for (const row of rows) {
      const el = ctx.model.elements[row]!;
      const tl = timeline.get(el.globalId);
      const iv = tl?.intervals.find((x) => x.state === 'active' || x.state === 'behind');
      if (!iv) continue;
      const key = `${el.storey ?? ''}|${iv.task}`;
      let g = byKey.get(key);
      if (!g) byKey.set(key, (g = { ...(el.storey !== undefined ? { storey: el.storey } : {}), task: iv.task, gids: [], start: iv.from, end: iv.to, zLo: Infinity }));
      g.gids.push(el.globalId);
      g.start = Math.min(g.start, iv.from);
      g.end = Math.max(g.end, iv.to);
      if (el.bbox) g.zLo = Math.min(g.zLo, el.bbox[2]);
    }
    const list = [...byKey.values()].sort((a, b) => (a.zLo - b.zLo) || (a.start - b.start) || a.task.localeCompare(b.task));
    list.forEach((g, n) => {
      const def = DEFAULT_TIMING[r.kind];
      const e = r.rule.erect;
      const s = r.rule.strike;
      let erect: { from: number; to: number };
      const ea = e?.activity ? ctx.spans.get(e.activity) : undefined;
      if (ea) erect = { from: ea.start, to: ea.end };
      else {
        const to = g.start - (e?.daysBefore ?? 1) * DAY;
        erect = { from: to - (e?.duration ?? def.erectDays) * DAY, to };
      }
      if (erect.to < erect.from) erect.to = erect.from;
      let strike: { from: number; to: number };
      const sa = s?.activity ? ctx.spans.get(s.activity) : undefined;
      if (sa) strike = { from: sa.start, to: sa.end };
      else {
        const anchor = s?.after ? ctx.spans.get(s.after)?.end ?? g.end : g.end;
        const from = anchor + (s?.daysAfter ?? def.strikeAfter) * DAY;
        strike = { from, to: from + (s?.duration ?? def.strikeDays) * DAY };
      }
      if (strike.from < erect.to) { const d = strike.to - strike.from; strike = { from: erect.to, to: erect.to + d }; }
      const where = g.storey !== undefined ? ` on ${g.storey}` : '';
      groups.push({
        id: `TW-${r.id}-${n + 1}`,
        rule: r.id,
        kind: r.kind,
        label: `${r.name}${where}`,
        ...(g.storey !== undefined ? { storey: g.storey } : {}),
        task: g.task,
        elements: g.gids,
        erect,
        strike,
        size: r.size,
      });
    });
  }
  groups.sort((a, b) => a.erect.from - b.erect.from || a.id.localeCompare(b.id));
  return { groups, problems };
}

/** How much of a group stands at plan time `t`: 0 before the erection, rising to 1, 1 while in use, falling to 0 while struck. */
export function groupProgress(g: Pick<TempWorksGroup, 'erect' | 'strike'>, t: number): number {
  if (t < g.erect.from) return 0;
  if (t < g.erect.to) return (t - g.erect.from) / Math.max(1, g.erect.to - g.erect.from);
  if (t < g.strike.from) return 1;
  if (t < g.strike.to) return 1 - (t - g.strike.from) / Math.max(1, g.strike.to - g.strike.from);
  return 0;
}

/** Alpha 0..1 of a piece with build `order` (0 first .. 1 last) at group progress `p`; `w` is the share of the progress a piece takes to fade. */
export function pieceAlpha(p: number, order: number, w: number): number {
  const x = (p - order * (1 - w)) / w;
  return x <= 0 ? 0 : x >= 1 ? 1 : x;
}

/** Fade share of a group's progress for a plan fade of `fadeIn` seconds (0 = at once). */
export const fadeShare = (fadeIn: number | undefined): number => (fadeIn === 0 ? 0.001 : 0.25);

/** Where in the lifecycle the group is at `t`. */
export function groupPhase(g: Pick<TempWorksGroup, 'erect' | 'strike'>, t: number): 'before' | 'erecting' | 'in use' | 'striking' | 'gone' {
  if (t < g.erect.from) return 'before';
  if (t < g.erect.to) return 'erecting';
  if (t < g.strike.from) return 'in use';
  if (t < g.strike.to) return 'striking';
  return 'gone';
}

// ---------------------------------------------------------------- geometry

export const PIECE_KINDS = ['standard', 'ledger', 'board', 'guard', 'prop', 'head beam', 'panel'] as const;
const K_STANDARD = 0, K_LEDGER = 1, K_BOARD = 2, K_GUARD = 3, K_PROP = 4, K_HEAD = 5, K_PANEL = 6;

export interface TempPieces {
  count: number;
  /** Group index (into the groups given) per piece. */
  group: Uint16Array;
  kind: Uint8Array;
  /** Run per piece: the index of the served element within its group. */
  run: Uint16Array;
  /** Lift (1-based; 0: none) per piece. */
  lift: Uint8Array;
  /** Build order 0..1. */
  order: Float32Array;
  /** cx, cy, cz, sx, sy, sz per piece, IFC frame. */
  box: Float32Array;
  /** Piece range [start, end) of each group (pieces of a group are contiguous). */
  range: Array<[number, number]>;
  /** Counts per group: bays, lifts, props, panels, standards. */
  stats: Array<{ runs: number; bays: number; lifts: number; props: number; panels: number; standards: number; pieces: number }>;
  /** Name of the served element of each run, per group. */
  runNames: string[][];
  /** The label of piece `i`: 'Temporary works: Scaffold, wall run W3, lift 2'. */
  describe(i: number): string;
}

type Box = [number, number, number, number, number, number];
interface Raw { kind: number; run: number; lift: number; order: number; box: Box }

const isWall = (e: FourDElement): boolean => /wall/i.test(e.ifcClass);
const isColumn = (e: FourDElement): boolean => /column|pile|footing|pier/i.test(e.ifcClass);
const isSlabLike = (e: FourDElement): boolean => /slab|plate|covering|roof/i.test(e.ifcClass);

function modelCentre(model: FourDModel): [number, number] {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const e of model.elements) if (e.bbox) { x0 = Math.min(x0, e.bbox[0]); y0 = Math.min(y0, e.bbox[1]); x1 = Math.max(x1, e.bbox[3]); y1 = Math.max(y1, e.bbox[4]); }
  return Number.isFinite(x0) ? [(x0 + x1) / 2, (y0 + y1) / 2] : [0, 0];
}

const box = (cx: number, cy: number, cz: number, sx: number, sy: number, sz: number): Box => [cx, cy, cz, sx, sy, sz];

function scaffoldPieces(g: TempWorksGroup, els: FourDElement[], centre: [number, number], out: Raw[]): { bays: number; lifts: number; standards: number } {
  const { offset, width, lift, bay, above } = g.size;
  const withBox = els.map((e, run) => ({ e, run })).filter((x) => x.e.bbox);
  let zLo = Infinity, zHi = -Infinity;
  for (const { e } of withBox) { zLo = Math.min(zLo, e.bbox![2]); zHi = Math.max(zHi, e.bbox![5]); }
  if (!withBox.length) return { bays: 0, lifts: 0, standards: 0 };
  const lifts = Math.max(1, Math.ceil((zHi - zLo) / lift - 1e-9));
  const H = lifts * lift + above;
  let bays = 0, standards = 0;
  for (const { e, run } of withBox) {
    const b = e.bbox!;
    const alongX = b[3] - b[0] >= b[4] - b[1];
    const lo = alongX ? b[0] : b[1];
    const hi = alongX ? b[3] : b[4];
    const mid = alongX ? (b[1] + b[4]) / 2 : (b[0] + b[3]) / 2;
    const cen = alongX ? centre[1] : centre[0];
    const sign = mid >= cen ? 1 : -1;
    const face = alongX ? (sign > 0 ? b[4] : b[1]) : sign > 0 ? b[3] : b[0];
    const rowIn = face + sign * offset;
    const rowOut = face + sign * (offset + width);
    const rowMid = (rowIn + rowOut) / 2;
    const nb = Math.max(1, Math.ceil((hi - lo) / bay - 1e-9));
    const bl = (hi - lo) / nb;
    bays += nb;
    const at = (along: number, across: number, z: number, la: number, lw: number, lz: number): Box => (alongX ? box(along, across, z, la, lw, lz) : box(across, along, z, lw, la, lz));
    for (let i = 0; i <= nb; i++) for (const row of [rowIn, rowOut]) { out.push({ kind: K_STANDARD, run, lift: 0, order: 0, box: at(lo + i * bl, row, zLo + H / 2, 0.05, 0.05, H) }); standards++; }
    for (let k = 1; k <= lifts; k++) {
      const z = zLo + k * lift;
      for (let i = 0; i < nb; i++) {
        const o = 0.1 + 0.9 * ((k - 1) + (i + 1) / nb) / lifts;
        const c = lo + (i + 0.5) * bl;
        out.push({ kind: K_LEDGER, run, lift: k, order: o, box: at(c, rowIn, z - 0.06, bl, 0.05, 0.05) });
        out.push({ kind: K_LEDGER, run, lift: k, order: o, box: at(c, rowOut, z - 0.06, bl, 0.05, 0.05) });
        out.push({ kind: K_BOARD, run, lift: k, order: o, box: at(c, rowMid, z, bl, width, 0.04) });
        out.push({ kind: K_GUARD, run, lift: k, order: o, box: at(c, rowOut, z + 1.0, bl, 0.04, 0.04) });
      }
    }
  }
  return { bays, lifts, standards };
}

function falseworkPieces(g: TempWorksGroup, els: FourDElement[], model: FourDModel, out: Raw[]): { props: number } {
  const { spacing } = g.size;
  const served = new Set(els);
  const slabs = model.elements.filter((e) => e.bbox && !served.has(e) && isSlabLike(e));
  const walls = model.elements.filter((e) => e.bbox && !served.has(e) && isWall(e));
  let ground = Infinity;
  for (const e of model.elements) if (e.bbox) ground = Math.min(ground, e.bbox[2]);
  if (!Number.isFinite(ground)) ground = 0;
  const pts = (a: number, b: number): number[] => {
    const len = b - a;
    if (len < 0.5 * spacing) return [(a + b) / 2];
    const n = Math.ceil(len / spacing - 1e-9) + 1;
    return Array.from({ length: n }, (_v, i) => a + (len * i) / (n - 1));
  };
  let props = 0;
  els.forEach((e, run) => {
    const b = e.bbox;
    if (!b) return;
    const inset = Math.min(0.2, (b[3] - b[0]) / 4, (b[4] - b[1]) / 4);
    const xs = pts(b[0] + inset, b[3] - inset);
    const ys = pts(b[1] + inset, b[4] - inset);
    const soffit = b[2];
    const headH = 0.1;
    const total = xs.length * ys.length;
    let idx = 0;
    for (const y of ys) {
      for (const x of xs) {
        idx++;
        let base = ground;
        for (const s of slabs) { const sb = s.bbox!; if (x >= sb[0] && x <= sb[3] && y >= sb[1] && y <= sb[4] && sb[5] <= soffit - 0.2) base = Math.max(base, sb[5]); }
        if (walls.some((w) => { const wb = w.bbox!; return x >= wb[0] - 0.05 && x <= wb[3] + 0.05 && y >= wb[1] - 0.05 && y <= wb[4] + 0.05 && wb[2] < soffit && wb[5] > base; })) continue;
        const h = soffit - headH - base;
        if (h < 0.1) continue;
        out.push({ kind: K_PROP, run, lift: 0, order: 0.05 + 0.55 * (idx / total), box: box(x, y, base + h / 2, 0.06, 0.06, h) });
        props++;
      }
    }
    ys.forEach((y, i) => out.push({ kind: K_HEAD, run, lift: 0, order: 0.65 + 0.35 * ((i + 1) / ys.length), box: box((b[0] + b[3]) / 2, y, soffit - headH / 2, b[3] - b[0], headH, headH) }));
  });
  return { props };
}

const PANEL_LEN = 2.4;

function formworkPieces(g: TempWorksGroup, els: FourDElement[], out: Raw[]): { panels: number } {
  const t = g.size.thickness;
  let panels = 0;
  const strip = (run: number, alongX: boolean, lo: number, hi: number, across: number, z0: number, z1: number, order: (i: number, n: number) => number): void => {
    const n = Math.max(1, Math.ceil((hi - lo) / PANEL_LEN - 1e-9));
    const l = (hi - lo) / n;
    for (let i = 0; i < n; i++) {
      const c = lo + (i + 0.5) * l;
      const bx = alongX ? box(c, across, (z0 + z1) / 2, l, t, z1 - z0) : box(across, c, (z0 + z1) / 2, t, l, z1 - z0);
      out.push({ kind: K_PANEL, run, lift: 0, order: order(i, n), box: bx });
      panels++;
    }
  };
  const ord = (k: number, faces: number) => (i: number, n: number): number => (k + (i + 1) / n) / faces;
  els.forEach((e, run) => {
    const b = e.bbox;
    if (!b) return;
    if (isWall(e) || isColumn(e)) {
      const col = !isWall(e);
      const faces = col ? 4 : 2;
      const alongX = b[3] - b[0] >= b[4] - b[1];
      if (col) {
        strip(run, true, b[0] - t, b[3] + t, b[1] - t / 2, b[2], b[5], ord(0, 4));
        strip(run, true, b[0] - t, b[3] + t, b[4] + t / 2, b[2], b[5], ord(1, 4));
        strip(run, false, b[1], b[4], b[0] - t / 2, b[2], b[5], ord(2, 4));
        strip(run, false, b[1], b[4], b[3] + t / 2, b[2], b[5], ord(3, 4));
      } else if (alongX) {
        strip(run, true, b[0], b[3], b[1] - t / 2, b[2], b[5], ord(0, faces));
        strip(run, true, b[0], b[3], b[4] + t / 2, b[2], b[5], ord(1, faces));
      } else {
        strip(run, false, b[1], b[4], b[0] - t / 2, b[2], b[5], ord(0, faces));
        strip(run, false, b[1], b[4], b[3] + t / 2, b[2], b[5], ord(1, faces));
      }
    } else {
      // slabs, beams and the rest: the soffit, then the edges
      const nx = Math.max(1, Math.ceil((b[3] - b[0]) / PANEL_LEN - 1e-9));
      const ny = Math.max(1, Math.ceil((b[4] - b[1]) / PANEL_LEN - 1e-9));
      const lx = (b[3] - b[0] + 2 * t) / nx;
      const ly = (b[4] - b[1] + 2 * t) / ny;
      for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) {
        out.push({ kind: K_PANEL, run, lift: 0, order: 0.5 * ((i * ny + j + 1) / (nx * ny)), box: box(b[0] - t + (i + 0.5) * lx, b[1] - t + (j + 0.5) * ly, b[2] - t / 2, lx, ly, t) });
        panels++;
      }
      const z1 = b[5];
      const z0 = b[2];
      strip(run, true, b[0] - t, b[3] + t, b[1] - t / 2, z0, z1, (i, n) => 0.5 + 0.125 * ((i + 1) / n));
      strip(run, true, b[0] - t, b[3] + t, b[4] + t / 2, z0, z1, (i, n) => 0.625 + 0.125 * ((i + 1) / n));
      strip(run, false, b[1], b[4], b[0] - t / 2, z0, z1, (i, n) => 0.75 + 0.125 * ((i + 1) / n));
      strip(run, false, b[1], b[4], b[3] + t / 2, z0, z1, (i, n) => 0.875 + 0.125 * ((i + 1) / n));
    }
  });
  return { panels };
}

/** The pieces of every group (instanced boxes). The groups' `elements` must be GlobalIds of `model`. */
export function generatePieces(groups: readonly TempWorksGroup[], model: FourDModel): TempPieces {
  const byGid = new Map(model.elements.map((e) => [e.globalId, e]));
  const centre = modelCentre(model);
  const all: Raw[] = [];
  const group: number[] = [];
  const range: Array<[number, number]> = [];
  const stats: TempPieces['stats'] = [];
  const runNames: string[][] = [];
  groups.forEach((g, gi) => {
    const els = g.elements.map((id) => byGid.get(id)).filter((e): e is FourDElement => !!e);
    const start = all.length;
    const part: Raw[] = [];
    const s = { runs: els.length, bays: 0, lifts: 0, props: 0, panels: 0, standards: 0, pieces: 0 };
    if (g.kind === 'scaffold') { const r = scaffoldPieces(g, els, centre, part); s.bays = r.bays; s.lifts = r.lifts; s.standards = r.standards; }
    else if (g.kind === 'falsework') s.props = falseworkPieces(g, els, model, part).props;
    else s.panels = formworkPieces(g, els, part).panels;
    for (const p of part) { all.push(p); group.push(gi); }
    s.pieces = all.length - start;
    range.push([start, all.length]);
    stats.push(s);
    runNames.push(els.map((e, i) => (g.kind === 'scaffold' ? `wall run W${i + 1}` : e.name || e.ifcClass)));
  });
  const n = all.length;
  const out: TempPieces = {
    count: n,
    group: Uint16Array.from(group),
    kind: new Uint8Array(n),
    run: new Uint16Array(n),
    lift: new Uint8Array(n),
    order: new Float32Array(n),
    box: new Float32Array(n * 6),
    range,
    stats,
    runNames,
    describe(i: number): string {
      if (i < 0 || i >= n) return '';
      const g = groups[this.group[i]!]!;
      const rn = runNames[this.group[i]!]![this.run[i]!] ?? '';
      const lift = this.lift[i]! > 0 ? `, lift ${this.lift[i]}` : '';
      const what = g.kind === 'scaffold' ? '' : `, ${PIECE_KINDS[this.kind[i]!]}`;
      return `Temporary works: ${KIND_NAME[g.kind]}, ${rn}${lift}${what}`;
    },
  };
  all.forEach((p, i) => {
    out.kind[i] = p.kind;
    out.run[i] = p.run;
    out.lift[i] = p.lift;
    out.order[i] = p.order;
    for (let k = 0; k < 6; k++) out.box[i * 6 + k] = p.box[k]!;
  });
  return out;
}
