// The 4D configuration in the viewer (no DOM): which activity code, user field or WBS level means location, trade and zone, the table that
// maps schedule values to the model's values, the trade queries, the style, and reading and writing `.4d.json`. The panel
// (schedulePanel.ts) draws it; the contract is `FourDConfig` in src/schedule/types.ts. Tested in tests/map4d-schedule-config.test.ts.

import { readTaskAttr } from '../schedule/attrs';
import { isBuildType } from '../schedule/planTime';
import { DEFAULT_STYLE } from '../schedule/types';
import type { AttributeKind, FourDConfig, FourDStyle, Schedule, ScheduleAttrSource, SplitRule } from '../schedule/types';

export const CONFIG_SCHEMA = 'xray-4d-config/1' as const;
export const ATTRS: readonly AttributeKind[] = ['location', 'trade', 'zone'];

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

/** A config that links nothing yet: no schedule sources, the model read from the 4D mapping tool's values first. */
export function emptyConfig(): FourDConfig {
  return {
    schema: CONFIG_SCHEMA,
    schedule: { location: [], trade: [] },
    model: {
      location: [{ property: 'Xray_4D.Location' }, { storey: true }],
      trade: [{ property: 'Xray_4D.Trade' }],
      zone: [{ property: 'Xray_4D.Zone' }, { zone: true }],
    },
    style: clone(DEFAULT_STYLE),
  };
}

// ---------------------------------------------------------------- sources

export interface SourceChoice { key: string; label: string; source: ScheduleAttrSource }

/** The key of a source in a drop-down: `code:Level`, `udf:Area`, `wbs:1`; a pattern has `pattern:...` (listed only when in use). */
export function sourceKey(s: ScheduleAttrSource | undefined): string {
  if (!s) return '';
  if ('code' in s) return `code:${s.code}`;
  if ('udf' in s) return `udf:${s.udf}`;
  if ('wbsLevel' in s) return `wbs:${s.wbsLevel}`;
  if ('wbsPattern' in s) return `pattern:wbs:${s.wbsPattern}`;
  return `pattern:name:${s.namePattern}`;
}

/** Depth of the WBS under the project: the longest path of any activity. */
export function wbsDepth(schedule: Schedule): number {
  let d = 0;
  for (const t of schedule.tasks) d = Math.max(d, t.wbsPath.length);
  return d;
}

/** What the schedule offers as a source: its code types, user fields and WBS levels. `current` sources not in the list are added (a pattern from a file). */
export function sourceChoices(schedule: Schedule | null, current: readonly ScheduleAttrSource[] = []): SourceChoice[] {
  const out: SourceChoice[] = [];
  if (schedule) {
    for (const code of Object.keys(schedule.codeTypes).sort()) out.push({ key: `code:${code}`, label: `Activity code: ${code}`, source: { code } });
    for (const udf of [...schedule.udfLabels].sort()) out.push({ key: `udf:${udf}`, label: `User field: ${udf}`, source: { udf } });
    for (let i = 0; i < wbsDepth(schedule); i++) out.push({ key: `wbs:${i}`, label: `WBS level ${i + 1}`, source: { wbsLevel: i } });
  }
  for (const s of current) {
    const key = sourceKey(s);
    if (!out.some((c) => c.key === key)) out.push({ key, label: customLabel(s), source: s });
  }
  return out;
}

function customLabel(s: ScheduleAttrSource): string {
  if ('code' in s) return `Activity code: ${s.code}`;
  if ('udf' in s) return `User field: ${s.udf}`;
  if ('wbsLevel' in s) return `WBS level ${s.wbsLevel + 1}`;
  if ('wbsPattern' in s) return `WBS pattern ${s.wbsPattern}`;
  return `Name pattern ${s.namePattern}`;
}

/** Use one source (or none: key '') for an attribute. Returns a new config; other sources of the file stay when `keepRest` (a config from a file may list several). */
export function setSource(config: FourDConfig, attr: AttributeKind, choice: SourceChoice | null): FourDConfig {
  const c = clone(config);
  const list = choice ? [clone(choice.source)] : [];
  if (attr === 'zone') {
    if (list.length) c.schedule.zone = list;
    else delete c.schedule.zone;
  } else c.schedule[attr] = list;
  return c;
}

export const sourcesOf = (config: FourDConfig, attr: AttributeKind): ScheduleAttrSource[] => (attr === 'zone' ? config.schedule.zone ?? [] : config.schedule[attr]);

/**
 * A first guess for a schedule: a code type, field or WBS level whose name says location (Level, Floor, Storey, Zone-like names),
 * trade (Trade, Discipline, Work package). Nothing found: the attribute stays unset. Never overwrites a source that is already set.
 */
export function guessConfig(schedule: Schedule, base: FourDConfig = emptyConfig()): FourDConfig {
  let c = clone(base);
  const names: Array<{ key: string; label: string; source: ScheduleAttrSource }> = sourceChoices(schedule).map((s) => ({ key: s.key, label: s.key.split(':')[1] ?? '', source: s.source }));
  const find = (re: RegExp): SourceChoice | null => {
    const hit = names.find((n) => !n.key.startsWith('wbs:') && re.test(n.label));
    return hit ? { key: hit.key, label: hit.label, source: hit.source } : null;
  };
  const want: Array<[AttributeKind, RegExp]> = [['location', /^(level|floor|storey|story|geschoss|etage)/i], ['trade', /^(trade|discipline|craft|gewerk|work ?package)/i], ['zone', /^(zone|area|section|bereich)/i]];
  for (const [attr, re] of want) {
    if (sourcesOf(c, attr).length) continue;
    const hit = find(re);
    if (hit) c = setSource(c, attr, hit);
  }
  c.schedule.project = schedule.project.shortName;
  return c;
}

// ---------------------------------------------------------------- the value table

export interface ValueRow {
  /** The schedule's value. */
  schedule: string;
  /** Activities that carry it. */
  count: number;
  /** The model value it maps to ('' = used as it is). */
  model: string;
}

/** The distinct values the schedule gives an attribute (building activities only), with the mapped model value. */
export function valueRows(schedule: Schedule | null, config: FourDConfig, attr: AttributeKind): ValueRow[] {
  if (!schedule) return [];
  const sources = sourcesOf(config, attr);
  const counts = new Map<string, number>();
  for (const t of schedule.tasks) {
    if (!isBuildType(t)) continue;
    const v = readTaskAttr(t, sources);
    if (v !== undefined) counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  const table = config.values?.[attr] ?? {};
  const rows: ValueRow[] = [...counts].map(([v, n]) => ({ schedule: v, count: n, model: Object.prototype.hasOwnProperty.call(table, v) ? table[v]! : '' }));
  // keys of the table that no activity uses (regex keys, or values of another schedule) stay visible so they can be edited away
  for (const k of Object.keys(table)) if (!counts.has(k)) rows.push({ schedule: k, count: 0, model: table[k]! });
  return rows.sort((a, b) => a.schedule.localeCompare(b.schedule, undefined, { numeric: true }));
}

/** Map a schedule value to a model value ('' removes the row: the value is used as it is). */
export function setValueMap(config: FourDConfig, attr: AttributeKind, scheduleValue: string, modelValue: string): FourDConfig {
  const c = clone(config);
  const values = (c.values ??= {});
  const table = { ...(values[attr] ?? {}) };
  if (modelValue.trim() === '') delete table[scheduleValue];
  else table[scheduleValue] = modelValue.trim();
  if (Object.keys(table).length) values[attr] = table;
  else delete values[attr];
  if (Object.keys(values).length === 0) delete c.values;
  return c;
}

/** The raw trade values of the schedule (the keys the trade queries are written for). */
export function tradeKeys(schedule: Schedule | null, config: FourDConfig): string[] {
  const keys = new Set(valueRows(schedule, config, 'trade').map((r) => r.schedule));
  for (const k of Object.keys(config.tradeQueries ?? {})) keys.add(k);
  return [...keys].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

/** Set the element query of a trade value ('' removes it). */
export function setTradeQuery(config: FourDConfig, trade: string, query: string): FourDConfig {
  const c = clone(config);
  const q = { ...(c.tradeQueries ?? {}) };
  if (query.trim() === '') delete q[trade];
  else q[trade] = query.trim();
  if (Object.keys(q).length) c.tradeQueries = q;
  else delete c.tradeQueries;
  return c;
}

export function setExisting(config: FourDConfig, query: string): FourDConfig {
  const c = clone(config);
  if (query.trim()) c.model.existing = query.trim();
  else delete c.model.existing;
  return c;
}

export function setSplit(config: FourDConfig, trade: string, rule: SplitRule | ''): FourDConfig {
  const c = clone(config);
  const s = { ...(c.split ?? {}) };
  if (!rule) delete s[trade];
  else s[trade] = rule;
  if (Object.keys(s).length) c.split = s;
  else delete c.split;
  return c;
}

export function setStyle(config: FourDConfig, patch: Partial<FourDStyle>): FourDConfig {
  const c = clone(config);
  c.style = { ...c.style, ...clone(patch) };
  return c;
}

// ---------------------------------------------------------------- the file

const VIEWS = ['planned', 'actual', 'variance'];
const SPLITS: readonly SplitRule[] = ['none', 'sweep_x', 'sweep_minus_x', 'sweep_y', 'sweep_minus_y', 'sweep_z', 'sweep_minus_z', 'by_storey', 'by_name'];

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

function validSources(v: unknown, path: string, problems: string[]): ScheduleAttrSource[] {
  if (!Array.isArray(v)) { problems.push(`${path} is not a list`); return []; }
  const out: ScheduleAttrSource[] = [];
  v.forEach((s, i) => {
    if (isObj(s) && (typeof s.code === 'string' || typeof s.udf === 'string' || typeof s.wbsLevel === 'number' || typeof s.wbsPattern === 'string' || typeof s.namePattern === 'string')) out.push(s as unknown as ScheduleAttrSource);
    else problems.push(`${path}[${i}] is not a source (code, udf, wbsLevel, wbsPattern or namePattern)`);
  });
  return out;
}

const stringMap = (v: unknown, path: string, problems: string[]): Record<string, string> | undefined => {
  if (v === undefined) return undefined;
  if (!isObj(v)) { problems.push(`${path} is not an object`); return undefined; }
  const out: Record<string, string> = {};
  for (const [k, x] of Object.entries(v)) { if (typeof x === 'string') out[k] = x; else problems.push(`${path}.${k} is not text`); }
  return out;
};

export interface ParsedConfig { config: FourDConfig | null; problems: string[] }

/** Read a `.4d.json` (text or object). Fields that are wrong are listed in `problems` and left out; a file that is no config gives `config: null`. */
export function parseConfig(input: unknown): ParsedConfig {
  let v: unknown = input;
  if (typeof input === 'string') {
    try { v = JSON.parse(input); } catch (e) { return { config: null, problems: [`Not JSON: ${e instanceof Error ? e.message : String(e)}`] }; }
  }
  if (!isObj(v)) return { config: null, problems: ['Not a 4D configuration: expected an object.'] };
  if (v.schema !== CONFIG_SCHEMA) return { config: null, problems: [`Not a 4D configuration: "schema" must be "${CONFIG_SCHEMA}".`] };
  const problems: string[] = [];
  const base = emptyConfig();
  const sch = isObj(v.schedule) ? v.schedule : {};
  const mod = isObj(v.model) ? v.model : {};
  if (!isObj(v.schedule)) problems.push('"schedule" is missing');
  const c: FourDConfig = {
    schema: CONFIG_SCHEMA,
    schedule: {
      ...(typeof sch.project === 'string' ? { project: sch.project } : {}),
      location: sch.location === undefined ? [] : validSources(sch.location, 'schedule.location', problems),
      trade: sch.trade === undefined ? [] : validSources(sch.trade, 'schedule.trade', problems),
      ...(sch.zone !== undefined ? { zone: validSources(sch.zone, 'schedule.zone', problems) } : {}),
    },
    model: {
      location: Array.isArray(mod.location) ? (mod.location as FourDConfig['model']['location']) : base.model.location,
      trade: Array.isArray(mod.trade) ? (mod.trade as FourDConfig['model']['trade']) : base.model.trade,
      ...(Array.isArray(mod.zone) ? { zone: mod.zone as NonNullable<FourDConfig['model']['zone']> } : { zone: base.model.zone! }),
      ...(typeof mod.existing === 'string' && mod.existing.trim() ? { existing: mod.existing } : {}),
    },
    style: { ...clone(DEFAULT_STYLE) },
  };
  if (isObj(v.values)) {
    const values: NonNullable<FourDConfig['values']> = {};
    for (const a of ATTRS) { const m = stringMap(v.values[a], `values.${a}`, problems); if (m) values[a] = m; }
    if (Object.keys(values).length) c.values = values;
  }
  const tq = stringMap(v.tradeQueries, 'tradeQueries', problems);
  if (tq) c.tradeQueries = tq;
  if (isObj(v.activities)) c.activities = v.activities as NonNullable<FourDConfig['activities']>;
  if (isObj(v.split)) {
    const s: Record<string, SplitRule> = {};
    for (const [k, x] of Object.entries(v.split)) { if (typeof x === 'string' && (SPLITS as readonly string[]).includes(x)) s[k] = x as SplitRule; else problems.push(`split.${k} is not a split rule`); }
    c.split = s;
  }
  if (isObj(v.style)) {
    const st = v.style as Partial<FourDStyle>;
    if (st.view !== undefined && !VIEWS.includes(st.view)) problems.push(`style.view "${String(st.view)}" is not planned, actual or variance`);
    const { view, ...rest } = st;
    c.style = { ...c.style, ...clone(rest), ...(view && VIEWS.includes(view) ? { view } : {}) };
  }
  return { config: c, problems };
}

export function serializeConfig(c: FourDConfig): string {
  return JSON.stringify(c, null, 2) + '\n';
}
