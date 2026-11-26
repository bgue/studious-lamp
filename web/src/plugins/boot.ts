// Boot plugin: applies window.__xrayBoot (written into the page by tools/xray-pack.mjs) once, after the FIRST model
// install. Order: page title, preset, params, camera, selection, tool, kiosk, saved view (openView; the views plugin
// adds boot.views to its list itself). The toolbar plugin reads
// window.__xrayBoot.tools itself. A page without __xrayBoot is untouched. See docs-features/xray-pack.md.
import type { AppPlugin, ViewerApp } from '../app';
import { runAction } from '../input/actions';
import { bootConfig } from '../tools/registry';
import type { XrayBoot } from '../tools/registry';
import { PARAMS_SCHEMA, applyParams } from '../ui/params';
import type { ParamsApp } from '../ui/params';
import type { ElementId } from '../types';
import { openBootView } from './views';
import { getScorePlayer } from '../anim/score';
import type { Score } from '../anim/score';
import { getPlan, registerPlan } from '../anim/fourd/plans';
import { planFilm } from '../anim/fourd/film';
import type { FourDPlan } from '../schedule/types';

/** XrayBoot plus the camera that xray-pack's --camera writes (viewer frame, Y up, origin-shifted). */
type BootWithCamera = XrayBoot & { camera?: { position: [number, number, number]; target: [number, number, number] } };

interface PresetsApi {
  apply(nameOrId: string): unknown;
}
interface ToolbarApi {
  open(id: string): unknown;
}
const win = (): { __xrayPresets?: PresetsApi; __xrayToolbar?: ToolbarApi } => window as unknown as { __xrayPresets?: PresetsApi; __xrayToolbar?: ToolbarApi };

const warn = (msg: string): void => console.warn(`[xray-boot] ${msg}`);

interface FlyApiLike {
  list(): Array<{ id: string; name: string }>;
  importJson(text: string): { ok: boolean; added: number };
  play(args?: { key?: string; loop?: boolean }): boolean;
}
interface ScriptApiLike {
  list(): Array<{ name: string }>;
  save(name: string, text: string): boolean;
  load(name: string): string | null;
  compile(text: string, opts?: { params?: Record<string, string>; libraries?: Record<string, string> }): { score: import('../anim/score').Score | null; errors?: Array<{ severity: string; line: number; message: string }> };
}
/** The film score of a registered 4D plan, with the cues of a script text when it compiles; null when the plan is unknown. */
export function filmScore(
  name: string,
  scriptText?: string | null,
  loop = false,
  /** Values for the script's `param` lines and extra libraries for its `use` lines (name -> text). */
  opts?: { params?: Record<string, string>; libraries?: Record<string, string> },
): { score: Score | null; warning?: string } {
  const plan = getPlan(name);
  if (!plan) return { score: null, warning: `4D plan "${name}" is not registered` };
  let script: Score | null = null;
  let warning: string | undefined;
  if (scriptText) {
    const c = animWin().__xrayScript?.compile(scriptText, opts);
    if (c?.score) script = c.score;
    else {
      const first = c?.errors?.find((e) => e.severity === 'error');
      warning = `the script has errors or the script runtime is not available: the plan plays without it${first ? ` (line ${first.line}: ${first.message})` : ''}`;
    }
    const odd = (c?.errors ?? []).filter((e) => e.severity === 'warning' && /parameter/i.test(e.message));
    if (odd.length) warning = [warning, ...odd.map((e) => e.message)].filter(Boolean).join('; ');
  }
  return { score: planFilm(plan, name, script, loop), ...(warning ? { warning } : {}) };
}

declare global {
  interface Window {
    /** Film score of a registered plan (+ script text): used by `xray-4d render`. */
    __xray4dFilm?: typeof filmScore;
  }
}
if (typeof window !== 'undefined') window.__xray4dFilm = filmScore;

const animWin = (): { __xrayFlythrough?: FlyApiLike; __xrayScript?: ScriptApiLike } => window as unknown as { __xrayFlythrough?: FlyApiLike; __xrayScript?: ScriptApiLike };

/**
 * Fly-throughs and scripts of a packed page: add the ones that the viewer does not have yet (by name, so a reload does not
 * duplicate them), then play the autoplay one. Returns the autoplay start function, or null.
 */
export function applyBootAnimation(boot: XrayBoot): (() => boolean) | null {
  const w = animWin();
  if (boot.flythroughs !== undefined && w.__xrayFlythrough) {
    const doc = boot.flythroughs as { flythroughs?: Array<{ name?: string }> } & Record<string, unknown>;
    const have = new Set(w.__xrayFlythrough.list().map((f) => f.name.toLowerCase()));
    const fresh = Array.isArray(doc.flythroughs) ? doc.flythroughs.filter((f) => typeof f?.name === 'string' && !have.has(f.name.toLowerCase())) : [];
    if (fresh.length > 0) {
      const r = w.__xrayFlythrough.importJson(JSON.stringify({ ...doc, flythroughs: fresh }));
      if (!r.ok) warn('the packed fly-throughs could not be read');
    }
  }
  if (boot.scripts && w.__xrayScript) {
    const have = new Set(w.__xrayScript.list().map((x) => x.name.toLowerCase()));
    for (const sc of boot.scripts) {
      if (typeof sc?.name !== 'string' || typeof sc.text !== 'string' || have.has(sc.name.toLowerCase())) continue;
      if (!w.__xrayScript.save(sc.name, sc.text)) warn(`script "${sc.name}" could not be stored`);
    }
  }
  if (boot.plans) {
    for (const [name, plan] of Object.entries(boot.plans)) {
      if (plan && (plan as FourDPlan).schema === 'xray-4d-plan/1') registerPlan(name, plan as FourDPlan);
      else warn(`4D plan "${name}" is not an xray-4d-plan/1 document`);
    }
  }
  const ap = boot.autoplay;
  if (!ap) return null;
  const loop = ap.loop === true;
  if (typeof ap.plan === 'string') {
    const name = ap.plan;
    const scriptText = typeof ap.script === 'string' ? boot.scripts?.find((x) => x.name.toLowerCase() === ap.script!.toLowerCase())?.text ?? null : null;
    return () => {
      const f = filmScore(name, scriptText, loop, boot.scriptParams ? { params: boot.scriptParams } : undefined);
      if (f.warning) warn(`autoplay: ${f.warning}`);
      const ok = !!f.score && getScorePlayer()?.play(f.score) === true;
      if (!ok) warn(`autoplay: 4D plan "${name}" could not start`);
      return ok;
    };
  }
  if (typeof ap.flythrough === 'string') {
    const name = ap.flythrough;
    return () => {
      const ok = animWin().__xrayFlythrough?.play({ key: name, loop }) === true;
      if (!ok) warn(`autoplay: fly-through "${name}" not found or has no keyframes`);
      return ok;
    };
  }
  if (typeof ap.script === 'string') {
    const name = ap.script;
    return () => {
      const text = animWin().__xrayScript?.load(name) ?? boot.scripts?.find((x) => x.name.toLowerCase() === name.toLowerCase())?.text ?? null;
      const c = text ? animWin().__xrayScript?.compile(text, boot.scriptParams ? { params: boot.scriptParams } : undefined) : null;
      for (const e of c?.errors ?? []) if (e.severity === 'warning' && /parameter/i.test(e.message)) warn(`autoplay: ${e.message}`);
      const score = c?.score ?? null;
      const ok = !!score && getScorePlayer()?.play({ ...score, loop: loop || score.loop === true }) === true;
      if (!ok) warn(`autoplay: script "${name}" not found or it has errors`);
      return ok;
    };
  }
  return null;
}

/** Start the autoplay once the viewer draws its first frame (the player needs the frame loop). */
function startWhenReady(start: () => boolean): void {
  let tries = 0;
  const go = (): void => {
    if ((window as unknown as { __xrayReady?: boolean }).__xrayReady === true || ++tries > 100) {
      setTimeout(() => void start(), 400);
      return;
    }
    setTimeout(go, 100);
  };
  go();
}

/**
 * A boot params document with the schema filled in when it has none: xray-pack accepts partial params files without
 * `schema` and writes the camera on its own, and applyParams would report the missing schema as an ignored key.
 */
export function withSchema(p: unknown): unknown {
  return p && typeof p === 'object' && !Array.isArray(p) ? { schema: PARAMS_SCHEMA, ...(p as Record<string, unknown>) } : p;
}

/** Map select entries (GlobalIds and `class:IfcX`) to element ids. Entries that match nothing are returned in `missing`. */
export function resolveSelect(
  model: { byGlobalId: Map<string, ElementId>; elements: ReadonlyArray<{ id: ElementId; ifcClass: string }> },
  entries: readonly string[],
): { ids: ElementId[]; missing: string[] } {
  const ids = new Set<ElementId>();
  const missing: string[] = [];
  for (const raw of entries) {
    const entry = raw.trim();
    if (!entry) continue;
    if (/^class:/i.test(entry)) {
      const cls = entry.slice(entry.indexOf(':') + 1).trim().toLowerCase();
      let n = 0;
      for (const e of model.elements) {
        if (e.ifcClass.toLowerCase() === cls) {
          ids.add(e.id);
          n++;
        }
      }
      if (n === 0) missing.push(entry);
    } else {
      const id = model.byGlobalId.get(entry);
      if (id === undefined) missing.push(entry);
      else ids.add(id);
    }
  }
  return { ids: [...ids], missing };
}

function openTool(id: string): void {
  // The BCF and Markup drawers moved into the sidebar tab Issues (src/plugins/issues.ts): old boot configs still name them.
  const issues = (window as unknown as { __xrayIssues?: { open(segment: 'issues' | 'sketches'): void } }).__xrayIssues;
  if ((id === 'bcf' || id === 'markup') && issues) {
    issues.open(id === 'bcf' ? 'issues' : 'sketches');
    return;
  }
  const tb = win().__xrayToolbar;
  if (tb?.open) {
    tb.open(id);
    return;
  }
  setTimeout(() => {
    const again = win().__xrayToolbar;
    if (again?.open) again.open(id);
    else warn(`cannot open tool "${id}": the toolbar is not available`);
  }, 500);
}

function applyBoot(app: ViewerApp, boot: BootWithCamera): void {
  if (boot.title) document.title = boot.title;

  if (boot.preset) {
    const presets = win().__xrayPresets;
    if (presets?.apply) {
      try {
        presets.apply(boot.preset);
      } catch (e) {
        warn(`preset "${boot.preset}" failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    } else warn(`preset "${boot.preset}" ignored: this page has no presets`);
  }

  if (boot.params !== undefined) {
    const bad = applyParams(app as unknown as ParamsApp, withSchema(boot.params));
    if (bad.length > 0) warn(`ignored parameter keys: ${bad.join(', ')}`);
  }

  if (boot.camera) {
    const bad = applyParams(app as unknown as ParamsApp, withSchema({ camera: boot.camera }), { reclassify: false });
    if (bad.length > 0) warn('ignored camera: expected position and target as three numbers each');
  }

  if (boot.select && boot.select.length > 0) {
    const { ids, missing } = resolveSelect(app.controller.model, boot.select);
    if (missing.length > 0) warn(`selection entries not found in the model: ${missing.slice(0, 12).join(', ')}${missing.length > 12 ? ', ...' : ''}`);
    if (ids.length > 0) app.selectIds(ids);
  }

  if (boot.kiosk) {
    if (!document.body.classList.contains('sb-collapsed')) runAction(app, 'panel.left');
    if (!document.body.classList.contains('dk-collapsed')) runAction(app, 'panel.right');
  }

  // After the kiosk step: a tool that lives in the right sidebar (classify) opens that column again on purpose.
  if (boot.openTool) openTool(boot.openTool);

  if (boot.openView) {
    if (!openBootView(boot.openView)) warn(`saved view "${boot.openView}" not found`);
  }

  const autoplay = applyBootAnimation(boot);
  if (autoplay) startWhenReady(autoplay);
}

let booted = false;

export const bootPlugin: AppPlugin = {
  name: 'boot',
  onModel(app) {
    if (booted) return;
    booted = true;
    const boot = bootConfig() as BootWithCamera;
    if (Object.keys(boot).length === 0) return;
    try {
      applyBoot(app, boot);
    } catch (e) {
      warn(`boot failed: ${e instanceof Error ? e.stack ?? e.message : String(e)}`);
    }
  },
};
