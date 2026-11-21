// Read native IFC 4D back: IfcTask + IfcRelAssignsToProduct / IfcRelAssignsToProcess -> GlobalId -> task codes, the `native` option of
// linkSchedule (confidence 1). Pure text over the STEP file, works in node and in the viewer (on the retained source blob).
//   IfcRelAssignsToProduct   (RelatedObjects = tasks, RelatingProduct = element)      -> build (the element is the task's output)
//   IfcRelAssignsToProcess   (RelatedObjects = elements, RelatingProcess = task)      -> build, or remove on a DEMOLITION / DISMANTLE /
//                                                                                        REMOVAL / DISPOSAL task (some tools export a build this way)
// The task code is the IfcTask Identification, else its Name.

import { parseStatement } from './stepText';
import type { StepValue } from './stepText';

export interface NativeTasks {
  /** GlobalId -> task codes that build it. */
  native: Map<string, string[]>;
  /** GlobalId -> task codes that remove it (not used by the linker's `native` option; for a prior-links style import). */
  remove: Map<string, string[]>;
  tasks: number;
}

const REMOVE_TYPES = new Set(['DEMOLITION', 'DISMANTLE', 'REMOVAL', 'DISPOSAL']);
const sv = (v: StepValue | undefined): string => (v && v.t === 'str' ? v.v : '');
const refs = (v: StepValue | undefined): number[] => (v && v.t === 'list' ? v.v.filter((x): x is { t: 'ref'; id: number } => x.t === 'ref').map((x) => x.id) : []);
const ref1 = (v: StepValue | undefined): number => (v && v.t === 'ref' ? v.id : -1);

/** End of the statement that starts at `from` (index just after its `;`), honouring quoted strings. */
function statementEnd(text: string, from: number): number {
  let i = from;
  const n = text.length;
  while (i < n) {
    const c = text.charCodeAt(i);
    if (c === 0x27) {
      i++;
      while (i < n && text.charCodeAt(i) !== 0x27) i++;
      i++;
    } else if (c === 0x3b) return i + 1;
    else i++;
  }
  return n;
}

/**
 * @param text the IFC file as latin1 text (STEP is ASCII; non-ASCII is escaped)
 * @param globalIdOf express id -> GlobalId of the elements of the model (the reader's expressId and globalId)
 */
export function readNativeTasks(text: string, globalIdOf: ReadonlyMap<number, string>): NativeTasks {
  const re = /#(\d+)\s*=\s*(IFCTASK|IFCRELASSIGNSTOPRODUCT|IFCRELASSIGNSTOPROCESS)\s*\(/gi;
  const task = new Map<number, { code: string; remove: boolean }>();
  const rels: Array<{ kind: 'product' | 'process'; a: number[]; b: number }> = [];
  for (let m = re.exec(text); m; m = re.exec(text)) {
    const end = statementEnd(text, m.index);
    re.lastIndex = end;
    const st = parseStatement(text.slice(m.index, end));
    if (!st) continue;
    const type = st.type;
    const a = st.args;
    if (type === 'IFCTASK') {
      const code = sv(a[5]) || sv(a[2]);
      if (code) task.set(Number(m[1]), { code, remove: a[12]?.t === 'enum' && REMOVE_TYPES.has(String(a[12].v).toUpperCase()) });
    } else if (type === 'IFCRELASSIGNSTOPRODUCT') rels.push({ kind: 'product', a: refs(a[4]), b: ref1(a[6]) });
    else rels.push({ kind: 'process', a: refs(a[4]), b: ref1(a[6]) });
  }
  const out: NativeTasks = { native: new Map(), remove: new Map(), tasks: task.size };
  const add = (m: Map<string, string[]>, gid: string, code: string): void => {
    const l = m.get(gid);
    if (!l) m.set(gid, [code]);
    else if (!l.includes(code)) l.push(code);
  };
  for (const r of rels) {
    if (r.kind === 'product') {
      const gid = globalIdOf.get(r.b);
      if (gid === undefined) continue;
      for (const t of r.a) {
        const k = task.get(t);
        if (k) add(k.remove ? out.remove : out.native, gid, k.code);
      }
    } else {
      const k = task.get(r.b);
      if (!k) continue;
      for (const e of r.a) {
        const gid = globalIdOf.get(e);
        if (gid !== undefined) add(k.remove ? out.remove : out.native, gid, k.code);
      }
    }
  }
  return out;
}

/** Same, from file bytes. */
export const readNativeTasksFromBytes = (bytes: Uint8Array, globalIdOf: ReadonlyMap<number, string>): NativeTasks =>
  readNativeTasks(new TextDecoder('latin1').decode(bytes), globalIdOf);
