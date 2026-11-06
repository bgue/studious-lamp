// Point cloud UI: the file input and drop handling, the drawer, and the lil-gui folder.

import type GUI from 'lil-gui';
import type { ViewerApp } from '../app';
import { button, check, note, row, section, select, slider, number, statusLine } from '../tools/ui';
import type { Widget } from '../tools/ui';
import { el } from '../ui/dom';
import { COLOUR_MODES } from './colour';
import type { ColourMode } from './colour';
import type { CoordMode } from './align';
import type { AlignRegion, DeviationScope, PointCloudController } from './controller';
import { ALIGN_REGIONS, DEFAULT_BUDGET, regionName } from './controller';
import { formatDistance } from './register';
import { DROP_EXTENSIONS, extensionOf, isPointCloudName } from './readers';

const ACCEPT = DROP_EXTENSIONS.join(',');
export const SCOPES: DeviationScope[] = ['all elements', 'focus only'];
export const COORD_MODES: CoordMode[] = ['project', 'viewer'];

let input: HTMLInputElement | null = null;

/** The hidden file input (data-pointcloud="open"); scripts and tests can feed it with setInputFiles. */
export function pointCloudInput(c: PointCloudController): HTMLInputElement {
  if (input && document.body.contains(input)) return input;
  const i = el('input', undefined, { type: 'file', accept: ACCEPT, 'data-pointcloud': 'open' });
  i.style.display = 'none';
  i.addEventListener('change', () => {
    const f = i.files?.[0];
    i.value = '';
    if (f) void openFile(c, f);
  });
  document.body.appendChild(i);
  input = i;
  return i;
}

export function pickPointCloud(c: PointCloudController): void {
  pointCloudInput(c).click();
}

export async function openFile(c: PointCloudController, f: File): Promise<void> {
  try {
    await c.load(f, f.name);
  } catch {
    // the controller put the reason in the status line
  }
}

/** Capture-phase drop handler, before plugins/fileLoader.ts: claims drops whose files are all point cloud files. */
export function installDrop(c: PointCloudController): () => void {
  const onDrop = (e: DragEvent): void => {
    const files = Array.from(e.dataTransfer?.files ?? []);
    if (!files.length || !files.every((f) => isPointCloudName(f.name))) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    // the shared drop overlay listens for drop on document, which we pre-empt: let it reset itself
    window.dispatchEvent(new Event('dragend'));
    void openFile(c, files[0]!);
    if (files.length > 1) setTimeout(() => c.noteExtra(`Only one point cloud is shown at a time: opened ${files[0]!.name}, ignored ${files.length - 1} more.`), 50);
  };
  window.addEventListener('drop', onDrop, true);
  return () => window.removeEventListener('drop', onDrop, true);
}

export const ICON =
  '<svg viewBox="0 0 20 20" width="20" height="20" fill="currentColor" stroke="none">' +
  '<circle cx="4" cy="5" r="1.3"/><circle cx="9" cy="3.5" r="1.3"/><circle cx="14" cy="5.5" r="1.3"/><circle cx="17" cy="9" r="1.3"/>' +
  '<circle cx="6" cy="9.5" r="1.3"/><circle cx="11" cy="9" r="1.3"/><circle cx="3.5" cy="14" r="1.3"/><circle cx="8.5" cy="14.5" r="1.3"/>' +
  '<circle cx="13.5" cy="14" r="1.3"/><circle cx="17" cy="16.5" r="1.3"/><circle cx="11" cy="17" r="1.3"/></svg>';

export function buildDrawer(container: HTMLElement, c: PointCloudController, _app: ViewerApp): () => void {
  void _app;
  const buttons: Array<() => void> = [];
  const ws: Widget[] = [];
  const root = el('div', 'pc-drawer');
  root.id = 'pointcloud-drawer';
  container.appendChild(root);
  const put = (n: HTMLElement): void => void root.appendChild(n);
  const addW = <T extends Widget>(w: T): T => {
    ws.push(w);
    root.appendChild(w.root);
    return w;
  };

  put(note('As-built check: open a scan (.las, .e57, .ply, .pcd, .xyz, .pts, .txt; or drop it on the viewer), align it to the model, then compute the deviation.'));
  const open = button('Open point cloud', () => pickPointCloud(c), { primary: true });
  const remove = button('Remove point cloud', () => c.remove());
  put(row(open, remove));
  const status = statusLine(c.status);
  status.setAttribute('data-pc-status', '');
  // The status line never shrinks while the drawer is open (and scrolls beyond 7 lines): a progress line shorter than
  // the previous result would otherwise pull every control below it up, and Stop ICP would move under the pointer.
  status.style.maxHeight = '8.4em';
  status.style.overflowY = 'auto';
  let statusMin = 0;
  put(status);

  put(section('Display'));
  addW(check('visible', () => c.settings.visible, (v) => { c.settings.visible = v; c.applyDisplay(); }));
  addW(slider('point size', 1, 10, 0.5, () => c.settings.pointSize, (v) => { c.settings.pointSize = v; c.applyDisplay(); }, (v) => `${v} px`));
  addW(check('size attenuation', () => c.settings.sizeAttenuation, (v) => { c.settings.sizeAttenuation = v; c.applyDisplay(); }));
  addW(select<ColourMode>('colour by', COLOUR_MODES, () => c.settings.colourBy, (v) => c.setColourBy(v)));
  addW(slider('point budget', 100_000, 10_000_000, 100_000, () => c.settings.budget, (v) => { c.settings.budget = v; }, (v) => `${(v / 1e6).toFixed(1)} M`));
  const apply = button('Apply budget', () => void c.setBudget(c.settings.budget).catch(() => undefined), { title: 'Decimate again to the budget (uniform random sample)' });
  put(apply);

  put(section('Alignment'));
  addW(select<CoordMode>('coordinates', COORD_MODES, () => c.settings.coordinates, (v) => c.setCoordinates(v)));
  put(button('Auto-align to model', () => void c.autoAlign(true), { title: 'Match bounds centres, then try 0/90/180/270 degrees about the vertical axis' }));
  addW(check('keep vertical', () => c.settings.keepVertical, (v) => { c.settings.keepVertical = v; c.resolvePairs(); }));
  addW(check('allow scale', () => c.settings.allowScale, (v) => { c.settings.allowScale = v; c.resolvePairs(); }));
  addW(select<AlignRegion>('align within', ALIGN_REGIONS, () => c.settings.alignRegion, (v) => { c.settings.alignRegion = v; c.resolvePairs(); c.noteRegion(); }));
  const pairBtn = button('Align by 3 points', () => void c.startPairs(), { title: 'Click a point on the cloud, then the same point on the model; 3 times or more' });
  put(pairBtn);
  // the guided 3-point mode: pairs, residuals, warnings and its own buttons
  const pairBox = el('div', 'pc-pairs');
  pairBox.setAttribute('data-pc-pairs', '');
  const pairList = el('div', 'xt-note pc-pair-list');
  const undoPick = button('Undo last', () => c.undoPair(), { title: 'Remove the last picked point' });
  const cancelPick = button('Cancel', () => c.cancelPairs(), { title: 'Leave the 3-point mode without a change (Esc)' });
  const applyPick = button('Apply alignment', () => void c.applyPairs(), { primary: true, title: 'Move the cloud with the solved transform' });
  pairBox.append(pairList, row(undoPick, cancelPick, applyPick));
  put(pairBox);
  // One button, two meanings: the label the user saw decides (data-mode), not the state at the time of the click; a
  // click that arrives just after the run ended (aimed at Stop ICP) does not start a new run.
  let flipAt = 0;
  const icpBtn = button('Refine (ICP)', () => {
    if (icpBtn.dataset.mode === 'stop') c.cancelWork();
    else if (performance.now() - flipAt < 600) c.noteExtra('(ICP had already finished.)');
    else void c.refine();
  }, { title: 'Fit the cloud to the model surfaces (point-to-plane ICP)' });
  icpBtn.dataset.mode = 'refine';
  put(icpBtn);
  // drift diagnostic: residual per region of a 3 x 3 plan grid after ICP
  const regionBox = el('div', 'xt-note pc-regions');
  regionBox.setAttribute('data-pc-regions', '');
  put(regionBox);
  const undoAl = button('Undo alignment', () => void c.undoAlignment(), { title: 'Back to the transform before the last alignment step' });
  const resetAl = button('Reset alignment', () => c.resetAlignment(), { title: 'No offset, no rotation, no registration' });
  put(row(undoAl, resetAl));
  buttons.push(() => {
    const busy = c.busy;
    pairBtn.setDisabled(!c.loaded ? 'Open a point cloud first' : c.pairMode ? 'Picking: use Cancel or Esc to stop' : false);
    pairBox.style.display = c.pairMode ? '' : 'none';
    const running = busy && c.icpRunning;
    const mode = running ? 'stop' : 'refine';
    if (icpBtn.dataset.mode !== mode) {
      if (mode === 'refine') flipAt = performance.now();
      icpBtn.dataset.mode = mode;
      icpBtn.textContent = running ? 'Stop ICP' : 'Refine (ICP)';
    }
    renderRegions(regionBox, c);
    icpBtn.setDisabled(!c.loaded ? 'Open a point cloud first' : c.pairMode ? 'Finish the 3-point alignment first' : busy && !running ? 'Wait for the current step' : false);
    undoAl.setDisabled(c.canUndoAlignment ? false : 'Nothing to undo');
    resetAl.setDisabled(!c.loaded ? 'Open a point cloud first' : false);
    if (c.pairMode) {
      const ps = c.pairs!;
      const sol = c.pairSolution;
      const done = c.solvedPairs;
      const lines: string[] = [];
      ps.forEach((p, i) => {
        const k = done.findIndex((q) => q.cloud === p.cloud);
        const r = sol?.ok && k >= 0 ? `residual ${formatDistance(sol.residuals[k]!)}` : p.model && k < 0 && c.settings.alignRegion !== 'whole cloud' ? 'outside the region, not used' : p.model ? 'picked' : p.cloud ? 'cloud picked, now the model' : '';
        lines.push(`Pair ${i + 1}: ${r}`);
      });
      if (!ps.length) lines.push('Click point 1 on the cloud (cyan), then the same point on the model (orange).');
      if (sol?.ok && done.length >= 2) lines.push(`RMS ${formatDistance(sol.rms)} over ${done.length} pairs${c.settings.allowScale ? `, scale ${sol.scale.toFixed(4)}` : ''}.`);
      for (const w of sol?.warnings ?? []) lines.push(`Warning: ${w}`);
      pairList.replaceChildren(...lines.map((l) => {
        const d = el('div', l.startsWith('Warning') ? 'pc-warn' : undefined, undefined, l);
        if (l.startsWith('Warning')) d.style.color = '#ffb347';
        return d;
      }));
      undoPick.setDisabled(ps.length ? false : 'Nothing picked yet');
      applyPick.setDisabled(sol?.ok && done.length >= 3 ? false : 'Pick 3 pairs first');
    }
  });
  // shown to 0.1 mm (a solved offset has 16 digits); the setting keeps full precision until the field is edited
  const num = (label: string, get: () => number, set: (v: number) => void): Widget => addW(number(label, -1e6, 0.01, () => +get().toFixed(4), (v) => { set(v); c.setAlignment(); }));
  num('offset x', () => c.settings.offsetX, (v) => (c.settings.offsetX = v));
  num('offset y', () => c.settings.offsetY, (v) => (c.settings.offsetY = v));
  num('offset z', () => c.settings.offsetZ, (v) => (c.settings.offsetZ = v));
  addW(slider('rotation (deg)', -180, 180, 0.1, () => c.settings.rotationDeg, (v) => { c.settings.rotationDeg = v; c.setAlignment(); }, (v) => `${v.toFixed(1)}`));
  put(note('Offsets are in metres in the viewer frame (x east, y up, z south) and move the cloud after the coordinate mapping and the registration. A phone scan (Y up) uses coordinates viewer: Align by 3 points, then Refine (ICP).'));

  put(section('Deviation from model'));
  addW(number('tolerance (m)', 0.001, 0.005, () => c.settings.tolerance, (v) => c.setTolerance(v)));
  addW(select<DeviationScope>('deviation scope', SCOPES, () => c.settings.scope, (v) => { c.settings.scope = v; }));
  put(button('Compute deviation', () => void c.computeDeviation(), { primary: true, title: 'Distance of the points to the nearest model surface' }));
  const result = el('div', 'xt-note pc-result');
  put(result);

  const refresh = (): void => {
    status.set(c.status);
    if (root.isConnected) {
      const h = status.offsetHeight;
      if (h > statusMin) {
        statusMin = h;
        status.style.minHeight = `${h}px`;
      }
    }
    for (const w of ws) w.update();
    const d = c.stats.deviation;
    result.textContent = d
      ? `Within tolerance: ${(d.shareWithin * 100).toFixed(1)}% of related points. Mean ${(d.mean * 100).toFixed(1)} cm, 95th percentile ${(d.p95 * 100).toFixed(1)} cm. Unrelated (> ${(d.maxDistance * 100).toFixed(1)} cm): ${(d.unrelatedShare * 100).toFixed(1)}%. Measured ${d.sampled.toLocaleString('en-US')} points in ${(c.stats.deviationMs / 1000).toFixed(1)} s.`
      : '';
    remove.disabled = !c.loaded;
    for (const b of buttons) b();
  };
  refresh();
  const off = c.onChange(refresh);
  return () => {
    off();
    c.cancelPairs(); // the pair list lives in this drawer
  };
}

/**
 * The 3 x 3 plan grid of the last ICP (north up): per cell the local misfit (how far that part sits off when fitted on
 * its own; noise averages out of it), coloured against the typical cell. Nothing before a run.
 */
function renderRegions(box: HTMLElement, c: PointCloudController): void {
  const icp = c.stats.icp;
  const regs = icp?.regions ?? [];
  const sig = icp ? `${icp.ms}|${regs.length}` : '';
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  if (!icp || regs.length !== 9) {
    box.replaceChildren();
    box.style.display = 'none';
    return;
  }
  box.style.display = '';
  const used = regs.filter((r) => r.count >= 40).map((r) => r.misfit).sort((a, b) => a - b);
  const typical = used.length ? used[used.length >> 1]! : 0;
  const grid = el('div');
  grid.style.cssText = 'display:grid;grid-template-columns:repeat(3,1fr);gap:2px;margin:4px 0;font-variant-numeric:tabular-nums';
  for (const r of regs) {
    const ok = r.count >= 40;
    const bad = ok && r.misfit >= 0.004 && r.misfit >= 2.5 * typical;
    const warn = ok && !bad && r.misfit >= 0.003 && r.misfit >= 1.6 * typical;
    const cell = el('div', undefined, { 'data-region': regionName(r) }, ok ? `${(r.misfit * 1000).toFixed(1)} mm` : '-');
    cell.title = `${regionName(r)}: ${r.count} points; off by ${(r.misfit * 1000).toFixed(1)} mm when fitted alone; residual median ${(r.median * 1000).toFixed(1)} mm, RMS ${(r.rms * 1000).toFixed(1)} mm`;
    cell.style.cssText = `text-align:center;padding:2px 0;border-radius:3px;background:${!ok ? 'rgba(127,127,127,0.12)' : bad ? 'rgba(255,90,70,0.35)' : warn ? 'rgba(255,180,70,0.3)' : 'rgba(80,200,120,0.25)'}`;
    grid.appendChild(cell);
  }
  const head = el('div', undefined, undefined, `Local misfit by plan region after ICP (north up${icp.region ? `, ${icp.region.label}` : ''}):`);
  const tail = el('div', undefined, undefined, icp.drift || 'Even fit: no region stands out.');
  if (icp.drift) tail.style.color = '#ffb347';
  box.replaceChildren(head, grid, tail);
}

export function buildGui(gui: GUI, c: PointCloudController): void {
  const folder = gui.addFolder('Point cloud');
  folder.close();
  const s = c.settings;
  const acts = {
    open: () => pickPointCloud(c),
    align: () => void c.autoAlign(true),
    pairs: () => {
      window.__xrayToolbar?.open('pointcloud');
      if (!c.pairMode) c.startPairs();
    },
    refine: () => void c.refine(),
    undo: () => void c.undoAlignment(),
    reset: () => c.resetAlignment(),
    deviation: () => void c.computeDeviation(),
    remove: () => c.remove(),
  };
  const st = new Proxy({} as { status: string }, { get: () => c.status, set: () => true });
  folder.add(acts, 'open').name('Open point cloud');
  folder.add(s, 'visible').name('visible').onChange(() => c.applyDisplay());
  folder.add(s, 'pointSize', 1, 10, 0.5).name('point size').onChange(() => c.applyDisplay());
  folder.add(s, 'colourBy', COLOUR_MODES).name('colour by').onChange((v: ColourMode) => c.setColourBy(v));
  folder.add(s, 'budget', 100_000, 10_000_000, 100_000).name('point budget').onFinishChange((v: number) => void c.setBudget(v).catch(() => undefined));
  folder.add(s, 'coordinates', COORD_MODES).name('coordinates').onChange((v: CoordMode) => c.setCoordinates(v));
  folder.add(acts, 'align').name('Auto-align to model');
  folder.add(s, 'keepVertical').name('keep vertical').onChange(() => c.resolvePairs());
  folder.add(s, 'allowScale').name('allow scale').onChange(() => c.resolvePairs());
  folder.add(s, 'alignRegion', ALIGN_REGIONS).name('align within').onChange(() => { c.resolvePairs(); c.noteRegion(); });
  folder.add(acts, 'pairs').name('Align by 3 points');
  folder.add(acts, 'refine').name('Refine (ICP)');
  folder.add(acts, 'undo').name('Undo alignment');
  folder.add(acts, 'reset').name('Reset alignment');
  folder.add(s, 'offsetX', -1000, 1000, 0.01).name('offset x').onChange(() => c.setAlignment());
  folder.add(s, 'offsetY', -1000, 1000, 0.01).name('offset y').onChange(() => c.setAlignment());
  folder.add(s, 'offsetZ', -1000, 1000, 0.01).name('offset z').onChange(() => c.setAlignment());
  folder.add(s, 'rotationDeg', -180, 180, 0.1).name('rotation (deg)').onChange(() => c.setAlignment());
  folder.add(acts, 'deviation').name('Compute deviation');
  folder.add(s, 'tolerance', 0.001, 0.5, 0.001).name('tolerance (m)').onChange((v: number) => c.setTolerance(v));
  folder.add(s, 'scope', SCOPES).name('deviation scope');
  folder.add(acts, 'remove').name('Remove point cloud');
  const ctrl = folder.add(st, 'status').name('Point cloud status').disable();
  c.onChange(() => {
    folder.controllers.forEach((k) => k.updateDisplay());
    void ctrl;
  });
}

export { DEFAULT_BUDGET, extensionOf };
