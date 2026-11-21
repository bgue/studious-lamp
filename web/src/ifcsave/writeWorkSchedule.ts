// Write the 4D work schedule into IFC bytes (node or browser): the original bytes stay, one XRAY block is appended (or replaced).
// An earlier block keeps its other lines (classification, Xray_Review, Xray_4D ...); only the XRAY-4D section is replaced, so a second
// write with the same input gives the same bytes.

import { DEFAULT_SCHEMA } from '../classify/defaultSchema';
import { emitAdditions } from './additions';
import { familyOf } from './families';
import type { FileSavePlan } from './plan';
import { locateInsert, splice } from './splice';
import { scanStep } from './stepScan';
import { WORK_BEGIN, workScheduleSupported } from './workSchedule';
import type { WorkScheduleSave } from './workSchedule';

export interface WorkScheduleWrite {
  bytes: Uint8Array;
  /** IFC schema as the file says. */
  schema: string;
  lines: number;
  /** An earlier XRAY block was replaced. */
  replaced: boolean;
}

/** `null` when the schema cannot hold the work schedule (IFC2X3 or unknown); `reason` says why. */
export function workScheduleSkipReason(schema: string): string | null {
  const f = familyOf(schema);
  if (!f) return `schema ${schema || '(none)'} is not supported for saving`;
  if (!workScheduleSupported(f)) return `${schema}: IfcTaskTime does not exist in IFC2X3, so the work schedule is not written (use IFC4 or IFC4X3)`;
  return null;
}

/** Express ids in the work schedule must be those of `bytes`. */
export async function writeWorkSchedule(bytes: Uint8Array, ws: WorkScheduleSave): Promise<WorkScheduleWrite> {
  const blob = new Blob([bytes as BlobPart]);
  const scan = await scanStep(blob);
  const skip = workScheduleSkipReason(scan.schema);
  if (skip) throw new Error(skip);
  const family = familyOf(scan.schema)!;
  const at = await locateInsert(blob);
  let base = scan.maxExpressId;
  let preserved: FileSavePlan['preserved'];
  if (at.oldBlock) {
    base = at.oldBlock.base;
    const old = new TextDecoder('latin1').decode(new Uint8Array(await blob.slice(at.oldBlock.begin, at.oldBlock.end).arrayBuffer()));
    const keep: string[] = [];
    let lastId = base;
    for (const line of old.split('\n')) {
      if (line.startsWith('/* XRAY-BEGIN') || line.startsWith('/* XRAY-END') || line.trim() === '') continue;
      if (line.startsWith(`/* ${WORK_BEGIN}`)) break;
      keep.push(line);
      const m = /^#(\d+)=/.exec(line);
      if (m) lastId = Math.max(lastId, Number(m[1]));
    }
    preserved = { lines: keep, lastId };
  }
  const plan: FileSavePlan = {
    fileName: 'model.ifc', family, base, ownerHistoryId: scan.ownerHistoryId, existingClassifications: [], elements: [], workSchedule: ws,
    ...(preserved ? { preserved } : {}),
  };
  const add = emitAdditions(plan, DEFAULT_SCHEMA, { includeReviewers: false, includeCleanupMarks: true, scope: 'all', toolVersion: 'cli' });
  const out = splice(blob, at, add.text);
  return { bytes: new Uint8Array(await out.arrayBuffer()), schema: scan.schema, lines: add.lines, replaced: !!at.oldBlock };
}
