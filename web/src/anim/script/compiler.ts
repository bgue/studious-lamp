// Compiler of the animation script language: the syntax tree to a Score (src/anim/score.ts). Pure: no DOM, no storage, no
// network, no eval. Runs in a few milliseconds, so the editor compiles on every key.
//
// Time. Statements run in order; a statement starts when the one before it has ended. What a statement lasts:
//   fly to, orbit            `over N seconds` (default 2 for fly, 3 for orbit)
//   set                      `over N seconds`, else instant
//   show, hide, isolate      `fading over N seconds`, else instant
//   mode, apply, select      instant
//   caption, label, hover    `for N seconds` (default 3, 3 and 2); the next statement waits for it
//   wait                     N seconds
//   together                 its statements start at the same moment; it lasts as long as the longest
//   repeat                   its body, again and again
// 4D: `schedule` plays a plan over its time and does not wait (the next statement starts with it); `at date` and `at milestone` put the
// statements after them at that moment of the running schedule (through the plan's time map), whether or not the statements before have
// ended. `explode`, `collapse`, `section box` and `tint` last their `over` / `fading` time (default 2, 2, 1.5, 0).
// Element references stay references (a query, a set name, GlobalIds) for the player to resolve; only `repeat for each element`
// needs the model, through the optional resolver.

import { scoreEnd, SCORE_SCHEMA } from '../score';
import type { Cue, Ease, ElementRef, Score } from '../score';
import type { Elements, Num, Program, Span, Stmt, Str, Value } from './ast';
import { ScriptError, didYouMean, nearest } from './diagnostics';
import type { ScriptDiagnostic } from './diagnostics';
import { COLOUR_NAMES, MODE_WORDS, STATEMENT_WORDS, parseScript } from './parser';
import { getPlan } from '../fourd/plans';
import { mapSpan, secondsAtPlan } from '../fourd/timeline';
import type { FourDPlan } from '../../schedule/types';

export interface Limits {
  /** One loop runs at most this many times. */
  maxIterations: number;
  /** Statements run in all (loops count every pass). */
  maxSteps: number;
  maxCues: number;
  /** Seconds. */
  maxDuration: number;
}

export const LIMITS: Readonly<Limits> = { maxIterations: 500, maxSteps: 20_000, maxCues: 5000, maxDuration: 3600 };

/** Default lengths in seconds. */
export const DEFAULT_SECONDS = { fly: 2, orbit: 3, caption: 3, label: 3, hover: 2, explode: 2, collapse: 2, section: 1.5 } as const;

/** The top-bar modes and the built-in preset each applies (mirrors MODES in src/ui/topBar.ts; a test keeps them in step). */
export const MODE_PRESETS: Readonly<Record<string, string>> = {
  solid: 'solid',
  ghost: 'coordination',
  radiograph: 'radiograph',
  glow: 'focus-glow',
  cutaway: 'peel-only',
};

/** Label fields that need no property set. */
export const LABEL_FIELDS = ['name', 'class', 'storey', 'material', 'globalid', 'type', 'activity', 'percent', 'finish'] as const;

const RESERVED = new Set<string>([...STATEMENT_WORDS, 'it', 'index', 'over', 'ease', 'margin', 'fading', 'for', 'with', 'about', 'to', 'into', 'times', 'where', 'class', 'everything', 'selection', 'true', 'false', 'on', 'off', 'yes', 'no', 'active', 'completed', 'critical', 'date', 'milestone', 'box', 'storey', 'storeys', 'radial', 'by', 'from', 'around']);

export interface CompileOptions {
  /** Element reference -> GlobalIds, for `repeat for each element`. Null: the reference cannot be resolved now. */
  resolve?(ref: ElementRef): string[] | null;
  /** Names of the stored selection sets: for `repeat for each set` and for checking `set "Name"`. */
  setNames?(): string[] | null;
  /** The known settings paths (params paths). Absent: not checked, with a warning. */
  paramPaths?: readonly string[] | null;
  /** The presets by id and name. Absent: not checked. */
  presets?: ReadonlyArray<{ id: string; name: string }> | null;
  /** The saved view names. Absent: not checked. */
  views?: readonly string[] | null;
  /** 4D plans by name, for `schedule` and `at`. Default: the registry of src/anim/fourd/plans.ts. */
  plans?(name: string): FourDPlan | null;
  /** Names of the known plans, for the hint on an unknown name. */
  planNames?(): readonly string[];
  /** The script name, stored in `score.source`. */
  name?: string;
  limits?: Partial<Limits>;
}

export interface CompileResult {
  /** Null when there is an error. */
  score: Score | null;
  errors: ScriptDiagnostic[];
  program: Program;
}

type Ctx = { kind: 'element'; gid: string } | { kind: 'set'; name: string } | null;

/** The running schedule: where its cue starts and how long it is, and the plan, for `at`. */
interface Running {
  t0: number;
  dur: number;
  plan: FourDPlan;
}

/** Plan time (ms, local read as UTC) of an ISO date `YYYY-MM-DD`, with an optional `THH:MM[:SS]` (or a space); null when it is not a real date. */
export function parsePlanDate(text: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(text.trim());
  if (!m) return null;
  const [y, mo, d, h, mi, se] = [m[1], m[2], m[3], m[4] ?? '0', m[5] ?? '0', m[6] ?? '0'].map(Number) as [number, number, number, number, number, number];
  const ms = Date.UTC(y, mo - 1, d, h, mi, se);
  const back = new Date(ms);
  if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d || h > 23 || mi > 59 || se > 59) return null;
  return ms;
}

class Abort extends Error {}

class Compiler {
  readonly cues: Cue[] = [];
  readonly diags: ScriptDiagnostic[] = [];
  private readonly seen = new Set<string>();
  private readonly env = new Map<string, number>();
  private ctx: Ctx = null;
  private running: Running | null = null;
  private steps = 0;
  private warnedParams = false;
  private readonly lim: Limits;

  constructor(
    private readonly opts: CompileOptions,
    private readonly sourceText: string,
  ) {
    this.lim = { ...LIMITS, ...opts.limits };
  }

  // ---- diagnostics

  private report(e: ScriptError, severity: 'error' | 'warning' = 'error'): void {
    const d = e.toDiagnostic(severity);
    const key = `${d.severity}|${d.line}|${d.col}|${d.message}`;
    if (this.seen.has(key)) return;
    this.seen.add(key);
    this.diags.push(d);
  }
  private warn(message: string, at: Span, hint?: string): void {
    this.report(new ScriptError(message, at.line, at.col, at.end, hint), 'warning');
  }
  private err(message: string, at: Span, hint?: string): ScriptError {
    return new ScriptError(message, at.line, at.col, at.end, hint);
  }

  // ---- numbers and text

  private num(n: Num): number {
    switch (n.k) {
      case 'num':
        return n.v;
      case 'var': {
        const key = n.name.toLowerCase();
        if (key === 'it') throw this.err('`it` is not a number.', n, this.ctx ? 'Use `it` as the elements of a statement, or in text.' : 'Use `it` only inside `repeat for each`.');
        const v = this.env.get(key);
        if (v === undefined) {
          const names = [...this.env.keys()];
          const dym = didYouMean(n.name, names);
          throw this.err(`I do not know the name \`${n.name}\`.`, n, dym || 'Give a number a name first: put 5 into pause.');
        }
        return v;
      }
      case 'neg':
        return -this.num(n.a);
      case 'bin': {
        const a = this.num(n.a);
        const b = this.num(n.b);
        let r: number;
        if (n.op === '+') r = a + b;
        else if (n.op === '-') r = a - b;
        else if (n.op === '*') r = a * b;
        else {
          if (b === 0) throw this.err('This divides by zero.', n.b);
          r = a / b;
        }
        if (!Number.isFinite(r)) throw this.err('This number is too large.', n);
        return r;
      }
    }
  }

  /** A length of time in seconds: not negative, not longer than the limit. */
  private secs(n: Num | undefined, fallback: number, what: string): number {
    if (!n) return fallback;
    const v = this.num(n);
    if (v < 0) throw this.err(`${what} cannot be negative (it is ${fmt(v)}).`, n);
    if (v > this.lim.maxDuration) throw this.err(`${what} is longer than the limit of ${this.lim.maxDuration} seconds.`, n);
    return v;
  }

  private text(s: Str): string {
    let out = '';
    for (const p of s.parts) {
      if (p.k === 'text') out += p.v;
      else if (p.k === 'num') out += fmt(this.num(p.n));
      else {
        const key = p.name.toLowerCase();
        if (key === 'it') {
          if (!this.ctx) throw this.err('`it` has no meaning here.', p.span, 'Use `it` inside `repeat for each`.');
          out += this.ctx.kind === 'set' ? this.ctx.name : this.ctx.gid;
        } else {
          const v = this.env.get(key);
          if (v === undefined) {
            const dym = didYouMean(p.name, [...this.env.keys()]);
            throw this.err(`I do not know the name \`${p.name}\`.`, p.span, dym || 'Write text in double quotes, like "Pumps".');
          }
          out += fmt(v);
        }
      }
    }
    return out;
  }

  // ---- elements

  private ref(e: Elements): ElementRef {
    switch (e.k) {
      case 'query':
        return { query: e.query };
      case 'set': {
        const names = this.opts.setNames?.();
        if (names && !names.includes(e.name)) {
          const near = nearest(e.name, names);
          this.warn(`There is no selection set named "${e.name}".`, e, near.length ? `Did you mean ${near.map((n) => `"${n}"`).join(' or ')}?` : names.length ? `The sets are ${names.slice(0, 6).map((n) => `"${n}"`).join(', ')}.` : 'This model has no stored sets.');
        }
        return { set: e.name };
      }
      case 'selection':
        return { selection: true };
      case 'everything':
        return { all: true };
      case 'gids':
        return { globalIds: [...e.ids] };
      case 'it':
        if (!this.ctx) throw this.err('`it` has no meaning here.', e, 'Use `it` inside `repeat for each`.');
        return this.ctx.kind === 'set' ? { set: this.ctx.name } : { globalIds: [this.ctx.gid] };
      case 'schedule':
        return { schedule: e.set };
    }
  }

  // ---- 4D helpers

  private plan(name: string, at: Span): FourDPlan {
    const found = (this.opts.plans ?? getPlan)(name);
    if (found) return found;
    const known = this.opts.planNames?.();
    const near = known ? nearest(name, known) : [];
    throw this.err(`There is no 4D plan named "${name}".`, at, near.length ? `Did you mean ${near.map((n) => `"${n}"`).join(' or ')}?` : known && known.length ? `The plans are ${known.slice(0, 6).map((n) => `"${n}"`).join(', ')}.` : 'Load the 4D plan first (the 4D tools of the viewer, or the plan file of xray-4d), then run the script again.');
  }

  /** Video second (script time) at which the running schedule reaches plan time `ms`. */
  private timeAtPlan(r: Running, ms: number): number {
    const span = mapSpan(r.plan);
    return span > 0 ? r.t0 + (secondsAtPlan(r.plan, ms) * r.dur) / span : r.t0;
  }

  private needSchedule(s: Span, what: string): Running {
    if (!this.running) throw this.err(`\`${what}\` needs a running schedule: there is no \`schedule\` statement before it.`, s, 'Start the plan first: schedule "Plan name" over 90 seconds.');
    return this.running;
  }

  private colour(c: { v: string } & Span): string {
    const t = c.v.trim().toLowerCase();
    if (/^#[0-9a-f]{6}$/.test(t)) return t;
    const named = COLOUR_NAMES[t];
    if (named) return named;
    throw this.err(`I do not know the colour "${c.v}".`, c, `${didYouMean(c.v, Object.keys(COLOUR_NAMES))} Write #rrggbb (like #e53935) or one of ${Object.keys(COLOUR_NAMES).join(', ')}.`.trim());
  }

  // ---- cues

  private emit(cue: Cue, at: Span): void {
    if (cue.at + cue.dur > this.lim.maxDuration) {
      this.report(this.err(`The script runs longer than ${this.lim.maxDuration / 3600 === 1 ? '1 hour' : `${this.lim.maxDuration} seconds`}.`, at, 'Shorten the waits and the lengths, or split the script.'));
      throw new Abort();
    }
    if (this.cues.length >= this.lim.maxCues) {
      this.report(this.err(`The script makes more than ${this.lim.maxCues} cues.`, at, 'Use fewer or smaller loops.'));
      throw new Abort();
    }
    cue.line = at.line;
    this.cues.push(cue);
  }

  // ---- statements

  /** Compile statements one after the other from time `t`; returns the time after the last. */
  seq(stmts: readonly Stmt[], t: number): number {
    for (const s of stmts) t = this.stmt(s, t);
    return t;
  }

  private stmt(s: Stmt, t: number): number {
    if (++this.steps > this.lim.maxSteps) {
      this.report(this.err(`The script runs more than ${this.lim.maxSteps} statements (loops count each pass).`, s, 'Use smaller loops.'));
      throw new Abort();
    }
    try {
      return this.stmt1(s, t);
    } catch (e) {
      if (e instanceof ScriptError) {
        this.report(e);
        return t;
      }
      throw e;
    }
  }

  private ease(e: Ease | undefined, fallback: Ease | undefined): Ease | undefined {
    return e ?? fallback;
  }

  private stmt1(s: Stmt, t: number): number {
    switch (s.kind) {
      case 'flyTo': {
        const dur = this.secs(s.over, DEFAULT_SECONDS.fly, 'The time');
        const frame = this.ref(s.target);
        let margin: number | undefined;
        if (s.margin) {
          margin = this.num(s.margin);
          if (margin < 1 || margin > 6) throw this.err(`The margin ${fmt(margin)} is outside 1 to 6.`, s.margin, 'The margin is how much room to leave around the elements: 1 is tight, 2.2 is the default.');
        }
        this.emit({ kind: 'camera', at: t, dur, ease: this.ease(s.ease, 'inOut'), to: { frame: frame, ...(margin !== undefined ? { margin } : {}) } }, s);
        return t + dur;
      }
      case 'flyView': {
        const dur = this.secs(s.over, DEFAULT_SECONDS.fly, 'The time');
        const views = this.opts.views;
        if (views && !views.includes(s.name)) {
          const near = nearest(s.name, views);
          this.warn(`There is no saved view named "${s.name}".`, s, near.length ? `Did you mean ${near.map((n) => `"${n}"`).join(' or ')}?` : views.length ? `The views are ${views.slice(0, 6).map((n) => `"${n}"`).join(', ')}.` : 'Save a view in the Views tab first.');
        }
        this.emit({ kind: 'camera', at: t, dur, ease: this.ease(s.ease, 'inOut'), to: { view: s.name } }, s);
        return t + dur;
      }
      case 'orbit': {
        const dur = this.secs(s.over, DEFAULT_SECONDS.orbit, 'The time');
        const deg = this.num(s.degrees);
        if (Math.abs(deg) > 36000) throw this.err(`${fmt(deg)} degrees is more than 100 turns.`, s.degrees);
        this.emit({ kind: 'camera', at: t, dur, ease: this.ease(s.ease, 'inOut'), to: { orbitDeg: deg, ...(s.about ? { about: this.ref(s.about) } : {}) } }, s);
        return t + dur;
      }
      case 'set': {
        const dur = this.secs(s.over, 0, 'The time');
        const path = this.checkPath(s.path, s.pathSpan);
        const to = this.value(s.value);
        const numeric = typeof to === 'number' || Array.isArray(to);
        const ease = this.ease(s.ease, dur > 0 && numeric ? 'inOut' : undefined);
        this.emit({ kind: 'param', at: t, dur, ...(ease ? { ease } : {}), path, to }, s);
        return t + dur;
      }
      case 'mode': {
        const m = s.mode.toLowerCase();
        const id = MODE_PRESETS[m];
        if (!id) throw this.err(`\`${s.mode}\` is not a mode.`, s.modeSpan, `${didYouMean(s.mode, MODE_WORDS)} The modes are ${MODE_WORDS.join(', ')}.`.trim());
        this.emit({ kind: 'preset', at: t, dur: 0, id }, s);
        return t;
      }
      case 'preset': {
        const list = this.opts.presets;
        let id = s.name;
        if (list) {
          const l = s.name.trim().toLowerCase();
          const hit = list.find((p) => p.id.toLowerCase() === l) ?? list.find((p) => p.name.toLowerCase() === l);
          if (!hit) {
            const near = nearest(s.name, list.flatMap((p) => [p.name]));
            throw this.err(`There is no preset "${s.name}".`, s.nameSpan, near.length ? `Did you mean ${near.map((n) => `"${n}"`).join(' or ')}?` : `The presets are ${list.slice(0, 8).map((p) => `"${p.name}"`).join(', ')}.`);
          }
          id = hit.id;
        }
        this.emit({ kind: 'preset', at: t, dur: 0, id }, s);
        return t;
      }
      case 'visibility': {
        const dur = this.secs(s.fading, 0, 'The fading time');
        const base = { kind: 'visibility' as const, at: t, dur };
        const all = s.target.k === 'everything';
        if (s.op === 'show') this.emit(all ? { ...base, showAll: true } : { ...base, show: this.ref(s.target) }, s);
        else if (s.op === 'hide') this.emit({ ...base, hide: this.ref(s.target) }, s);
        else this.emit(all ? { ...base, showAll: true } : { ...base, isolate: this.ref(s.target) }, s);
        return t + dur;
      }
      case 'select':
        this.emit({ kind: 'select', at: t, dur: 0, elements: s.target ? this.ref(s.target) : null }, s);
        return t;
      case 'caption': {
        const dur = this.secs(s.for, DEFAULT_SECONDS.caption, 'The time');
        const title = this.text(s.title);
        const text = s.text ? this.text(s.text) : undefined;
        this.emit({ kind: 'caption', at: t, dur, title, ...(text !== undefined ? { text } : {}) }, s);
        return t + dur;
      }
      case 'label': {
        const dur = this.secs(s.for, DEFAULT_SECONDS.label, 'The time');
        const fields = s.fields.map((f) => (LABEL_FIELDS.includes(f.toLowerCase() as never) ? f.toLowerCase() : f));
        for (const f of fields) {
          if (!f.includes('.') && !(LABEL_FIELDS as readonly string[]).includes(f)) {
            this.warn(`\`${f}\` is not a field I know.`, s, `${didYouMean(f, LABEL_FIELDS)} Fields: ${LABEL_FIELDS.join(', ')}, or a property in double quotes as "Pset_X.Prop".`.trim());
          }
        }
        this.emit({ kind: 'label', at: t, dur, elements: this.ref(s.target), fields }, s);
        return t + dur;
      }
      case 'hover': {
        const dur = this.secs(s.for, DEFAULT_SECONDS.hover, 'The time');
        this.emit({ kind: 'hover', at: t, dur, elements: this.ref(s.target) }, s);
        return t + dur;
      }
      case 'wait':
        return t + this.secs(s.seconds, 0, 'The wait');
      case 'put': {
        const key = s.name.toLowerCase();
        if (RESERVED.has(key)) throw this.err(`\`${s.name}\` is a word of the language and cannot be a name.`, s.nameSpan, 'Choose another name, like pause or gap.');
        this.env.set(key, this.num(s.value));
        return t;
      }
      case 'schedule': {
        const plan = this.plan(s.plan.v, s.plan);
        const span = mapSpan(plan);
        const dur = this.secs(s.over, span > 0 ? span : 1, 'The time');
        for (const d of [s.from, s.to]) if (d && parsePlanDate(d.v) === null) throw this.err(`"${d.v}" is not a date.`, d, 'Write dates as "YYYY-MM-DD", like "2027-03-01".');
        this.running = { t0: t, dur, plan };
        this.emit({ kind: 'schedule4d', at: t, dur, plan: { name: s.plan.v }, ...(s.view ? { view: s.view } : {}), ...(s.from ? { from: s.from.v } : {}), ...(s.to ? { to: s.to.v } : {}) }, s);
        return t; // the schedule runs in the background: the next statement starts with it
      }
      case 'at': {
        const r = this.needSchedule(s, `at ${s.what}`);
        let ms: number;
        if (s.what === 'date') {
          const p = parsePlanDate(s.value.v);
          if (p === null) throw this.err(`"${s.value.v}" is not a date.`, s.value, 'Write it as "YYYY-MM-DD", like "2027-03-01", or with a time, "2027-03-01T10:30".');
          ms = p;
          const { from: wFrom, to: wTo } = r.plan.window;
          if (ms < wFrom || ms > wTo) {
            const iso = (x: number): string => new Date(x).toISOString().slice(0, 10);
            this.warn(`The date ${s.value.v} is outside the plan (${iso(wFrom)} to ${iso(wTo)}); it counts as the nearest end.`, s.value);
          }
        } else {
          const names = r.plan.milestones.map((m) => m.name);
          const key = s.value.v.trim().toLowerCase();
          const hit = r.plan.milestones.find((m) => m.name === s.value.v) ?? r.plan.milestones.find((m) => m.name.toLowerCase() === key);
          if (!hit) {
            const near = nearest(s.value.v, names);
            throw this.err(`The plan has no milestone named "${s.value.v}".`, s.value, near.length ? `Did you mean ${near.map((n) => `"${n}"`).join(' or ')}?` : names.length ? `The milestones are ${names.slice(0, 6).map((n) => `"${n}"`).join(', ')}.` : 'This plan has no milestones.');
          }
          ms = hit.at;
        }
        return this.timeAtPlan(r, ms);
      }
      case 'tint': {
        const dur = this.secs(s.fading, 0, 'The fading time');
        const colour = s.colour ? this.colour(s.colour) : null;
        this.emit({ kind: 'tint', at: t, dur, ease: 'inOut', elements: this.ref(s.target), colour }, s);
        return t + dur;
      }
      case 'explode': {
        const dur = this.secs(s.over, DEFAULT_SECONDS.explode, 'The time');
        let factor: number | undefined;
        if (s.by) {
          factor = this.num(s.by);
          if (!(factor > 0) || factor > 10) throw this.err(`The explode factor ${fmt(factor)} is outside 0 to 10.`, s.by, 'By is how far the storeys move apart: 1 is the normal gap, 2 twice that.');
        }
        this.emit({ kind: 'explode', at: t, dur, ease: 'inOut', mode: s.mode, ...(factor !== undefined ? { factor } : {}) }, s);
        return t + dur;
      }
      case 'collapse': {
        const dur = this.secs(s.over, DEFAULT_SECONDS.collapse, 'The time');
        this.emit({ kind: 'collapse', at: t, dur, ease: 'inOut' }, s);
        return t + dur;
      }
      case 'focus':
        this.emit({ kind: 'focus', at: t, dur: 0, elements: s.target ? this.ref(s.target) : null }, s);
        return t;
      case 'section': {
        const dur = this.secs(s.over, DEFAULT_SECONDS.section, 'The time');
        const around = s.around === null ? null : 'storey' in s.around ? { storey: s.around.storey.v } : this.ref(s.around);
        this.emit({ kind: 'sectionBox', at: t, dur, ease: 'inOut', around }, s);
        return t + dur;
      }
      case 'together': {
        if (s.body.length === 0) this.warn('This `together` block is empty.', s);
        let end = t;
        for (const b of s.body) end = Math.max(end, this.stmt(b, t));
        return end;
      }
      case 'repeat': {
        const n = this.num(s.times);
        if (!Number.isInteger(n) || n < 0) throw this.err(`The repeat count must be a whole number of 0 or more (it is ${fmt(n)}).`, s.times);
        if (n > this.lim.maxIterations) throw this.err(`A loop can run at most ${this.lim.maxIterations} times (this one asks for ${n}).`, s.times, 'Use fewer repeats.');
        if (s.body.length === 0) this.warn('This `repeat` block is empty.', s);
        const saved = this.env.get('index');
        for (let i = 1; i <= n; i++) {
          this.env.set('index', i);
          t = this.seq(s.body, t);
        }
        this.restoreIndex(saved);
        return t;
      }
      case 'forEach':
        return this.forEach(s, t);
    }
  }

  private restoreIndex(saved: number | undefined): void {
    if (saved === undefined) this.env.delete('index');
    else this.env.set('index', saved);
  }

  private forEach(s: Extract<Stmt, { kind: 'forEach' }>, t: number): number {
    let items: Ctx[];
    if (s.each === 'set') {
      const names = this.opts.setNames?.();
      if (!names) throw this.err('`repeat for each set` needs the stored selection sets, which are not available here.', s, 'Open a model first.');
      items = names.map((name) => ({ kind: 'set' as const, name }));
    } else {
      const ref = this.ref(s.target!);
      const ids = this.opts.resolve?.(ref);
      if (!ids) throw this.err('`repeat for each element` needs the model to find the elements, and none is loaded.', s.target!, 'Open a model, then run the script again.');
      if (ids.length > this.lim.maxIterations) {
        throw this.err(`These elements number ${ids.length}; a loop can run at most ${this.lim.maxIterations} times.`, s.target!, 'Narrow the elements with `where`, for example by storey or by name.');
      }
      items = ids.map((gid) => ({ kind: 'element' as const, gid }));
    }
    if (s.each === 'set' && items.length > this.lim.maxIterations) {
      throw this.err(`There are ${items.length} selection sets; a loop can run at most ${this.lim.maxIterations} times.`, s.target ?? s, 'Delete sets you do not need, or loop over elements with `where` instead.');
    }
    if (items.length === 0) this.warn(s.each === 'set' ? 'There are no selection sets, so the loop does not run.' : 'No element matches, so the loop does not run.', s.target ?? s);
    const savedCtx = this.ctx;
    const savedIndex = this.env.get('index');
    try {
      items.forEach((it, i) => {
        this.ctx = it;
        this.env.set('index', i + 1);
        t = this.seq(s.body, t);
      });
    } finally {
      this.ctx = savedCtx;
      this.restoreIndex(savedIndex);
    }
    return t;
  }

  private value(v: Value): number | boolean | string | number[] {
    switch (v.k) {
      case 'bool':
        return v.v;
      case 'str':
        return v.v;
      case 'word': {
        const n = this.env.get(v.text.toLowerCase());
        return n !== undefined ? n : v.text;
      }
      case 'list': {
        const nums = v.items.map((n) => this.num(n));
        return nums.length === 1 ? nums[0]! : nums;
      }
    }
  }

  private checkPath(path: string, at: Span): string {
    const known = this.opts.paramPaths;
    if (!known || known.length === 0) {
      if (!this.warnedParams) {
        this.warnedParams = true;
        this.warn('The setting names cannot be checked now.', at, 'Open a model to check them. A wrong name is skipped when the script runs.');
      }
      return path;
    }
    if (known.includes(path)) return path;
    const lower = path.toLowerCase();
    const ci = known.find((k) => k.toLowerCase() === lower);
    if (ci) return ci;
    const children = known.filter((k) => k.toLowerCase().startsWith(`${lower}.`));
    // A warning, not an error: the list is what this build stores in its parameters document, and the player may know more.
    if (children.length > 0) {
      this.warn(`\`${path}\` is a group of settings, not one setting.`, at, `Settings in it: ${children.slice(0, 5).map((c) => `\`${c}\``).join(', ')}${children.length > 5 ? ', ...' : ''}.`);
      return path;
    }
    const near = nearest(path, known, 4);
    this.warn(`I do not know the setting \`${path}\`; the player skips it if it does not either.`, at, near.length ? `Nearest settings: ${near.map((n) => `\`${n}\``).join(', ')}.` : 'Settings are named as in the parameters document, like cinematic.glowStrength.');
    return path;
  }
}

/** Number as text for captions and messages: 2, 0.5, 1.25. */
export function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : String(Math.round(n * 1e6) / 1e6);
}

/** Compile a parsed program. Errors come back in the result; the score is null when there is one. */
export function compileProgram(program: Program, parseErrors: ScriptDiagnostic[], text: string, opts: CompileOptions = {}): CompileResult {
  // Syntax errors first: compiling a program with lines left out would only add errors that follow from them.
  if (parseErrors.some((e) => e.severity === 'error')) return { score: null, errors: parseErrors, program };
  const c = new Compiler(opts, text);
  let end = 0;
  try {
    end = c.seq(program.body, 0);
  } catch (e) {
    if (!(e instanceof Abort)) throw e;
  }
  const errors = [...parseErrors, ...c.diags].sort((a, b) => a.line - b.line || a.col - b.col);
  if (errors.some((e) => e.severity === 'error')) return { score: null, errors, program };
  const cues = c.cues.map((q, i) => ({ q, i })).sort((a, b) => a.q.at - b.q.at || a.i - b.i).map((x) => x.q);
  const score: Score = {
    schema: SCORE_SCHEMA,
    duration: Math.max(end, scoreEnd(cues)),
    cues,
    source: { kind: 'script', ...(opts.name ? { name: opts.name } : {}), text },
  };
  return { score, errors, program };
}

/** Parse and compile a script text. Never throws. */
export function compileScript(text: string, opts: CompileOptions = {}): CompileResult {
  const { program, errors } = parseScript(text);
  return compileProgram(program, errors, text, opts);
}
