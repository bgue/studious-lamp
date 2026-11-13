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

  if (boot.openTool) openTool(boot.openTool);

  if (boot.kiosk) {
    if (!document.body.classList.contains('sb-collapsed')) runAction(app, 'panel.left');
    if (!document.body.classList.contains('dk-collapsed')) runAction(app, 'panel.right');
  }

  if (boot.openView) {
    if (!openBootView(boot.openView)) warn(`saved view "${boot.openView}" not found`);
  }
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
