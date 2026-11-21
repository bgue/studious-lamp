// Hand-built fixtures for the 4D linker / plan / report tests: a 3-storey building (31 elements), a 15-activity schedule with
// codes Level / Trade / Area, a WBS, milestones, an active task with actuals, and the config that maps them.
import { DEFAULT_STYLE } from '../src/schedule/types';
import type { FourDConfig, FourDStyle, Schedule, ScheduleTask, TaskType, TaskStatus } from '../src/schedule/types';
import type { FourDElement, FourDModel } from '../src/schedule/model';

export const STOREYS = [
  { name: 'Level 1', elevation: 0 },
  { name: 'Level 2', elevation: 4 },
  { name: 'Level 3', elevation: 8 },
];

function el(globalId: string, ifcClass: string, name: string, storey: string | undefined, x0: number, y0: number, z0: number, dx: number, dy: number, dz: number, extra: Partial<FourDElement> = {}): FourDElement {
  return { globalId, ifcClass, name, ...(storey ? { storey } : {}), props: {}, bbox: [x0, y0, z0, x0 + dx, y0 + dy, z0 + dz], ...extra };
}

/** 3 storeys x (slab, 2 columns, 2 walls, duct, door, window) = 24, plus 2 old walls (existing), 2 furniture, a roof, a stair and a proxy = 31. */
export function buildModel(): FourDModel {
  const elements: FourDElement[] = [];
  STOREYS.forEach((s, i) => {
    const n = i + 1;
    const z = s.elevation;
    elements.push(el(`SLAB${n}`, 'IfcSlab', `Slab L${n}`, s.name, 0, 0, z - 0.3, 20, 10, 0.3, { props: { 'Xray_4D.Trade': 'CONC' } }));
    elements.push(el(`COLA${n}`, 'IfcColumn', `Column A L${n}`, s.name, 0, 0, z, 0.4, 0.4, 4, { zone: 'Zone A', props: { 'Xray_4D.Trade': 'CONC' } }));
    elements.push(el(`COLB${n}`, 'IfcColumn', `Column B L${n}`, s.name, 18, 0, z, 0.4, 0.4, 4, { zone: 'Zone B', props: { 'Xray_4D.Trade': 'CONC' } }));
    elements.push(el(`WALLA${n}`, 'IfcWall', `Wall 1 L${n}`, s.name, 2, 0, z, 5, 0.2, 4, { zone: 'Zone A', props: { 'Xray_4D.Trade': 'MAS' } }));
    elements.push(el(`WALLB${n}`, 'IfcWall', `Wall 2 L${n}`, s.name, 12, 0, z, 5, 0.2, 4, { zone: 'Zone B', props: { 'Xray_4D.Trade': 'MAS' } }));
    // ducts and windows carry no trade: the config's tradeQueries find them
    elements.push(el(`DUCT${n}`, 'IfcDuctSegment', `Duct L${n}`, s.name, 5, 5, z + 3, 8, 0.5, 0.5));
    elements.push(el(`DOOR${n}`, 'IfcDoor', `Door L${n}`, s.name, 8, 0, z, 1, 0.1, 2.1));
    elements.push(el(`WIN${n}`, 'IfcWindow', `Window L${n}`, s.name, 15, 0, z + 1, 1.5, 0.1, 1.2));
  });
  // 24 so far
  elements.push(el('OLD1', 'IfcWall', 'Old wall 1', 'Level 1', 0, 10, 0, 5, 0.3, 4));
  elements.push(el('OLD2', 'IfcWall', 'Old wall 2', 'Level 1', 6, 10, 0, 5, 0.3, 4));
  elements.push(el('FURN1', 'IfcFurniture', 'Desk', 'Level 1', 3, 3, 0, 1.5, 0.8, 0.75));
  elements.push(el('FURN2', 'IfcFurniture', 'Desk', 'Level 1', 5, 3, 0, 1.5, 0.8, 0.75));
  elements.push(el('ROOF1', 'IfcRoof', 'Roof', 'Level 3', 0, 0, 12, 20, 10, 0.4, { props: { 'Xray_4D.Trade': 'ROOF' } }));
  elements.push(el('STAIR1', 'IfcStair', 'Stair', undefined, 16, 6, 0, 3, 1.2, 12));
  elements.push(el('PROXY1', 'IfcBuildingElementProxy', 'Proxy', 'Level 2', 1, 1, 4, 1, 1, 1));
  return { identityKey: 'fixture|31|abcd', name: 'fixture.ifc', elements, storeys: STOREYS };
}

export const CODES = (level: string, trade?: string, area?: string): Record<string, string> => ({ Level: level, ...(trade ? { Trade: trade } : {}), ...(area ? { Area: area } : {}) });

interface TaskSpec {
  type?: TaskType; status?: TaskStatus; codes?: Record<string, string>; wbs?: string[];
  early?: [string, string]; target?: [string, string]; actual?: [string, string?]; remaining?: [string, string];
  float?: number; driving?: boolean; udfs?: Record<string, string | number>; pct?: number;
}
export function task(code: string, name: string, s: TaskSpec = {}): ScheduleTask {
  const d: ScheduleTask['dates'] = {};
  if (s.early) { d.earlyStart = s.early[0]; d.earlyEnd = s.early[1]; }
  if (s.target) { d.targetStart = s.target[0]; d.targetEnd = s.target[1]; }
  if (s.actual) { d.actualStart = s.actual[0]; if (s.actual[1]) d.actualEnd = s.actual[1]; }
  if (s.remaining) { d.remainingStart = s.remaining[0]; d.remainingEnd = s.remaining[1]; }
  return {
    id: `id-${code}`, code, name, wbsId: s.wbs?.join('/') ?? 'root', wbsPath: s.wbs ?? ['P'], calendarId: 'cal1', type: s.type ?? 'task', status: s.status ?? 'notStarted',
    dates: d, totalFloatHours: s.float ?? 40, ...(s.driving ? { driving: true } : {}), ...(s.pct !== undefined ? { percentComplete: s.pct } : {}), codes: s.codes ?? {}, udfs: s.udfs ?? {},
  };
}

const T = (d: string, h = '08:00'): string => `${d}T${h}`;
const E = (a: string, b: string): [string, string] => [T(a), T(b, '17:00')];

export const DATA_DATE = '2027-01-20T08:00';

export function buildSchedule(): Schedule {
  const tasks: ScheduleTask[] = [
    task('A100', 'Start of works', { type: 'milestone', early: [T('2027-01-04'), T('2027-01-04')], wbs: ['P'], status: 'complete', actual: [T('2027-01-04'), T('2027-01-04')] }),
    task('A110', 'Mobilise', { wbs: ['P', 'GEN'], early: E('2027-01-04', '2027-01-04'), status: 'complete', actual: [T('2027-01-04'), T('2027-01-04', '17:00')] }),
    task('A200', 'L1 slab pour', { codes: CODES('L01', 'CONC'), wbs: ['P', 'STR', 'L1'], early: E('2027-01-04', '2027-01-08'), target: E('2027-01-04', '2027-01-08'), status: 'complete', actual: [T('2027-01-04'), T('2027-01-08', '17:00')], float: 0 }),
    task('A210', 'L1 columns zone A', { codes: CODES('L01', 'CONC', 'A'), wbs: ['P', 'STR', 'L1'], early: E('2027-01-11', '2027-01-15'), target: E('2027-01-11', '2027-01-15'), status: 'complete', actual: [T('2027-01-11'), T('2027-01-13', '17:00')], float: 0 }),
    task('A300', 'L2 slab', { codes: CODES('L02', 'CONC'), wbs: ['P', 'STR', 'L2'], early: E('2027-01-18', '2027-01-22'), target: E('2027-01-18', '2027-01-19'), status: 'active', actual: [T('2027-01-18')], remaining: [T('2027-01-20'), T('2027-01-25', '17:00')], pct: 60, float: 0, driving: true }),
    task('A310', 'L2 masonry', { codes: CODES('L02', 'MAS'), wbs: ['P', 'STR', 'L2'], early: E('2027-01-25', '2027-01-29'), target: E('2027-01-25', '2027-01-29'), float: 16 }),
    task('A320', 'L2 ductwork', { codes: CODES('L02', 'MEP'), wbs: ['P', 'MEP', 'L2'], early: E('2027-01-25', '2027-02-05'), target: E('2027-01-25', '2027-02-05'), float: 80 }),
    task('A400', 'L3 slab', { codes: CODES('L03', 'CONC'), wbs: ['P', 'STR', 'L3'], early: E('2027-02-01', '2027-02-05'), target: E('2027-02-01', '2027-02-05'), float: 0 }),
    task('A410', 'L3 masonry', { codes: CODES('L03', 'MAS'), wbs: ['P', 'STR', 'L3'], early: E('2027-02-08', '2027-02-12'), float: 8 }),
    task('A420', 'L3 ductwork', { codes: CODES('L03', 'MEP'), wbs: ['P', 'MEP', 'L3'], early: E('2027-02-08', '2027-02-19'), float: 80 }),
    task('A500', 'Install windows', { wbs: ['P', 'FAC'], early: E('2027-02-15', '2027-02-19'), float: 24 }),
    task('A600', 'Strip out old walls', { wbs: ['P', 'DEM'], early: E('2027-01-05', '2027-01-06'), status: 'complete', actual: [T('2027-01-05'), T('2027-01-06', '17:00')] }),
    task('A720', 'Level 2 door installation', { wbs: ['P', 'FIT', 'L2'], early: E('2027-02-08', '2027-02-10'), float: 120 }),
    task('A800', 'Site management', { type: 'loe', wbs: ['P', 'GEN'], early: E('2027-01-04', '2027-02-22') }),
    task('A900', 'Practical completion', { type: 'finishMilestone', early: [T('2027-02-22', '17:00'), T('2027-02-22', '17:00')], wbs: ['P'] }),
  ];
  const week: Array<Array<[number, number]>> = [[], [[8, 12], [13, 17]], [[8, 12], [13, 17]], [[8, 12], [13, 17]], [[8, 12], [13, 17]], [[8, 12], [13, 17]], []];
  return {
    schema: 'xray-schedule/1', sourceHash: 'deadbeefcafe0123', project: { id: 'p1', shortName: 'TOWER', dataDate: DATA_DATE, calendarId: 'cal1' },
    projects: [{ id: 'p1', shortName: 'TOWER' }],
    calendars: [{ id: 'cal1', name: 'Std', week, exceptions: { '2027-02-15': [] }, hoursPerDay: 8 }],
    wbs: [{ id: 'P', parentId: null, shortName: 'P', name: 'Project' }],
    tasks,
    relations: [
      { taskId: 'id-A110', predecessorId: 'id-A100', type: 'FS', lagHours: 0 },
      { taskId: 'id-A200', predecessorId: 'id-A110', type: 'FS', lagHours: 0 },
      { taskId: 'id-A210', predecessorId: 'id-A200', type: 'FS', lagHours: 0 },
      { taskId: 'id-A300', predecessorId: 'id-A210', type: 'FS', lagHours: 0 },
      { taskId: 'id-A310', predecessorId: 'id-A300', type: 'FS', lagHours: 0 },
      { taskId: 'id-A320', predecessorId: 'id-A300', type: 'FS', lagHours: 0 },
      { taskId: 'id-A400', predecessorId: 'id-A300', type: 'FS', lagHours: 0 },
      { taskId: 'id-A410', predecessorId: 'id-A400', type: 'FS', lagHours: 0 },
      { taskId: 'id-A420', predecessorId: 'id-A400', type: 'FS', lagHours: 0 },
      { taskId: 'id-A500', predecessorId: 'id-A410', type: 'FS', lagHours: 0 },
      { taskId: 'id-A900', predecessorId: 'id-A500', type: 'FS', lagHours: 0 },
      { taskId: 'id-A900', predecessorId: 'id-A420', type: 'FS', lagHours: 0 },
      { taskId: 'id-A600', predecessorId: 'id-A100', type: 'FS', lagHours: 0 },
      { taskId: 'id-A720', predecessorId: 'id-A310', type: 'FS', lagHours: 0 },
    ],
    codeTypes: { Level: ['L01', 'L02', 'L03'], Trade: ['CONC', 'MAS', 'MEP'], Area: ['A', 'B'] }, udfLabels: [], warnings: [],
  };
}

export function buildConfig(style: Partial<FourDStyle> = {}): FourDConfig {
  return {
    schema: 'xray-4d-config/1',
    schedule: { location: [{ code: 'Level' }], trade: [{ code: 'Trade' }], zone: [{ code: 'Area' }] },
    model: { location: [{ property: 'Xray_4D.Location' }, { storey: true }], trade: [{ property: 'Xray_4D.Trade' }], zone: [{ zone: true }], existing: "name LIKE 'Old wall%'" },
    values: { location: { '/^L0?(\\d+)$/': 'Level $1' }, zone: { A: 'Zone A', B: 'Zone B' } },
    tradeQueries: { MEP: "class IN ('IfcDuctSegment')" },
    activities: {
      A500: { query: "class = 'IfcWindow'" },
      A600: { query: "name LIKE 'Old wall%'", role: 'remove' },
    },
    split: { CONC: 'sweep_x', '*': 'none' },
    style: { ...DEFAULT_STYLE, ...style },
  };
}
