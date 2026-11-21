// 4D contracts: the parsed P6 schedule, the 4D configuration (how the schedule and the model describe location and trade, and
// the film style), the links between activities and elements, and the 4D plan the player evaluates. Design:
// docs/design/4d-xer-animation.md. Shared by the XER parser (src/schedule/xer.ts), the linker and plan builder
// (src/schedule/link.ts, plan.ts), the 4D mapping tool in the viewer, the score player (cue kind `schedule4d`) and the
// `xray-4d` CLI. Change ADDITIVELY only.
//
// Times: P6 dates carry no time zone. They are kept as ISO local strings ('2027-03-14T08:00') in the schedule, and as
// numbers in the plan: milliseconds of Date.UTC(y, m, d, h, min), i.e. the local wall time read as UTC (no DST jumps).

// ---------------------------------------------------------------- the parsed schedule

export type TaskType = 'task' | 'resource' | 'milestone' | 'finishMilestone' | 'loe' | 'wbsSummary' | 'other';
export type TaskStatus = 'notStarted' | 'active' | 'complete';
export type RelationType = 'FS' | 'SS' | 'FF' | 'SF';

export interface ScheduleCalendar {
  id: string;
  name: string;
  /** Working hours per weekday, 0 = Sunday .. 6 = Saturday: [[startHour, endHour], ...]; empty = not a working day. */
  week: Array<Array<[number, number]>>;
  /** Exceptions by ISO date ('2027-12-25'): the working hours of that day (empty = holiday). */
  exceptions: Record<string, Array<[number, number]>>;
  hoursPerDay?: number;
}

export interface ScheduleTask {
  /** P6 internal id (task_id). */
  id: string;
  /** Activity ID as people see it (task_code), the key used everywhere else. */
  code: string;
  name: string;
  wbsId: string;
  /** WBS short names from the root down to the task's WBS node. */
  wbsPath: string[];
  calendarId: string;
  type: TaskType;
  status: TaskStatus;
  dates: {
    targetStart?: string; targetEnd?: string;
    earlyStart?: string; earlyEnd?: string;
    lateStart?: string; lateEnd?: string;
    actualStart?: string; actualEnd?: string;
    remainingStart?: string; remainingEnd?: string;
  };
  totalFloatHours?: number;
  driving?: boolean;
  /** Physical % complete, 0..100. */
  percentComplete?: number;
  /** Activity code values by code type name: { Level: 'L03', Trade: 'CONC' } (short names). */
  codes: Record<string, string>;
  /** User-defined fields by label. */
  udfs: Record<string, string | number>;
}

export interface ScheduleWbs {
  id: string;
  parentId: string | null;
  shortName: string;
  name: string;
  seq?: number;
}

export interface ScheduleRelation {
  taskId: string;
  predecessorId: string;
  type: RelationType;
  lagHours: number;
}

export interface ScheduleProject {
  id: string;
  shortName: string;
  name?: string;
  /** The data date (last_recalc_date), ISO local. */
  dataDate?: string;
  /** Default calendar id. */
  calendarId?: string;
}

export interface Schedule {
  schema: 'xray-schedule/1';
  /** Content hash of the source file (hex), for traceability in reports and films. */
  sourceHash: string;
  project: ScheduleProject;
  /** Every project in the file (the parser picks `project` by option or the only one). */
  projects: ScheduleProject[];
  calendars: ScheduleCalendar[];
  wbs: ScheduleWbs[];
  tasks: ScheduleTask[];
  relations: ScheduleRelation[];
  /** Activity code types and their values: { Level: ['L00', 'L01', ...] } (for the mapping UI and `inspect`). */
  codeTypes: Record<string, string[]>;
  udfLabels: string[];
  warnings: string[];
}

// ---------------------------------------------------------------- the 4D configuration

/** Where a schedule attribute (location, trade, zone) comes from. Several sources: the first that gives a value wins. */
export type ScheduleAttrSource =
  | { code: string }                                 // activity code type name
  | { udf: string }                                  // user-defined field label
  | { wbsLevel: number }                             // WBS short name at this depth (0 = top under the project)
  | { wbsPattern: string; group?: number }           // regex over the joined WBS path ('A/L03/STR'), capture group
  | { namePattern: string; group?: number };         // regex over the activity name

/** Where the model holds an element's location or trade. Default: the `Xray_4D` property set the mapping tool writes. */
export type ModelAttrSource =
  | { property: string }                             // 'Xray_4D.Location', 'Pset_X.Area', ...
  | { storey: true }                                 // the IFC storey name (location only)
  | { zone: true }                                   // the IfcZone the element belongs to
  | { discipline: true };                            // the classifier's discipline (trade only)

export type SplitRule = 'none' | 'sweep_x' | 'sweep_minus_x' | 'sweep_y' | 'sweep_minus_y' | 'sweep_z' | 'sweep_minus_z' | 'by_storey' | 'by_name';

export interface FourDStyle {
  /** planned (early dates; or the baseline when given), actual (actuals to the data date, then remaining), variance. */
  view: 'planned' | 'actual' | 'variance';
  /** Elements whose activity has not started: hidden, or a faint ghost. */
  unbuilt: 'hidden' | 'ghost';
  /** The whole job, or a lookahead window from the data date (or a date) for N weeks (e.g. 6), with the past shown built. */
  window: { kind: 'all' } | { kind: 'lookahead'; from: 'dataDate' | string; weeks: number } | { kind: 'range'; from: string; to: string };
  /** Film length in seconds, or a fixed pace (schedule days per video second). One of the two. */
  length?: number;
  daysPerSecond?: number;
  /** fixed: linear working time; warp: busy weeks get more screen time (bounded). */
  pace: 'fixed' | 'warp';
  camera: 'director' | 'fixed' | 'none';
  explode: 'auto' | 'off';
  /** The active elements are the x-ray focus (occluders ghost). */
  xrayFocus: boolean;
  sectionBox: 'auto' | 'off';
  /** At most this many activity labels at once (0 = none). */
  labels: number;
  /** Activities with total float at or under this many hours count as critical (null: use only the driving path flag). */
  criticalFloatHours: number | null;
  /** Trade colours (#rrggbb) by trade value; missing ones come from a default palette. */
  colours: Record<string, string>;
  captions: boolean;
  /** Minimum hold at each milestone, seconds. */
  milestoneHold: number;
}

export const DEFAULT_STYLE: FourDStyle = {
  view: 'planned',
  unbuilt: 'hidden',
  window: { kind: 'all' },
  length: 120,
  pace: 'warp',
  camera: 'director',
  explode: 'auto',
  xrayFocus: true,
  sectionBox: 'auto',
  labels: 3,
  criticalFloatHours: 0,
  colours: {},
  captions: true,
  milestoneHold: 1.5,
};

export interface FourDConfig {
  schema: 'xray-4d-config/1';
  schedule: {
    /** Project short name, when the file holds several. */
    project?: string;
    location: ScheduleAttrSource[];
    trade: ScheduleAttrSource[];
    zone?: ScheduleAttrSource[];
  };
  model: {
    location: ModelAttrSource[];
    trade: ModelAttrSource[];
    zone?: ModelAttrSource[];
    /** Elements that exist before the job starts (criteria query). */
    existing?: string;
  };
  /** Schedule value -> model value (exact text, or a regex key written /.../ with $1 substitutions), per attribute. */
  values?: { location?: Record<string, string>; trade?: Record<string, string>; zone?: Record<string, string> };
  /** Trade value -> an element query used when the model has no trade attribute (criteria language). */
  tradeQueries?: Record<string, string>;
  /** Per-activity overrides by activity ID. */
  activities?: Record<string, { query?: string; globalIds?: string[]; split?: SplitRule; /** 'remove': the activity demolishes the elements it matches (default 'build'). Added by the linker. */ role?: 'build' | 'remove' }>;
  /** Split rule by trade value ('*' = default). */
  split?: Record<string, SplitRule>;
  style: FourDStyle;
}

// ---------------------------------------------------------------- links (the LinkML schema schema/linkml/xray_4d.yaml)
//
// links.json is a LinkML `LinkDataset` in its JSON form: slot names as keys (snake_case), references by key (an activity by its
// task_code, an element by its GlobalId). The same schema generates the SQL tables (schema/linkml/xray_4d.sql) used when
// assignments and links are made in a SQL / MCP environment. Keep these types and the schema in step (tests/fourd-links-schema).

export type LinkSource = 'native' | 'property' | 'attributes' | 'override' | 'suggested' | 'manual' | 'agent' | 'classifier';
export type ReviewStatus = 'proposed' | 'accepted' | 'rejected' | 'superseded';
export type AttributeKind = 'location' | 'trade' | 'zone';

export interface LinkModelRef { identity_key: string; name?: string; file_name?: string; file_hash?: string; ifc_schema?: 'IFC2X3' | 'IFC4' | 'IFC4X3' }
export interface LinkScheduleRef { source_hash: string; project: string; data_date?: string; file_name?: string }

export interface LinkActivity {
  task_code: string;
  name?: string;
  wbs_path?: string;
  activity_type?: TaskType;
  activity_status?: TaskStatus;
  start?: string;
  finish?: string;
  location?: string;
  trade?: string;
  zone?: string;
  critical?: boolean;
}

export interface LinkElement {
  global_id: string;
  ifc_class?: string;
  name?: string;
  storey?: string;
  location?: string;
  trade?: string;
  zone?: string;
  existing?: boolean;
}

/** One attribute value given to one element (the 4D mapping tool, rules, the classifier, SQL / MCP agents). */
export interface Assignment {
  id: string;
  element: string;                 // GlobalId
  attribute: AttributeKind;
  value: string;
  source?: LinkSource;
  confidence?: number;
  reasons?: string[];
  status?: ReviewStatus;
  reviewed_by?: string;            // personal data: never into share links or packed pages; into the IFC only by opt-in
  reviewed_at?: string;
  created_at?: string;
}

export interface ActivityLink {
  id: string;
  activity: string;                // task_code
  role: 'build' | 'remove';
  elements: string[];              // GlobalIds
  source?: LinkSource;
  /** 0..1; native, property, override and manual are 1. */
  confidence?: number;
  /** Human-readable evidence ('Level 3 from code Level=L03', 'IfcSlab from trade CONC'). */
  reasons?: string[];
  split?: SplitRule;
  rule?: string;
  status?: ReviewStatus;
  reviewed_by?: string;
  reviewed_at?: string;
  created_at?: string;
}

export interface LinkTie { element: string; candidates: string[] }

/** The LinkML tree root: one model, one schedule, and everything that links them. */
export interface FourDLinks {
  id: string;
  model: LinkModelRef;
  schedule: LinkScheduleRef;
  created_at?: string;
  tool?: string;
  activities?: LinkActivity[];
  model_elements?: LinkElement[];
  assignments?: Assignment[];
  links?: ActivityLink[];
  ties?: LinkTie[];
  unlinked_activities?: string[];  // task_codes
  unlinked_elements?: string[];    // GlobalIds
}

// ---------------------------------------------------------------- the 4D plan

export type ElementState = 'existing' | 'future' | 'active' | 'complete' | 'removed' | 'behind' | 'ahead';

export interface ElementTimeline {
  globalId: string;
  /** Sorted, non-overlapping; times in plan time (ms, local read as UTC). Before the first interval: `future` (or existing). */
  intervals: Array<{ from: number; to: number; state: ElementState; task: string }>;
}

export interface PlanTask {
  code: string;
  name: string;
  start: number;
  end: number;
  critical: boolean;
  milestone: boolean;
  location?: string;
  trade?: string;
  elements: number;
}

export interface FourDPlan {
  schema: 'xray-4d-plan/1';
  model: { identityKey: string; name: string };
  schedule: { project: string; dataDate?: string; sourceHash: string };
  style: FourDStyle;
  /** The plan's time window (ms). */
  window: { from: number; to: number };
  elements: ElementTimeline[];
  tasks: PlanTask[];
  milestones: Array<{ code: string; name: string; at: number }>;
  /** Plan time -> video seconds, piecewise linear, increasing: [[planMs, seconds], ...]. */
  timeMap: Array<[number, number]>;
  /** Progress curve for the HUD S-curve: fraction complete (0..1) planned and actual at sample times. */
  progress: Array<{ at: number; planned: number; actual?: number }>;
}
