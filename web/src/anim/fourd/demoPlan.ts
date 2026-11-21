// A demo 4D plan built from a loaded model, so the 4D cues can be shown without a schedule (tests, smoke checks, the first look):
// elements grouped by storey from the bottom up, a few trades by IFC class (structure, envelope, building services, fit-out), each
// trade of a storey one task whose elements appear one after the other along x (a sweep), one milestone per storey (the structure
// topped out) and a critical chain through the structure tasks. Deterministic: the same model gives the same plan.

import type { ElementTimeline, FourDPlan, PlanTask } from '../../schedule/types';
import { DEFAULT_STYLE } from '../../schedule/types';
import type { StoreyRecord } from '../../types';

const DAY = 86400000;

export interface DemoModel {
  name?: string;
  storeys: ReadonlyArray<Pick<StoreyRecord, 'id' | 'name' | 'elevation'>>;
  elements: ReadonlyArray<{ globalId: string; ifcClass: string; storey: number | null; bounds?: readonly number[] }>;
}

export interface DemoPlanOptions {
  /** Start date (ISO); default 2027-01-04. */
  start?: string;
  /** Film length the time map is built for, seconds (the cue scales it); default 30. */
  seconds?: number;
  /** Unbuilt elements: hidden (default) or a faint ghost. */
  unbuilt?: 'hidden' | 'ghost';
  /** Give the plan an actual progress curve up to a data date at 60 % of the window; default true. */
  actual?: boolean;
  /** Follow the x-ray focus on the active work; default true. */
  xrayFocus?: boolean;
}

export const DEMO_TRADES = ['Structure', 'Envelope', 'Services', 'Fit-out'] as const;
type Trade = (typeof DEMO_TRADES)[number];

/** The trade a demo task gives an IFC class. */
export function tradeOfClass(ifcClass: string): Trade {
  const c = ifcClass.toLowerCase();
  if (/slab|column|beam|footing|pile|member|stair|ramp|plate|reinforc/.test(c)) return 'Structure';
  if (/wall|curtain|roof|window|door|opening/.test(c)) return 'Envelope';
  if (/pipe|duct|flow|distribution|pump|fan|boiler|chiller|tank|valve|cable|light|sanitary|electric|energy|unitary|fire/.test(c)) return 'Services';
  return 'Fit-out';
}

// start offset and length of each trade within a storey (days); the next storey starts STRIDE days after this one
const TRADE_SPAN: Record<Trade, [number, number]> = { Structure: [0, 7], Envelope: [4, 8], Services: [8, 8], 'Fit-out': [13, 8] };
const STRIDE = 7;

export function buildDemoPlan(model: DemoModel, opts: DemoPlanOptions = {}): FourDPlan {
  const startMs = parseStart(opts.start ?? '2027-01-04');
  const seconds = opts.seconds ?? 30;
  const storeys = [...model.storeys].sort((a, b) => a.elevation - b.elevation || a.id - b.id);
  const rank = new Map<number, number>(storeys.map((s, i) => [s.id, i]));
  const nStoreys = Math.max(1, storeys.length);

  // group: storey rank -> trade -> element indices
  const groups = new Map<string, number[]>();
  const rankOf = (e: DemoModel['elements'][number]): number => {
    if (e.storey !== null && rank.has(e.storey)) return rank.get(e.storey)!;
    // no storey: by the height of the bounds centre against the storey elevations
    if (e.bounds && storeys.length > 0) {
      const cy = (e.bounds[1]! + e.bounds[4]!) / 2;
      let r = 0;
      for (let i = 0; i < storeys.length; i++) if (storeys[i]!.elevation <= cy + 0.5) r = i;
      return r;
    }
    return 0;
  };
  model.elements.forEach((e, i) => {
    const key = `${rankOf(e)}|${tradeOfClass(e.ifcClass)}`;
    let g = groups.get(key);
    if (!g) groups.set(key, (g = []));
    g.push(i);
  });

  const elements: ElementTimeline[] = model.elements.map((e) => ({ globalId: e.globalId, intervals: [] }));
  const tasks: PlanTask[] = [];
  const milestones: FourDPlan['milestones'] = [];
  const completions: number[] = []; // end time of each element, for the progress curve
  const windowFrom = startMs - 2 * DAY; // a lead-in: the first frame shows the site before any work
  const windowTo = startMs + ((nStoreys - 1) * STRIDE + 13 + 8 + 2) * DAY;

  for (let r = 0; r < nStoreys; r++) {
    const storeyName = storeys[r]?.name ?? 'Level';
    for (const trade of DEMO_TRADES) {
      const ids = groups.get(`${r}|${trade}`);
      if (!ids || ids.length === 0) continue;
      const [off, len] = TRADE_SPAN[trade];
      const t0 = startMs + (r * STRIDE + off) * DAY;
      const t1 = t0 + len * DAY;
      // a sweep along x: the element slots follow the order of their x position
      const order = [...ids].sort((a, b) => cx(model.elements[a]!) - cx(model.elements[b]!) || a - b);
      const n = order.length;
      const active = Math.max(DAY, Math.min(len * DAY * 0.3, len * DAY));
      order.forEach((ei, k) => {
        const from = t0 + (n > 1 ? (k / (n - 1)) * (len * DAY - active) : 0);
        const to = from + active;
        const code = `${storeyName}-${trade}`;
        elements[ei]!.intervals.push({ from, to, state: 'active', task: code }, { from: to, to: windowTo, state: 'complete', task: code });
        completions.push(to);
      });
      tasks.push({ code: `${storeyName}-${trade}`, name: `${storeyName} ${trade.toLowerCase()}`, start: t0, end: t1, critical: trade === 'Structure', milestone: false, location: storeyName, trade, elements: n });
    }
    const sEnd = startMs + (r * STRIDE + TRADE_SPAN.Structure[0] + TRADE_SPAN.Structure[1]) * DAY;
    milestones.push({ code: `M${r + 1}`, name: `${storeyName} structure complete`, at: sEnd });
  }
  milestones.push({ code: 'MEND', name: 'Handover', at: windowTo - DAY });

  // time map: even pace over the window with a short hold at every milestone
  const hold = 0.04 * seconds;
  const spanS = Math.max(1, seconds - hold * milestones.length);
  const timeMap: Array<[number, number]> = [[windowFrom, 0]];
  let s = 0;
  let prev = windowFrom;
  for (const m of [...milestones].sort((a, b) => a.at - b.at)) {
    s += ((m.at - prev) / (windowTo - windowFrom)) * spanS;
    timeMap.push([m.at, s]);
    s += hold;
    timeMap.push([m.at, s]);
    prev = m.at;
  }
  s += ((windowTo - prev) / (windowTo - windowFrom)) * spanS;
  timeMap.push([windowTo, s]);

  // progress curve: fraction of elements complete, daily samples; actual runs slightly behind up to the data date
  completions.sort((a, b) => a - b);
  const total = Math.max(1, completions.length);
  const days = Math.round((windowTo - windowFrom) / DAY);
  const dataDay = Math.round(days * 0.6);
  const progress: FourDPlan['progress'] = [];
  let ci = 0;
  for (let d = 0; d <= days; d++) {
    const at = windowFrom + d * DAY;
    while (ci < completions.length && completions[ci]! <= at) ci++;
    const planned = ci / total;
    progress.push({ at, planned, ...(opts.actual !== false && d <= dataDay ? { actual: planned * 0.94 } : {}) });
  }

  return {
    schema: 'xray-4d-plan/1',
    model: { identityKey: 'demo', name: model.name ?? 'demo' },
    schedule: { project: 'DEMO', ...(opts.actual !== false ? { dataDate: isoOf(windowFrom + dataDay * DAY) } : {}), sourceHash: 'demo' },
    style: { ...DEFAULT_STYLE, unbuilt: opts.unbuilt ?? 'hidden', length: seconds, pace: 'fixed', xrayFocus: opts.xrayFocus !== false, milestoneHold: 1 },
    window: { from: windowFrom, to: windowTo },
    elements,
    tasks,
    milestones,
    timeMap,
    progress,
  };
}

function cx(e: DemoModel['elements'][number]): number {
  return e.bounds ? (e.bounds[0]! + e.bounds[3]!) / 2 : 0;
}

function parseStart(s: string): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return m ? Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : Date.UTC(2027, 0, 4);
}

function isoOf(ms: number): string {
  const d = new Date(ms);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
}
