// Point cloud UI: the file input and drop handling, the drawer, and the lil-gui folder.

import type GUI from 'lil-gui';
import type { ViewerApp } from '../app';
import { button, check, note, row, section, select, slider, number, statusLine } from '../tools/ui';
import type { Widget } from '../tools/ui';
import { el } from '../ui/dom';
import { COLOUR_MODES } from './colour';
import type { ColourMode } from './colour';
import type { CoordMode } from './align';
import type { DeviationScope, PointCloudController } from './controller';
import { DEFAULT_BUDGET } from './controller';
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

  put(note('As-built check: open a scan (.las, .ply, .pcd, .xyz, .pts, .txt; or drop it on the viewer), align it to the model, then compute the deviation.'));
  const open = button('Open point cloud', () => pickPointCloud(c), { primary: true });
  const remove = button('Remove point cloud', () => c.remove());
  put(row(open, remove));
  const status = statusLine(c.status);
  status.setAttribute('data-pc-status', '');
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
  const num = (label: string, get: () => number, set: (v: number) => void): Widget => addW(number(label, -1e6, 0.01, get, (v) => { set(v); c.setAlignment(); }));
  num('offset x', () => c.settings.offsetX, (v) => (c.settings.offsetX = v));
  num('offset y', () => c.settings.offsetY, (v) => (c.settings.offsetY = v));
  num('offset z', () => c.settings.offsetZ, (v) => (c.settings.offsetZ = v));
  addW(slider('rotation (deg)', -180, 180, 0.1, () => c.settings.rotationDeg, (v) => { c.settings.rotationDeg = v; c.setAlignment(); }, (v) => `${v.toFixed(1)}`));
  put(note('Offsets are in metres in the viewer frame (x east, y up, z south) and move the cloud after the coordinate mapping.'));

  put(section('Deviation from model'));
  addW(number('tolerance (m)', 0.001, 0.005, () => c.settings.tolerance, (v) => c.setTolerance(v)));
  addW(select<DeviationScope>('deviation scope', SCOPES, () => c.settings.scope, (v) => { c.settings.scope = v; }));
  put(button('Compute deviation', () => void c.computeDeviation(), { primary: true, title: 'Distance of the points to the nearest model surface' }));
  const result = el('div', 'xt-note pc-result');
  put(result);

  const refresh = (): void => {
    status.set(c.status);
    for (const w of ws) w.update();
    const d = c.stats.deviation;
    result.textContent = d
      ? `Within tolerance: ${(d.shareWithin * 100).toFixed(1)}% of related points. Mean ${(d.mean * 100).toFixed(1)} cm, 95th percentile ${(d.p95 * 100).toFixed(1)} cm. Unrelated (> ${(d.maxDistance * 100).toFixed(1)} cm): ${(d.unrelatedShare * 100).toFixed(1)}%. Measured ${d.sampled.toLocaleString('en-US')} points in ${(c.stats.deviationMs / 1000).toFixed(1)} s.`
      : '';
    remove.disabled = !c.loaded;
  };
  refresh();
  return c.onChange(refresh);
}

export function buildGui(gui: GUI, c: PointCloudController): void {
  const folder = gui.addFolder('Point cloud');
  folder.close();
  const s = c.settings;
  const acts = {
    open: () => pickPointCloud(c),
    align: () => void c.autoAlign(true),
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
