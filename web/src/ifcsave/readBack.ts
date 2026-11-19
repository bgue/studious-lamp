// Read an additions block back from its text (design 1.7). Used by tests and by the import of a saved state.

import { parseStatement, scanStatements } from './stepText';
import type { StepValue } from './stepText';

export interface ReadCode {
  /** Name of the classification system. */
  system: string;
  code: string;
  label: string;
}
export interface ReadAdditions {
  header?: { base: number; lines: number; tool: string };
  /** Per element express id: its classification references, and every property as `<set name>.<property>`. */
  byExpressId: Map<number, { codes: ReadCode[]; review: Record<string, unknown> }>;
}

const sv = (v: StepValue | undefined): string => (v && v.t === 'str' ? v.v : '');
const refs = (v: StepValue | undefined): number[] => (v && v.t === 'list' ? v.v.filter((x): x is { t: 'ref'; id: number } => x.t === 'ref').map((x) => x.id) : []);
const refId = (v: StepValue | undefined): number => (v && v.t === 'ref' ? v.id : -1);

function nominal(v: StepValue | undefined): unknown {
  if (!v || v.t !== 'typed') return undefined;
  const a = v.args[0];
  if (!a) return undefined;
  if (a.t === 'str') return a.v;
  if (a.t === 'enum') return a.v === 'T' ? true : a.v === 'F' ? false : a.v;
  if (a.t === 'num') return Number(a.v);
  return undefined;
}

/**
 * @param external names of classifications that the block only references (reused from the original file), by express id.
 */
export function readAdditions(blockText: string, external: ReadonlyMap<number, string> = new Map()): ReadAdditions {
  const out: ReadAdditions = { byExpressId: new Map() };
  const h = /\/\* XRAY-BEGIN \S+ base=(\d+) lines=(\d+) tool=(\S+)(?: [^*]*?)? \*\//.exec(blockText);
  if (h) out.header = { base: Number(h[1]), lines: Number(h[2]), tool: h[3]! };
  const classes = new Map<number, string>(external);
  const references = new Map<number, { code: string; label: string; source: number }>();
  const assoc: Array<{ objects: number[]; ref: number }> = [];
  const singles = new Map<number, { name: string; value: unknown }>();
  const sets = new Map<number, { name: string; props: number[] }>();
  const defines: Array<{ objects: number[]; set: number }> = [];

  for (const s of scanStatements(blockText)) {
    const st = parseStatement(s.text);
    if (!st || st.id === undefined) continue;
    const a = st.args;
    switch (st.type) {
      case 'IFCCLASSIFICATION':
        classes.set(st.id, sv(a[3]));
        break;
      case 'IFCCLASSIFICATIONREFERENCE':
        references.set(st.id, { code: sv(a[1]), label: sv(a[2]), source: refId(a[3]) });
        break;
      case 'IFCRELASSOCIATESCLASSIFICATION':
        assoc.push({ objects: refs(a[4]), ref: refId(a[5]) });
        break;
      case 'IFCPROPERTYSINGLEVALUE':
        singles.set(st.id, { name: sv(a[0]), value: nominal(a[2]) });
        break;
      case 'IFCPROPERTYSET':
        sets.set(st.id, { name: sv(a[2]), props: refs(a[4]) });
        break;
      case 'IFCRELDEFINESBYPROPERTIES':
        defines.push({ objects: refs(a[4]), set: refId(a[5]) });
        break;
    }
  }
  const entry = (id: number): { codes: ReadCode[]; review: Record<string, unknown> } => {
    let e = out.byExpressId.get(id);
    if (!e) out.byExpressId.set(id, (e = { codes: [], review: {} }));
    return e;
  };
  const systemOf = (id: number): string => {
    for (let guard = 0; guard < 8; guard++) {
      const r = references.get(id);
      if (!r) return classes.get(id) ?? `#${id}`;
      id = r.source;
    }
    return `#${id}`;
  };
  for (const r of assoc) {
    const ref = references.get(r.ref);
    if (!ref) continue;
    const code: ReadCode = { system: systemOf(ref.source), code: ref.code, label: ref.label };
    for (const o of r.objects) entry(o).codes.push(code);
  }
  for (const d of defines) {
    const set = sets.get(d.set);
    if (!set) continue;
    for (const o of d.objects) {
      const e = entry(o);
      for (const p of set.props) {
        const sp = singles.get(p);
        if (sp) e.review[`${set.name}.${sp.name}`] = sp.value;
      }
    }
  }
  return out;
}
