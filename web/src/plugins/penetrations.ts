// Penetration schedule plugin (tool `penetrations`): where MEP elements pass through slabs, walls, beams, columns,
// footings and roofs, and whether the host has an opening there. Analysis is in penetrations/analysis.ts; this file
// is the drawer, the markers on the shared SVG overlay, the lil-gui folder and the params section.
// See docs-features/penetrations.md.
//
//   window.__xrayPenetrations = { analyse(opts?), rows }

import { Box3, Vector3 } from 'three';
import type GUI from 'lil-gui';
import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { filterRows, PEN_CSV_HEADER, penetrationCsvRows } from '../penetrations/analysis';
import type { PenFilter, PenStatus, Penetration, PenSummary } from '../penetrations/analysis';
import { runPenetrations, SCOPES } from '../penetrations/runner';
import type { PenRun, PenScope } from '../penetrations/runner';
import { downloadText, toCsv } from '../tools/csv';
import { ICONS } from '../tools/icons';
import { registerTool } from '../tools/registry';
import { button, check, chips, note, row, section, select, statusLine } from '../tools/ui';
import { el } from '../ui/dom';
import { requestFrame } from '../ui/fit';
import { getOverlay, svgEl } from '../ui/overlay';
import type { Overlay } from '../ui/overlay';
import { registerParamSection } from '../ui/params';

export const STATUS_COLOUR: Record<PenStatus, string> = { none: '#ef4444', opening: '#22c55e', unknown: '#9aa5b4' };
const STATUS_LABEL: Record<PenStatus, string> = { none: 'no opening', opening: 'opening', unknown: 'unknown' };

interface BcfApi {
  createTopics(list: unknown[]): unknown;
}
const bcfApi = (): BcfApi | undefined => (window as unknown as { __xrayBcf?: BcfApi }).__xrayBcf;

declare global {
  interface Window {
    __xrayPenetrations?: {
      analyse(opts?: { scope?: PenScope; markers?: boolean }): PenRun;
      readonly rows: Penetration[];
      readonly summary: PenSummary;
    };
  }
}

type SortKey = 'id' | 'mep' | 'host' | 'storey' | 'size' | 'thickness' | 'status' | 'gap';

class PenetrationsTool {
  opts = { scope: 'focus classes' as PenScope, markers: true };
  run: PenRun | null = null;
  rows: Penetration[] = [];
  readonly filter = { status: new Set<PenStatus>(), storeys: new Set<number | null>(), hostClasses: new Set<string>() };
  sort: { key: SortKey; dir: 1 | -1 } = { key: 'id', dir: 1 };
  readonly selected = new Set<number>();
  private folder: GUI | null = null;
  private overlay: Overlay | null = null;
  private layer: SVGGElement | null = null;
  private pool: SVGCircleElement[] = [];
  private pulse: { loc: [number, number, number]; until: number } | null = null;
  private pulseEl: SVGGElement | null = null;
  private listeners = new Set<() => void>();
  private lastModel = '';

  constructor(readonly app: ViewerApp) {}

  attach(folder: GUI): void {
    this.folder = folder;
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  private emit(): void {
    this.overlay?.invalidate();
    for (const l of this.listeners) l();
    this.folder?.controllersRecursive().forEach((c) => c.updateDisplay());
  }

  // ---------------------------------------------------------------- analysis

  analyse(over?: { scope?: PenScope; markers?: boolean }): PenRun {
    if (over?.scope && (SCOPES as readonly string[]).includes(over.scope)) this.opts.scope = over.scope;
    if (typeof over?.markers === 'boolean') this.opts.markers = over.markers;
    this.ensureOverlay();
    const r = runPenetrations(this.app, this.opts.scope);
    this.run = r;
    this.rows = r.rows;
    this.selected.clear();
    this.filter.status.clear();
    this.filter.storeys.clear();
    this.filter.hostClasses.clear();
    this.lastModel = this.app.modelName;
    this.emit();
    return r;
  }

  get statusText(): string {
    const r = this.run;
    if (!r) return 'Not analysed yet';
    const s = r.summary;
    return `${s.total} penetrations: ${s.opening} with opening, ${s.none} no opening, ${s.unknown} unknown (${r.mepCount} MEP, ${r.hostCount} hosts, ${r.ms.toFixed(0)} ms)`;
  }

  hasRunFor(model: string): boolean {
    return this.run !== null && this.lastModel === model;
  }

  onModel(): void {
    this.run = null;
    this.rows = [];
    this.selected.clear();
    this.pulse = null;
    this.emit();
  }

  // ---------------------------------------------------------------- views of the data

  get model() {
    return this.app.controller.model;
  }

  hostClassOf = (id: number): string => this.model.elements[id]?.ifcClass ?? '';

  private label(id: number): string {
    const e = this.model.elements[id];
    if (!e) return `#${id}`;
    return e.name && e.name.trim() ? e.name : `${e.ifcClass.replace(/^Ifc/, '')} #${id}`;
  }

  mepLabel = (id: number): string => this.label(id);
  hostLabel = (id: number): string => this.label(id);

  storeyName = (s: number | null): string => (s === null ? '-' : (this.model.storeys[s]?.name ?? String(s)));

  visibleRows(): Penetration[] {
    const f: PenFilter = { status: this.filter.status, storeys: this.filter.storeys, hostClasses: this.filter.hostClasses };
    const rows = filterRows(this.rows, f, this.hostClassOf);
    const { key, dir } = this.sort;
    const elev = (s: number | null): number => (s === null ? -1e9 : (this.model.storeys[s]?.elevation ?? 0));
    const val = (r: Penetration): number | string => {
      switch (key) {
        case 'id': return r.id;
        case 'mep': return this.mepLabel(r.mep).toLowerCase();
        case 'host': return this.hostLabel(r.host).toLowerCase();
        case 'storey': return elev(r.storey);
        case 'size': return r.sizeMm[1] * 1e5 + r.sizeMm[0];
        case 'thickness': return r.hostThicknessMm;
        case 'status': return r.status;
        case 'gap': return r.gapMm ?? -1e9;
      }
    };
    return [...rows].sort((a, b) => {
      const x = val(a), y = val(b);
      const c = typeof x === 'string' ? (x < (y as string) ? -1 : x > (y as string) ? 1 : 0) : (x as number) - (y as number);
      return (c || a.id - b.id) * dir;
    });
  }

  // ---------------------------------------------------------------- actions

  exportCsv(): number {
    if (!this.run) this.analyse();
    const rows = this.visibleRows();
    const m = this.model;
    const csv = toCsv(PEN_CSV_HEADER, penetrationCsvRows(rows, {
      mepName: (id) => m.elements[id]?.name ?? '', mepGlobalId: (id) => m.elements[id]?.globalId ?? '', mepClass: (id) => m.elements[id]?.ifcClass ?? '',
      hostName: (id) => m.elements[id]?.name ?? '', hostGlobalId: (id) => m.elements[id]?.globalId ?? '', hostClass: (id) => m.elements[id]?.ifcClass ?? '',
      storeyName: this.storeyName,
    }));
    downloadText(`penetrations-${this.app.modelName}.csv`, csv);
    return rows.length;
  }

  /** Why the BCF button is off, or null when it works. */
  bcfDisabledReason(): string | null {
    if (!bcfApi()?.createTopics) return 'BCF export is not available in this build (window.__xrayBcf.createTopics is missing)';
    if (this.rows.length === 0) return 'Analyse first';
    return null;
  }

  async createBcf(): Promise<number> {
    const api = bcfApi();
    if (!api?.createTopics) return 0;
    const chosen = this.selected.size > 0 ? this.visibleRows().filter((r) => this.selected.has(r.id)) : this.visibleRows();
    const m = this.model;
    const shift = m.originShift;
    const list = chosen.map((r) => {
      const mep = m.elements[r.mep];
      const host = m.elements[r.host];
      const [x, y, z] = r.location;
      return {
        title: `Penetration #${r.id}: ${this.mepLabel(r.mep)} through ${this.hostLabel(r.host)}`,
        description:
          `${STATUS_LABEL[r.status]}${r.gapMm !== null ? `, gap ${r.gapMm} mm` : ''}; ${r.orientation}; ${r.sizeMm[0]} x ${r.sizeMm[1]} mm; ` +
          `host thickness ${r.hostThicknessMm} mm; storey ${this.storeyName(r.storey)}`,
        labels: ['penetration', r.status],
        status: r.status,
        elementIds: [r.mep, r.host],
        elements: [mep?.globalId, host?.globalId].filter((g): g is string => !!g),
        /** viewer frame (Y up, origin shifted) */
        location: { x, y, z },
        /** IFC world frame (Z up, metres) */
        ifcLocation: { x: x + shift[0], y: -z + shift[1], z: y + shift[2] },
      };
    });
    await api.createTopics(list);
    return list.length;
  }

  select(r: Penetration, additive: boolean): void {
    if (additive) {
      if (this.selected.has(r.id)) this.selected.delete(r.id);
      else this.selected.add(r.id);
    } else {
      this.selected.clear();
      this.selected.add(r.id);
    }
    this.app.selectIds([r.mep]);
    this.flyTo(r);
    this.pulse = { loc: r.location, until: performance.now() + 1400 };
    this.overlay?.invalidate();
    for (const l of this.listeners) l();
  }

  private flyTo(r: Penetration): void {
    const half = Math.max(0.75, 2 * Math.max(r.sizeMm[1], r.hostThicknessMm) / 1000);
    const [x, y, z] = r.location;
    const box = new Box3(new Vector3(x - half, y - half, z - half), new Vector3(x + half, y + half, z + half));
    const cin = (window as unknown as { __cinematic?: { flyTo(b: Box3): void } }).__cinematic;
    if (cin?.flyTo) cin.flyTo(box);
    else requestFrame(this.app.renderer.camera, this.app.renderer.controls, box);
    this.app.renderer.markDirty();
  }

  // ---------------------------------------------------------------- markers

  ensureOverlay(): void {
    if (this.overlay) return;
    this.overlay = getOverlay(this.app);
    this.layer = this.overlay.layer('penetrations');
    this.overlay.onUpdate((ov) => this.drawMarkers(ov));
  }

  private drawMarkers(ov: Overlay): void {
    const layer = this.layer;
    if (!layer) return;
    const show = this.opts.markers && this.rows.length > 0;
    const rows = show ? this.visibleRows() : [];
    const sp = { x: 0, y: 0, visible: false, front: false, depth: 0 };
    let used = 0;
    for (const r of rows) {
      ov.project(r.location, sp);
      if (!sp.visible) continue;
      let c = this.pool[used];
      if (!c) {
        c = svgEl('circle', { r: 5, 'stroke-width': 1.5, 'fill-opacity': 0.55 });
        layer.appendChild(c);
        this.pool[used] = c;
      }
      used++;
      c.setAttribute('cx', sp.x.toFixed(1));
      c.setAttribute('cy', sp.y.toFixed(1));
      const col = STATUS_COLOUR[r.status];
      if (c.getAttribute('fill') !== col) {
        c.setAttribute('fill', col);
        c.setAttribute('stroke', '#0b0f14');
      }
      const sel = this.selected.has(r.id);
      c.setAttribute('r', sel ? '7' : '5');
      c.setAttribute('stroke-width', sel ? '2.5' : '1.5');
      c.style.display = '';
      c.setAttribute('data-pen', String(r.id));
    }
    for (let i = used; i < this.pool.length; i++) this.pool[i]!.style.display = 'none';

    // pulse ring
    const now = performance.now();
    if (this.pulse && now < this.pulse.until) {
      ov.project(this.pulse.loc, sp);
      if (sp.visible) {
        if (!this.pulseEl) {
          const g = svgEl('g', { 'data-pulse': '1' });
          const ring = svgEl('circle', { fill: 'none', stroke: '#fff', 'stroke-width': 2.5, r: 6 });
          ring.appendChild(svgEl('animate', { attributeName: 'r', from: 6, to: 38, dur: '1.2s', fill: 'freeze', repeatCount: 1 }));
          ring.appendChild(svgEl('animate', { attributeName: 'opacity', from: 1, to: 0, dur: '1.2s', fill: 'freeze', repeatCount: 1 }));
          g.appendChild(ring);
          layer.appendChild(g);
          this.pulseEl = g;
        }
        this.pulseEl.setAttribute('transform', `translate(${sp.x.toFixed(1)} ${sp.y.toFixed(1)})`);
      }
      ov.invalidate(); // keep following the camera while the ring plays
    } else {
      this.pulseEl?.remove();
      this.pulseEl = null;
      this.pulse = null;
    }
  }

  onChangeMarkers: () => void = () => undefined;
  refreshMarkers: () => void = () => undefined;
  overlayInvalidate(): void {
    this.overlay?.invalidate();
  }

  /** Number of markers currently drawn (for tests). */
  markerCount(): number {
    return this.pool.filter((c) => c.style.display !== 'none').length;
  }
}

let tool: PenetrationsTool | null = null;

function panel(box: HTMLElement, app: ViewerApp): (() => void) | void {
  const t = tool;
  if (!t) return;
  t.ensureOverlay();
  if (!t.hasRunFor(app.modelName)) t.analyse();

  const status = statusLine(t.statusText);
  const bcfBtn = button('Create BCF topics', () => {
    void t.createBcf().then((n) => status.set(`Created ${n} BCF topics`));
  }, { title: 'One topic per selected (or filtered) row' });
  const exportBtn = button('Export CSV', () => {
    const n = t.exportCsv();
    status.set(`Exported ${n} rows`);
  }, { title: 'Download the filtered rows as CSV' });
  const analyseBtn = button('Analyse', () => t.analyse(), { primary: true, title: 'Run the analysis again (after changing the focus, scope or model)' });
  const scope = select<PenScope>('scope', SCOPES, () => t.opts.scope, (v) => { t.opts.scope = v; });
  const markers = check('Markers on the model', () => t.opts.markers, (v) => { t.opts.markers = v; t.onChangeMarkers(); });

  box.append(row(analyseBtn, exportBtn, bcfBtn), scope.root, markers.root, status);
  scope.update();
  markers.update();

  const filters = el('div');
  const tableWrap = el('div', 'xt-table-wrap');
  box.append(filters, tableWrap);

  const MAXROWS = 500;
  const COLS: Array<{ key: SortKey; label: string; title: string }> = [
    { key: 'id', label: '#', title: 'Penetration number' },
    { key: 'mep', label: 'Element', title: 'MEP element' },
    { key: 'host', label: 'Host', title: 'Structural host' },
    { key: 'storey', label: 'Storey', title: 'Storey of the host' },
    { key: 'size', label: 'Size', title: 'The two smaller extents of the MEP bounds, mm (approximate for inclined runs)' },
    { key: 'thickness', label: 'Thk', title: 'Smallest extent of the host, mm' },
    { key: 'status', label: 'Status', title: 'opening / no opening / unknown (no opening data in the model)' },
    { key: 'gap', label: 'Gap', title: 'Clearance between the MEP section and the opening, mm' },
  ];

  const renderTable = (): void => {
    const rows = t.visibleRows();
    const table = el('table', 'xt-table');
    const head = el('tr');
    for (const c of COLS) {
      const th = el('th', t.sort.key === c.key ? `sorted${t.sort.dir < 0 ? ' desc' : ''}` : '', { title: c.title }, c.label);
      th.addEventListener('click', () => {
        t.sort = t.sort.key === c.key ? { key: c.key, dir: (t.sort.dir * -1) as 1 | -1 } : { key: c.key, dir: 1 };
        renderTable();
      });
      head.appendChild(th);
    }
    const thead = el('thead');
    thead.appendChild(head);
    table.appendChild(thead);
    const tb = el('tbody');
    for (const r of rows.slice(0, MAXROWS)) {
      const tr = el('tr', t.selected.has(r.id) ? 'sel' : '', { 'data-pen': String(r.id) });
      const dot = el('span', 'xt-dot');
      dot.style.background = STATUS_COLOUR[r.status];
      const stCell = el('td');
      stCell.append(dot, document.createTextNode(STATUS_LABEL[r.status]));
      const cells: Array<HTMLElement | string> = [
        String(r.id), t.mepLabel(r.mep), t.hostLabel(r.host), t.storeyName(r.storey),
        `${r.sizeMm[0]}x${r.sizeMm[1]}`, String(r.hostThicknessMm), '', r.gapMm === null ? '' : String(r.gapMm),
      ];
      cells.forEach((c, i) => {
        if (i === 6) tr.appendChild(stCell);
        else {
          const td = el('td', undefined, i === 1 || i === 2 ? { title: String(c) } : undefined, String(c));
          tr.appendChild(td);
        }
      });
      tr.addEventListener('click', (ev) => {
        t.select(r, ev.ctrlKey || ev.metaKey || ev.shiftKey);
        tb.querySelectorAll('tr').forEach((x) => x.classList.toggle('sel', t.selected.has(Number(x.getAttribute('data-pen')))));
      });
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    tableWrap.textContent = '';
    tableWrap.appendChild(table);
    if (rows.length > MAXROWS) tableWrap.appendChild(el('div', 'xt-note', undefined, `Showing the first ${MAXROWS} of ${rows.length} rows; filter or export the rest.`));
    if (rows.length === 0) tableWrap.appendChild(el('div', 'xt-note', undefined, t.rows.length === 0 ? 'No penetrations found.' : 'No rows match the filters.'));
    exportBtn.textContent = `Export CSV (${rows.length})`;
    const why = t.bcfDisabledReason();
    bcfBtn.setDisabled(why ?? false);
  };

  const renderFilters = (): void => {
    filters.textContent = '';
    const s = t.run?.summary;
    filters.appendChild(section('Status'));
    filters.appendChild(chips<PenStatus>([
      { value: 'none', label: `no opening${s ? ` ${s.none}` : ''}` },
      { value: 'opening', label: `opening${s ? ` ${s.opening}` : ''}` },
      { value: 'unknown', label: `unknown${s ? ` ${s.unknown}` : ''}` },
    ], t.filter.status, () => { renderTable(); t.refreshMarkers(); }));
    const storeys = [...new Set(t.rows.map((r) => r.storey))].sort((a, b) => (a ?? -1) - (b ?? -1));
    if (storeys.length > 1) {
      filters.appendChild(section('Storey'));
      filters.appendChild(chips<number | null>(storeys.map((v) => ({ value: v, label: t.storeyName(v) })), t.filter.storeys, () => { renderTable(); t.refreshMarkers(); }));
    }
    const classes = [...new Set(t.rows.map((r) => t.hostClassOf(r.host)))].sort();
    if (classes.length > 1) {
      filters.appendChild(section('Host class'));
      filters.appendChild(chips<string>(classes.map((v) => ({ value: v, label: v.replace(/^Ifc/, '') })), t.filter.hostClasses, () => { renderTable(); t.refreshMarkers(); }));
    }
    if (!t.run?.hasOpeningData) filters.appendChild(note('This model has no opening data: statuses are unknown unless the element is hosted by relation. Reconvert with the current tools/ifc2glb.py, or open the IFC file, to get openings.'));
  };

  const refresh = (): void => {
    status.set(t.statusText);
    renderFilters();
    renderTable();
  };
  refresh();
  const off = t.onChange(refresh);
  const timer = setInterval(() => bcfBtn.setDisabled(t.bcfDisabledReason() ?? false), 1000);
  return () => {
    off();
    clearInterval(timer);
  };
}

export const penetrationsPlugin: AppPlugin = {
  name: 'penetrations',

  install(app: ViewerApp): void {
    const t = new PenetrationsTool(app);
    tool = t;
    t.refreshMarkers = () => {
      t.ensureOverlay();
      t.overlayInvalidate();
    };
    t.onChangeMarkers = () => t.refreshMarkers();

    registerTool({
      id: 'penetrations', label: 'Penetrations', title: 'Schedule of MEP penetrations through slabs and walls, with opening status',
      icon: ICONS.penetrations, order: 90, drawerWidth: 460, panel: (box, a) => panel(box, a),
    });
    registerAction({ id: 'penetrations.analyse', label: 'Penetrations: analyse', group: 'Tools', keys: [], run: () => void t.analyse() });

    registerParamSection('penetrations', {
      collect: () => ({ scope: t.opts.scope, markers: t.opts.markers }),
      apply(value, bad, path) {
        if (!value || typeof value !== 'object') { bad.push(path); return; }
        const v = value as Record<string, unknown>;
        if (v['scope'] !== undefined) {
          if ((SCOPES as readonly unknown[]).includes(v['scope'])) t.opts.scope = v['scope'] as PenScope;
          else bad.push(`${path}.scope`);
        }
        if (v['markers'] !== undefined) {
          if (typeof v['markers'] === 'boolean') t.opts.markers = v['markers'];
          else bad.push(`${path}.markers`);
        }
        t.refreshMarkers();
      },
    });

    window.__xrayPenetrations = {
      analyse: (o) => t.analyse(o),
      get rows() { return t.rows; },
      get summary() { return t.run?.summary ?? { total: 0, opening: 0, none: 0, unknown: 0 }; },
    };

    const gui = app.panel;
    if (gui) {
      const f = gui.addFolder('Penetrations');
      f.close();
      t.attach(f);
      const actions = {
        analyse: () => void t.analyse(),
        exportCsv: () => void t.exportCsv(),
      };
      f.add(actions, 'analyse').name('Analyse penetrations');
      f.add(actions, 'exportCsv').name('Export penetrations CSV');
      f.add(t.opts, 'scope', [...SCOPES]).name('scope');
      f.add(t.opts, 'markers').name('markers').onChange(() => t.refreshMarkers());
      const st = { get status() { return t.statusText; } };
      f.add(st, 'status').name('Penetration status').disable();
    }
  },

  onModel(): void {
    tool?.onModel();
  },
};
