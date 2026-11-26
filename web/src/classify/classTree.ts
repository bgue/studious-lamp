// The standard tree of the classification view: elements grouped by 1 to 4 levels taken from their facet values, the discipline,
// the storey or the IFC class, or by UniFormat II codes mapped from them. Pure, no DOM. Docs: docs-features/classification-tree.md,
// docs/design/classification-facets.md sections 6 and 7.
//
// Presets are data (`PRESETS`): a later Concrete preset (Method, role, strength class) is one more entry whose level ids are
// facet ids; any level id that is not built in reads `XR_<id>.Code` of the element's facet set.

import type { ElementId } from '../types';
import type { TreeNode } from '../ui/treeModel';
import type { FacetResult } from './facets/defs';

export interface CodeLabel {
  code: string;
  label: string;
}

/** What the tree needs to know about one element. */
export interface ClassInfo {
  id: ElementId;
  name: string;
  globalId: string;
  ifcClass: string;
  storey: string;
  /** Facet results by facet id (any id: the facet set of the element). */
  facets: Readonly<Record<string, FacetResult | undefined>>;
  discipline?: CodeLabel;
  subDiscipline?: CodeLabel;
  /** The discipline result is below its review threshold. */
  disciplineReview?: boolean;
}

/** Built-in level ids besides facet ids. UF1 to UF3 are the UniFormat II levels. */
export const BUILTIN_LEVELS = ['Discipline', 'SubDiscipline', 'Storey', 'IfcClass', 'UF1', 'UF2', 'UF3'] as const;

/** The levels a person can choose in the "Group by" control, in the order they are offered. */
export const LEVEL_CHOICES: ReadonlyArray<{ id: string; label: string }> = [
  { id: 'Phase', label: 'Phase' },
  { id: 'Discipline', label: 'Discipline' },
  { id: 'SubDiscipline', label: 'Sub-discipline' },
  { id: 'Trade', label: 'Trade' },
  { id: 'Placement', label: 'Placement' },
  { id: 'Material', label: 'Material' },
  { id: 'Orientation', label: 'Orientation' },
  { id: 'Storey', label: 'Storey' },
  { id: 'IfcClass', label: 'IFC class' },
  { id: 'UF1', label: 'UniFormat level 1' },
  { id: 'UF2', label: 'UniFormat level 2' },
  { id: 'UF3', label: 'UniFormat level 3' },
];

export const levelLabel = (id: string): string => LEVEL_CHOICES.find((l) => l.id === id)?.label ?? id;

export interface ClassPreset {
  id: string;
  label: string;
  levels: string[];
}

export const MAX_LEVELS = 4;

export const PRESETS: readonly ClassPreset[] = [
  { id: 'construction', label: 'Construction', levels: ['Phase', 'Trade', 'IfcClass'] },
  { id: 'ownership', label: 'Ownership', levels: ['Discipline', 'SubDiscipline', 'IfcClass'] },
  { id: 'envelope', label: 'Envelope', levels: ['Placement', 'Material', 'IfcClass'] },
  { id: 'uniformat', label: 'Standard (UniFormat II)', levels: ['UF1', 'UF2', 'UF3'] },
];

export const NOT_CLASSIFIED = 'Not classified';
export const NONE_CODE = '\u0000none';

// ---------------------------------------------------------------- UniFormat II

export interface UfNode {
  code: string;
  title: string;
  children?: UfNode[];
}

export interface UfRule {
  when: { class?: string[]; placement?: string[]; phase?: string[]; trade?: string[]; discipline?: string[] };
  code: string;
}

export interface UniformatTable {
  title: string;
  levels: UfNode[];
  rules: UfRule[];
  fallbacks: Record<string, string>;
  /** Title of every code of levels 1 to 3. */
  titles: Map<string, string>;
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const strList = (v: unknown): string[] | undefined => (Array.isArray(v) && v.every((x) => typeof x === 'string') ? (v as string[]) : undefined);

/** Parse the JSON of a mapping table. Returns the table, or the problems in plain words. */
export function parseUniformat(json: unknown): { table: UniformatTable | null; errors: string[] } {
  const errors: string[] = [];
  if (!isObj(json) || json['schema'] !== 'xray-uniformat2/1') return { table: null, errors: ['The file is not a UniFormat mapping (schema "xray-uniformat2/1").'] };
  const titles = new Map<string, string>();
  const walk = (a: unknown, depth: number): UfNode[] => {
    if (!Array.isArray(a)) {
      errors.push('"levels" must be a list.');
      return [];
    }
    const out: UfNode[] = [];
    for (const n of a) {
      if (!isObj(n) || typeof n['code'] !== 'string' || typeof n['title'] !== 'string') {
        errors.push('A level entry needs a code and a title.');
        continue;
      }
      titles.set(n['code'], n['title']);
      out.push({ code: n['code'], title: n['title'], children: depth < 3 && n['children'] !== undefined ? walk(n['children'], depth + 1) : undefined });
    }
    return out;
  };
  const levels = walk(json['levels'], 1);
  const rules: UfRule[] = [];
  const rawRules = json['rules'];
  if (!Array.isArray(rawRules)) errors.push('"rules" must be a list.');
  else {
    rawRules.forEach((r, i) => {
      if (!isObj(r) || typeof r['code'] !== 'string' || !isObj(r['when'])) {
        errors.push(`Rule ${i + 1} needs "when" and "code".`);
        return;
      }
      if (!titles.has(r['code'])) {
        errors.push(`Rule ${i + 1} uses the code ${r['code']}, which is not in "levels".`);
        return;
      }
      const w = r['when'];
      rules.push({ when: { class: strList(w['class']), placement: strList(w['placement']), phase: strList(w['phase']), trade: strList(w['trade']), discipline: strList(w['discipline']) }, code: r['code'] });
    });
  }
  const fallbacks: Record<string, string> = {};
  if (isObj(json['fallbacks'])) for (const [k, v] of Object.entries(json['fallbacks'])) if (typeof v === 'string' && titles.has(v)) fallbacks[k] = v;
  if (errors.length > 0 || levels.length === 0) return { table: null, errors: errors.length ? errors : ['The table has no levels.'] };
  return { table: { title: typeof json['title'] === 'string' ? json['title'] : 'UniFormat II', levels, rules, fallbacks, titles }, errors: [] };
}

const codeOf = (r: FacetResult | undefined): string => r?.code ?? '';

/** The UniFormat II code of an element (level 3, else 2, else 1), or null. */
export function mapUniformat(t: UniformatTable, e: ClassInfo): string | null {
  const cls = e.ifcClass;
  const placement = codeOf(e.facets['Placement']);
  const phase = codeOf(e.facets['Phase']);
  const trade = codeOf(e.facets['Trade']);
  const disc = e.discipline?.code ?? '';
  const has = (list: string[] | undefined, v: string): boolean => list === undefined || list.includes(v);
  for (const r of t.rules) {
    const w = r.when;
    if (w.class && !w.class.some((c) => cls.startsWith(c))) continue;
    if (!has(w.placement, placement) || !has(w.phase, phase) || !has(w.trade, trade) || !has(w.discipline, disc)) continue;
    return r.code;
  }
  return t.fallbacks[phase] ?? null;
}

/** The part of a UniFormat code at level 1, 2 or 3 (A, A10, A1010), or null when the code is not that deep. */
export function ufAtLevel(code: string | null, level: 1 | 2 | 3): string | null {
  if (!code) return null;
  const n = level === 1 ? 1 : level === 2 ? 3 : 5;
  return code.length >= n ? code.slice(0, n) : null;
}

// ---------------------------------------------------------------- levels

export interface BuildOptions {
  levels: readonly string[];
  uniformat?: UniformatTable | null;
  /** Preferred order of the values of a level (codes). Others follow alphabetically; "Not classified" is last. */
  order?: Readonly<Record<string, readonly string[]>>;
  /** Column that holds the discipline and sub-discipline codes (for the queries). */
  columns?: { discipline: string; subDiscipline: string };
}

interface Value extends CodeLabel {
  review: boolean;
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

/** True when any facet value of the element is below its review threshold. */
export function needsReview(e: ClassInfo): boolean {
  if (e.disciplineReview) return true;
  for (const r of Object.values(e.facets)) if (r?.needsReview) return true;
  return false;
}

/** The value of an element at a level, or null (it goes to "Not classified"). */
export function levelValue(e: ClassInfo, level: string, opts: Pick<BuildOptions, 'uniformat'>): CodeLabel | null {
  switch (level) {
    case 'Discipline':
      return e.discipline ?? null;
    case 'SubDiscipline':
      return e.subDiscipline ?? null;
    case 'Storey':
      return e.storey ? { code: e.storey, label: e.storey } : null;
    case 'IfcClass':
      return e.ifcClass ? { code: e.ifcClass, label: e.ifcClass } : null;
    case 'UF1':
    case 'UF2':
    case 'UF3': {
      const t = opts.uniformat;
      if (!t) return null;
      const c = ufAtLevel(mapUniformat(t, e), Number(level[2]) as 1 | 2 | 3);
      return c ? { code: c, label: t.titles.get(c) ?? c } : null;
    }
    default: {
      const r = e.facets[level];
      return r?.code ? { code: r.code, label: r.label || r.code } : null;
    }
  }
}

/** The query that selects the elements with a value at a level, or null when there is no such query (UniFormat). */
export function levelQuery(level: string, code: string | null, cols?: BuildOptions['columns']): string | null {
  const lit = (s: string): string => `'${s.replace(/'/g, "''")}'`;
  const col = (c: string): string => (/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$/.test(c) ? c : `"${c.replace(/"/g, '""')}"`);
  let c: string;
  switch (level) {
    case 'Discipline':
      c = col(cols?.discipline ?? 'XR_Discipline.Discipline');
      break;
    case 'SubDiscipline':
      c = col(cols?.subDiscipline ?? 'XR_Discipline.SubDiscipline');
      break;
    case 'Storey':
      c = 'storey';
      break;
    case 'IfcClass':
      c = 'class';
      break;
    case 'UF1':
    case 'UF2':
    case 'UF3':
      return null;
    default:
      c = `XR_${level}.Code`;
  }
  return code === null ? `${c} IS NULL` : `${c} = ${lit(code)}`;
}

const sorter = (order: readonly string[] | undefined) => {
  const rank = (c: string): number => {
    const i = order ? order.indexOf(c) : -1;
    return i < 0 ? Number.MAX_SAFE_INTEGER : i;
  };
  return (a: string, b: string): number => rank(a) - rank(b) || collator.compare(a, b);
};

interface Group {
  value: Value | null;
  items: ClassInfo[];
}

function nodeFrom(kind: TreeNode['kind'], key: string, label: string, title: string, children: TreeNode[], query: string | null): TreeNode {
  const ids: ElementId[] = [];
  let review = 0;
  for (const c of children) {
    for (const id of c.ids) ids.push(id);
    review += c.review ?? 0;
  }
  return { key, kind, label, title, count: ids.length, ids, elementId: null, children, review, query };
}

/**
 * Build the tree: one node per distinct value at each level (elements without a value under "Not classified"), then the elements.
 * Each group node carries `review` (elements below the review threshold) and `query` (the saved-set query of the node, or null).
 */
export function buildClassTree(infos: readonly ClassInfo[], opts: BuildOptions): TreeNode[] {
  const levels = opts.levels.slice(0, MAX_LEVELS);
  const walk = (list: readonly ClassInfo[], depth: number, parentKey: string, parentQuery: string[] | null): TreeNode[] => {
    if (depth >= levels.length) {
      return [...list]
        .sort((a, b) => collator.compare(a.name || a.globalId, b.name || b.globalId) || a.id - b.id)
        .map((e) => {
          const full = e.name && e.name.trim() ? e.name : e.globalId;
          const rv = needsReview(e);
          return {
            key: `${parentKey}/e:${e.id}`, kind: 'element', label: full.length > 44 ? full.slice(0, 43) + '…' : full,
            title: `${full}\n${e.ifcClass}  ${e.globalId}${rv ? '\nNeeds review' : ''}`, count: 1, ids: [e.id], elementId: e.id, children: [], review: rv ? 1 : 0,
          } satisfies TreeNode;
        });
    }
    const level = levels[depth]!;
    const groups = new Map<string, Group>();
    for (const e of list) {
      const v = levelValue(e, level, opts);
      const k = v ? v.code : NONE_CODE;
      let g = groups.get(k);
      if (!g) groups.set(k, (g = { value: v ? { ...v, review: false } : null, items: [] }));
      g.items.push(e);
    }
    const codes = [...groups.keys()].filter((k) => k !== NONE_CODE).sort(sorter(opts.order?.[level]));
    if (groups.has(NONE_CODE)) codes.push(NONE_CODE);
    return codes.map((k) => {
      const g = groups.get(k)!;
      const none = k === NONE_CODE;
      const key = `${parentKey}|${level}:${none ? '-' : k}`;
      const q = levelQuery(level, none ? null : k, opts.columns);
      // A level without a query (UniFormat) makes the whole branch queryless.
      const own = parentQuery === null || q === null ? null : [...parentQuery, q];
      const v = g.value;
      const label = none ? NOT_CLASSIFIED : v!.label === v!.code || level === 'Storey' || level === 'IfcClass' ? v!.code : `${v!.code} ${v!.label}`;
      const title = none ? `${NOT_CLASSIFIED}: no ${levelLabel(level)} value` : `${levelLabel(level)}: ${v!.code}${v!.label !== v!.code ? ` ${v!.label}` : ''}`;
      return nodeFrom('group', key, label, title, walk(g.items, depth + 1, key, own), own ? own.join(' and ') : null);
    });
  };
  return walk(infos, 0, 'cl', []);
}

/** Keys of the first-level nodes (the default expansion). */
export function topKeys(roots: readonly TreeNode[]): Set<string> {
  return new Set(roots.filter((r) => r.children.length > 0).map((r) => r.key));
}

/** The first-level nodes as a colour legend: one row per value of a facet (or the discipline), with its count and query. */
export interface LegendRow {
  code: string;
  label: string;
  count: number;
  review: number;
  ids: ElementId[];
  query: string | null;
}

export function legendRows(infos: readonly ClassInfo[], level: string, opts: Pick<BuildOptions, 'order' | 'columns'>): LegendRow[] {
  return buildClassTree(infos, { levels: [level], order: opts.order, columns: opts.columns }).map((n) => {
    const none = n.label === NOT_CLASSIFIED;
    const first = n.key.split(':').slice(1).join(':');
    const code = none ? '' : first;
    const label = none ? NOT_CLASSIFIED : n.label.startsWith(code + ' ') ? n.label.slice(code.length + 1) : n.label;
    return { code, label, count: n.count, review: n.review ?? 0, ids: n.ids, query: n.query ?? null };
  });
}
