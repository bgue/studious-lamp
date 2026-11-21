// IFC 4D write-back: an IfcWorkSchedule with one IfcTask per linked activity, written into the same append-only XRAY block as the
// property sets (docs/design/4d-xer-animation.md section 10, docs-features/xray-4d.md). Pure text, deterministic: same input, same bytes.
//
//   IfcWorkSchedule      the schedule (project short name, data date as creation date, first start to last finish)
//   IfcTask              one per linked activity and role: Identification = task code, Name, IsMilestone,
//                        PredefinedType CONSTRUCTION (role build) or DEMOLITION (role remove), TaskTime
//   IfcTaskTime          ScheduleStart / ScheduleFinish (the plan's view dates), ActualStart / ActualFinish when present, IsCritical
//   IfcRelAssignsToControl   work schedule -> its tasks
//   IfcRelAssignsToProduct   role build: the element is an OUTPUT of the task (RelatingProduct = element, RelatedObjects = [its tasks]),
//                        one relation per element (the ifcopenshell `sequence.assign_product` mapping)
//   IfcRelAssignsToProcess   role remove: the element is an INPUT of the demolition task (RelatingProcess = task, RelatedObjects = elements)
//   IfcRelSequence (+ IfcLagTime)   a predecessor relation between two written tasks: FS, SS, FF, SF and its lag
//
// IFC4 and IFC4X3 only. IFC2X3 has no IfcTaskTime (it uses IfcScheduleTimeControl + IfcRelAssignsTasks); the 2X3 form is NOT
// written: `workScheduleSupported('2x3')` is false and the caller skips the file with a warning (decision documented in the feature doc).

import type { FourDLinks, FourDPlan, Schedule } from '../schedule/types';
import type { FourDModel } from '../schedule/model';
import { isMilestone, parseLocal, plannedSpan } from '../schedule/planTime';
import { xrayGuid } from './ifcGuid';
import { LIST, NULLTXT, REF, cutChars, entityLine, stepString } from './stepText';
import type { SchemaFamily } from './families';

export type TaskRole = 'build' | 'remove';

export interface WorkTaskSave {
  /** Unique key inside the schedule: `<code>|<role>`. */
  key: string;
  /** Activity ID (task_code): the IfcTask Identification. */
  code: string;
  name: string;
  milestone: boolean;
  predefined: 'CONSTRUCTION' | 'DEMOLITION';
  /** IfcDateTime texts, 'YYYY-MM-DDTHH:MM:SS' (local time, no zone). */
  scheduleStart?: string;
  scheduleFinish?: string;
  actualStart?: string;
  actualFinish?: string;
  critical?: boolean;
  /** Express ids of the linked elements in the file being written. */
  elements: number[];
}

export interface WorkSequenceSave {
  /** Task keys. */
  predecessor: string;
  successor: string;
  type: 'FS' | 'SS' | 'FF' | 'SF';
  lagHours: number;
}

export interface WorkScheduleSave {
  /** Name of the IfcWorkSchedule: always 'Xray 4D'. */
  name: string;
  /** The project short name (Description of the schedule; part of the GlobalId keys). */
  project: string;
  /** Written as Identification: the schedule file hash prefix, so a viewer knows which XER it came from. */
  identification?: string;
  /** IfcDateTime: the data date when there is one, else the first start. */
  created: string;
  start: string;
  finish: string;
  /** PLANNED (planned view) or ACTUAL (actual view). */
  kind: 'PLANNED' | 'ACTUAL';
  tasks: WorkTaskSave[];
  sequences: WorkSequenceSave[];
}

export const workScheduleSupported = (f: SchemaFamily): boolean => f !== '2x3';

export const WORK_BEGIN = 'XRAY-4D-BEGIN';
export const WORK_END = 'XRAY-4D-END';

const SEQ_ENUM: Record<WorkSequenceSave['type'], string> = { FS: '.FINISH_START.', SS: '.START_START.', FF: '.FINISH_FINISH.', SF: '.START_FINISH.' };
const label = (s: string): string => stepString(cutChars(s, 255));
const opt = (s: string | undefined): string => (s ? stepString(s) : NULLTXT);

/** ISO 8601 duration of lag hours: 16 -> PT16H, 7.5 -> PT7.5H, -8 -> -PT8H. */
export function isoDurationHours(h: number): string {
  const v = Math.abs(h);
  const body = `PT${Number.isInteger(v) ? v : Number(v.toFixed(4))}H`;
  return h < 0 ? `-${body}` : body;
}

/** 'YYYY-MM-DDTHH:MM:SS' of a plan time (ms, local read as UTC). */
export function ifcDateTime(ms: number): string {
  return new Date(ms).toISOString().slice(0, 19);
}

/**
 * The entity lines of the work schedule, ids from `first`. Returns the lines (the two XRAY-4D comments included) and the last id used.
 * IFC4 / IFC4X3 attribute lists. `owner` is always `$` in these families.
 */
export function emitWorkSchedule(ws: WorkScheduleSave, first: number): { lines: string[]; lastId: number } {
  let next = first - 1;
  const alloc = (): number => ++next;
  const lines: string[] = [`/* ${WORK_BEGIN} tasks=${ws.tasks.length} sequences=${ws.sequences.length} */`];
  const taskTimeId = new Map<string, number>();
  for (const t of ws.tasks) {
    const id = alloc();
    taskTimeId.set(t.key, id);
    // IfcTaskTime: Name, DataOrigin, UserDefinedDataOrigin, DurationType, ScheduleDuration, ScheduleStart, ScheduleFinish, EarlyStart,
    // EarlyFinish, LateStart, LateFinish, FreeFloat, TotalFloat, IsCritical, StatusTime, ActualDuration, ActualStart, ActualFinish,
    // RemainingTime, Completion
    lines.push(entityLine(id, 'IFCTASKTIME', [
      NULLTXT, NULLTXT, NULLTXT, NULLTXT, NULLTXT, opt(t.scheduleStart), opt(t.scheduleFinish), NULLTXT, NULLTXT, NULLTXT, NULLTXT, NULLTXT, NULLTXT,
      t.critical === undefined ? NULLTXT : t.critical ? '.T.' : '.F.', NULLTXT, NULLTXT, opt(t.actualStart), opt(t.actualFinish), NULLTXT, NULLTXT,
    ]));
  }
  const taskId = new Map<string, number>();
  for (const t of ws.tasks) {
    const id = alloc();
    taskId.set(t.key, id);
    // IfcTask: GlobalId, OwnerHistory, Name, Description, ObjectType, Identification, LongDescription, Status, WorkMethod, IsMilestone,
    // Priority, TaskTime, PredefinedType
    lines.push(entityLine(id, 'IFCTASK', [
      stepString(xrayGuid('task', `${ws.project}|${t.key}`)), NULLTXT, label(t.name || t.code), NULLTXT, NULLTXT, label(t.code), NULLTXT, NULLTXT, NULLTXT,
      t.milestone ? '.T.' : '.F.', NULLTXT, REF(taskTimeId.get(t.key)!), `.${t.predefined}.`,
    ]));
  }
  // IfcWorkSchedule: GlobalId, OwnerHistory, Name, Description, ObjectType, Identification, CreationDate, Creators, Purpose, Duration,
  // TotalFloat, StartTime, FinishTime, PredefinedType
  const wsId = alloc();
  lines.push(entityLine(wsId, 'IFCWORKSCHEDULE', [
    stepString(xrayGuid('workschedule', ws.project)), NULLTXT, label(ws.name), label(ws.project), NULLTXT, opt(ws.identification), stepString(ws.created), NULLTXT, NULLTXT, NULLTXT,
    NULLTXT, stepString(ws.start), stepString(ws.finish), `.${ws.kind}.`,
  ]));
  if (ws.tasks.length) {
    // IfcRelAssignsToControl: GlobalId, OwnerHistory, Name, Description, RelatedObjects, RelatedObjectsType, RelatingControl
    lines.push(entityLine(alloc(), 'IFCRELASSIGNSTOCONTROL', [
      stepString(xrayGuid('relctl', ws.project)), NULLTXT, label('Xray 4D tasks'), NULLTXT, LIST(ws.tasks.map((t) => REF(taskId.get(t.key)!))), NULLTXT, REF(wsId),
    ]));
  }
  // role build: one IfcRelAssignsToProduct per element (RelatingProduct), its tasks as RelatedObjects
  // IfcRelAssignsToProduct: GlobalId, OwnerHistory, Name, Description, RelatedObjects, RelatedObjectsType, RelatingProduct
  const outputs = new Map<number, number[]>();
  for (const t of ws.tasks) {
    if (t.predefined !== 'CONSTRUCTION') continue;
    for (const e of new Set(t.elements)) {
      if (!outputs.has(e)) outputs.set(e, []);
      outputs.get(e)!.push(taskId.get(t.key)!);
    }
  }
  for (const e of [...outputs.keys()].sort((a, b) => a - b)) {
    lines.push(entityLine(alloc(), 'IFCRELASSIGNSTOPRODUCT', [
      stepString(xrayGuid('relprod', `${ws.project}|${e}`)), NULLTXT, label('Xray 4D output'), NULLTXT, LIST(outputs.get(e)!.map(REF)), NULLTXT, REF(e),
    ]));
  }
  // role remove: IfcRelAssignsToProcess (RelatingProcess = task, RelatedObjects = elements)
  for (const t of ws.tasks) {
    if (t.predefined !== 'DEMOLITION' || !t.elements.length) continue;
    const els = [...new Set(t.elements)].sort((a, b) => a - b);
    lines.push(entityLine(alloc(), 'IFCRELASSIGNSTOPROCESS', [
      stepString(xrayGuid('relproc', `${ws.project}|${t.key}`)), NULLTXT, label('Xray 4D input'), NULLTXT, LIST(els.map(REF)), NULLTXT, REF(taskId.get(t.key)!), NULLTXT,
    ]));
  }
  for (const s of ws.sequences) {
    const a = taskId.get(s.predecessor);
    const b = taskId.get(s.successor);
    if (a === undefined || b === undefined) continue;
    let lag = NULLTXT;
    if (s.lagHours !== 0) {
      // IfcLagTime: Name, DataOrigin, UserDefinedDataOrigin, LagValue, DurationType
      const lid = alloc();
      lines.push(entityLine(lid, 'IFCLAGTIME', [NULLTXT, NULLTXT, NULLTXT, `IFCDURATION(${stepString(isoDurationHours(s.lagHours))})`, '.WORKTIME.']));
      lag = REF(lid);
    }
    // IfcRelSequence: GlobalId, OwnerHistory, Name, Description, RelatingProcess, RelatedProcess, TimeLag, SequenceType, UserDefinedSequenceType
    lines.push(entityLine(alloc(), 'IFCRELSEQUENCE', [
      stepString(xrayGuid('relseq', `${ws.project}|${s.predecessor}|${s.successor}|${s.type}`)), NULLTXT, label('Xray 4D sequence'), NULLTXT, REF(a), REF(b), lag, SEQ_ENUM[s.type], NULLTXT,
    ]));
  }
  lines.push(`/* ${WORK_END} */`);
  return { lines, lastId: next };
}

// ---------------------------------------------------------------- building the save input

export interface WorkScheduleInput {
  schedule: Schedule;
  links: FourDLinks;
  /** Elements of the IFC being written with their express ids (the node reader's sidecar elements have `expressId`). */
  expressIds: ReadonlyMap<string, number>;
  /** The plan: its tasks' view dates are the ScheduleStart / ScheduleFinish. Without a plan the planned (early) dates are used. */
  plan?: FourDPlan;
  /** For the `kind` when there is no plan. */
  view?: 'planned' | 'actual' | 'variance';
}

/** The WorkScheduleSave of accepted links. Activities with no linked element of the file are left out (an empty task has nothing to assign). */
export function buildWorkSchedule(inp: WorkScheduleInput): { save: WorkScheduleSave | null; warnings: string[] } {
  const { schedule, links, expressIds } = inp;
  const warnings: string[] = [];
  const taskByCode = new Map(schedule.tasks.map((t) => [t.code, t]));
  const planTask = new Map((inp.plan?.tasks ?? []).map((t) => [t.code, t]));
  const critical = (code: string): boolean | undefined => (planTask.has(code) ? planTask.get(code)!.critical : undefined);
  const byKey = new Map<string, WorkTaskSave>();
  let missing = 0;
  for (const l of links.links ?? []) {
    if (l.status !== 'accepted') continue;
    const t = taskByCode.get(l.activity);
    if (!t) continue;
    const key = `${l.activity}|${l.role}`;
    let task = byKey.get(key);
    if (!task) {
      const pt = planTask.get(t.code);
      const span = pt ? { start: pt.start, end: pt.end } : plannedSpan(t);
      const as = parseLocal(t.dates.actualStart);
      const ae = parseLocal(t.dates.actualEnd);
      task = {
        key, code: t.code, name: t.name, milestone: isMilestone(t), predefined: l.role === 'remove' ? 'DEMOLITION' : 'CONSTRUCTION',
        ...(span ? { scheduleStart: ifcDateTime(span.start), scheduleFinish: ifcDateTime(span.end) } : {}),
        ...(as !== undefined ? { actualStart: ifcDateTime(as) } : {}),
        ...(ae !== undefined ? { actualFinish: ifcDateTime(ae) } : {}),
        ...(critical(t.code) !== undefined ? { critical: critical(t.code)! } : {}),
        elements: [],
      };
      byKey.set(key, task);
    }
    for (const g of l.elements) {
      const id = expressIds.get(g);
      if (id === undefined) missing++;
      else task.elements.push(id);
    }
  }
  if (missing) warnings.push(`${missing} linked element${missing > 1 ? 's' : ''} have no express id in the IFC file and are not assigned`);
  const tasks = [...byKey.values()].filter((t) => t.elements.length > 0).sort((a, b) => (a.code < b.code ? -1 : a.code > b.code ? 1 : a.predefined < b.predefined ? -1 : a.predefined > b.predefined ? 1 : 0));
  if (tasks.length === 0) return { save: null, warnings };
  // the sequence between two written tasks (build tasks first when an activity has both roles)
  const keyOfCode = new Map<string, string>();
  for (const t of tasks) if (!keyOfCode.has(t.code) || t.predefined === 'CONSTRUCTION') keyOfCode.set(t.code, t.key);
  const idOf = new Map(schedule.tasks.map((t) => [t.id, t.code]));
  const sequences: WorkSequenceSave[] = [];
  for (const r of schedule.relations) {
    const succ = keyOfCode.get(idOf.get(r.taskId) ?? '');
    const pred = keyOfCode.get(idOf.get(r.predecessorId) ?? '');
    if (succ && pred && succ !== pred) sequences.push({ predecessor: pred, successor: succ, type: r.type, lagHours: r.lagHours ?? 0 });
  }
  sequences.sort((a, b) => (a.predecessor + a.successor + a.type).localeCompare(b.predecessor + b.successor + b.type));
  const starts = tasks.map((t) => t.scheduleStart).filter((x): x is string => !!x).sort();
  const finishes = tasks.map((t) => t.scheduleFinish).filter((x): x is string => !!x).sort();
  const dd = parseLocal(schedule.project.dataDate);
  const first = starts[0] ?? (dd !== undefined ? ifcDateTime(dd) : ifcDateTime(0));
  const view = inp.plan?.style.view ?? inp.view ?? 'planned';
  return {
    save: {
      name: 'Xray 4D',
      project: schedule.project.shortName,
      identification: schedule.sourceHash.slice(0, 16),
      created: dd !== undefined ? ifcDateTime(dd) : first,
      start: first,
      finish: finishes[finishes.length - 1] ?? first,
      kind: view === 'actual' ? 'ACTUAL' : 'PLANNED',
      tasks,
      sequences,
    },
    warnings,
  };
}
