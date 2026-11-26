// The "By classification" half of the Model tab: the switch (Model tree | By classification), the Group by controls and the tree
// computed from the facet values. The tree itself is the model tree's TreeView (virtualised, same keyboard): this file only
// feeds it rows. State (mode, grouping) is a per-viewer convenience kept in localStorage. Docs: docs-features/classification-tree.md.

import type { ElementId, SceneModel } from '../types';
import {
  LEVEL_CHOICES, MAX_LEVELS, PRESETS, buildClassTree, needsReview, parseUniformat, topKeys,
} from '../classify/classTree';
import type { ClassInfo, ClassPreset, UniformatTable } from '../classify/classTree';
import type { FacetResult } from '../classify/facets/defs';
import uniformatJson from '../../public/classification/uniformat2.json';
import { el } from './dom';
import { matchesElement } from './treeModel';
import type { TreeNode } from './treeModel';
import type { TreeView } from './treeView';

const KEY = 'xray.classtree.v1';
const UF_KEY = 'xray.uniformat2.custom';

export interface ClassTreeState {
  mode: 'model' | 'class';
  preset: string;
  levels: string[];
}

const DEFAULT_STATE: ClassTreeState = { mode: 'model', preset: 'construction', levels: PRESETS[0]!.levels.slice() };

/** The minimum of the classifier the tree reads: the discipline results and the facet values by GlobalId. */
export interface ClassSource {
  results(): ReadonlyArray<{ id: string; discipline: { code: string; label: string }; subDiscipline?: { code: string; label: string } | null; needsReview?: boolean }>;
  facetResults(): ReadonlyMap<string, Readonly<Record<string, FacetResult | undefined>>> | Readonly<Record<string, Readonly<Record<string, FacetResult | undefined>>>>;
  /** Column names of the discipline and sub-discipline (for the queries of the nodes). */
  columns?(): { discipline: string; subDiscipline: string };
  /** The preferred order of the codes of each facet (its code list). */
  order?(): Record<string, string[]>;
}

/** One ClassInfo per element of the model, joined with the classifier's results. */
export function collectClassInfos(model: SceneModel, src: ClassSource | null): ClassInfo[] {
  const disc = new Map<string, ReturnType<ClassSource['results']>[number]>();
  const facets = src?.facetResults();
  const facetOf = (gid: string): Readonly<Record<string, FacetResult | undefined>> =>
    (facets instanceof Map ? facets.get(gid) : (facets as Record<string, Readonly<Record<string, FacetResult | undefined>>> | undefined)?.[gid]) ?? {};
  if (src) for (const r of src.results()) disc.set(r.id, r);
  const storeyName = new Map(model.storeys.map((s) => [s.id, s.name]));
  return model.elements.map((e) => {
    const d = disc.get(e.globalId);
    const info: ClassInfo = {
      id: e.id, name: e.name ?? '', globalId: e.globalId, ifcClass: e.ifcClass,
      storey: e.storey !== null && e.storey !== undefined ? storeyName.get(e.storey) ?? '' : '',
      facets: facetOf(e.globalId),
    };
    if (d) {
      info.discipline = { code: d.discipline.code, label: d.discipline.label };
      if (d.subDiscipline) info.subDiscipline = { code: d.subDiscipline.code, label: d.subDiscipline.label };
      if (d.needsReview) info.disciplineReview = true;
    }
    return info;
  });
}

let shipped: UniformatTable | null | undefined;

/** The UniFormat mapping in use: the one this viewer imported, else the shipped file. */
export function uniformatTable(): UniformatTable | null {
  try {
    const raw = localStorage.getItem(UF_KEY);
    if (raw) {
      const t = parseUniformat(JSON.parse(raw)).table;
      if (t) return t;
    }
  } catch {
    /* a broken stored mapping is no mapping */
  }
  if (shipped === undefined) shipped = parseUniformat(uniformatJson).table;
  return shipped;
}

function readState(): ClassTreeState {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Partial<ClassTreeState> | null;
    if (v) {
      const levels = Array.isArray(v.levels) ? v.levels.filter((x): x is string => typeof x === 'string').slice(0, MAX_LEVELS) : [];
      return {
        mode: v.mode === 'class' ? 'class' : 'model',
        preset: typeof v.preset === 'string' ? v.preset : DEFAULT_STATE.preset,
        levels: levels.length > 0 ? levels : DEFAULT_STATE.levels.slice(),
      };
    }
  } catch {
    /* ignore */
  }
  return { ...DEFAULT_STATE, levels: DEFAULT_STATE.levels.slice() };
}

function writeState(s: ClassTreeState): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

export interface ClassTreeHost {
  source(): ClassSource | null;
  model(): SceneModel | null;
  /** Open the criteria-set editor with this query. */
  saveQuery(query: string, name: string): void;
  /** Save these elements as a plain set (the node has no query). */
  saveIds(name: string, ids: readonly ElementId[]): string;
  /** The mode changed: the sidebar clears and re-routes its filter box. */
  modeChanged(): void;
}

export interface ClassTreePanel {
  /** The switch and the controls, to put above the tree. */
  readonly root: HTMLElement;
  readonly active: boolean;
  state(): ClassTreeState;
  setMode(mode: 'model' | 'class'): void;
  setLevels(levels: string[]): void;
  /** Recompute after a new model, a new classification or a new filter. */
  refresh(opts?: { reset?: boolean }): void;
  setFilter(q: string): void;
  /** "Save as set" for a group node. */
  save(node: TreeNode): void;
  /** The nodes of the tree on screen (for scripts). */
  roots(): readonly TreeNode[];
}

const sameLevels = (a: readonly string[], b: readonly string[]): boolean => a.length === b.length && a.every((x, i) => x === b[i]);

export function createClassTreePanel(tree: TreeView, host: ClassTreeHost): ClassTreePanel {
  const st = readState();
  const root = el('div', 'ct');
  const seg = el('div', 'ct-seg', { role: 'group', 'aria-label': 'Model tab view' });
  const bModel = el('button', 'ct-seg-btn', { type: 'button', 'data-mode': 'model', 'data-help-key': 'Sidebar/Model tree view', 'data-help-title': 'Model tree' }, 'Model tree');
  const bClass = el('button', 'ct-seg-btn', { type: 'button', 'data-mode': 'class', 'data-help-key': 'Sidebar/By classification view', 'data-help-title': 'By classification' }, 'By classification');
  seg.append(bModel, bClass);

  const controls = el('div', 'ct-ctl', { 'data-role': 'class-controls' });
  const presetSel = el('select', 'inp', { 'aria-label': 'Group by preset', 'data-role': 'preset', 'data-help-key': 'Sidebar/Group by preset', 'data-help-title': 'Group by' }) as HTMLSelectElement;
  for (const p of PRESETS) presetSel.appendChild(el('option', undefined, { value: p.id }, p.label));
  presetSel.appendChild(el('option', undefined, { value: 'custom' }, 'Custom'));
  const presetRow = el('div', 'ct-row');
  presetRow.append(el('span', 'ct-lbl', undefined, 'Group by'), presetSel);
  const levelRow = el('div', 'ct-levels');
  const levelSels: HTMLSelectElement[] = [];
  for (let i = 0; i < MAX_LEVELS; i++) {
    const s = el('select', 'inp', { 'aria-label': `Level ${i + 1}`, 'data-role': 'level', 'data-i': String(i), 'data-help-key': 'Sidebar/Group level', 'data-help-title': 'Level' }) as HTMLSelectElement;
    if (i > 0) s.appendChild(el('option', undefined, { value: '' }, '(none)'));
    for (const l of LEVEL_CHOICES) s.appendChild(el('option', undefined, { value: l.id }, l.label));
    levelSels.push(s);
    levelRow.appendChild(s);
  }
  const mapRow = el('div', 'ct-row');
  const mapBtn = el('button', 'btn', { type: 'button', 'data-help-key': 'Sidebar/UniFormat mapping', 'data-help-title': 'UniFormat mapping', title: 'Load your own mapping table from a JSON file' }, 'Mapping...');
  const mapReset = el('button', 'btn', { type: 'button', 'data-help-key': 'Sidebar/UniFormat mapping', 'data-help-title': 'UniFormat mapping', title: 'Go back to the shipped mapping table' }, 'Reset');
  const mapFile = el('input', undefined, { type: 'file', accept: 'application/json,.json', hidden: '' }) as HTMLInputElement;
  mapRow.append(mapBtn, mapReset, mapFile);
  const note = el('div', 'ct-note', { 'data-role': 'class-note', role: 'status' });
  controls.append(presetRow, levelRow, mapRow, note);
  root.append(seg, controls);

  let allInfos: ClassInfo[] = [];
  let shown: TreeNode[] = [];
  let filterQ = '';

  const syncControls = (): void => {
    bModel.setAttribute('aria-pressed', String(st.mode === 'model'));
    bClass.setAttribute('aria-pressed', String(st.mode === 'class'));
    bModel.classList.toggle('on', st.mode === 'model');
    bClass.classList.toggle('on', st.mode === 'class');
    controls.style.display = st.mode === 'class' ? '' : 'none';
    presetSel.value = st.preset;
    levelSels.forEach((s, i) => {
      s.value = st.levels[i] ?? '';
      s.style.display = i === 0 || st.levels[i - 1] ? '' : 'none';
    });
    const uf = st.levels.some((l) => l.startsWith('UF'));
    mapRow.style.display = uf ? '' : 'none';
    mapReset.style.display = hasCustomMapping() ? '' : 'none';
  };

  const hasCustomMapping = (): boolean => {
    try {
      return !!localStorage.getItem(UF_KEY);
    } catch {
      return false;
    }
  };

  const savedName = (key: string): string => {
    const names: string[] = [];
    const find = (n: TreeNode): boolean => {
      names.push(n.label);
      if (n.key === key) return true;
      for (const c of n.children) if (find(c)) return true;
      names.pop();
      return false;
    };
    for (const r of shown) if (find(r)) break;
    return names.join(' > ') || 'Classification';
  };

  const doSave = (n: TreeNode): void => {
    const name = savedName(n.key);
    if (n.query) host.saveQuery(n.query, name);
    else {
      const msg = host.saveIds(name, n.ids);
      note.textContent = `${msg} This node has no query, so the set holds its elements.`;
    }
  };

  const paintNote = (): void => {
    const m = host.model();
    if (!m) {
      note.textContent = '';
      return;
    }
    const withData = allInfos.filter((i) => Object.keys(i.facets).length > 0 || i.discipline).length;
    const rv = allInfos.filter(needsReview).length;
    note.textContent =
      withData === 0
        ? 'Nothing is classified yet. Run Classify (with the facets on) in the Classification tab to fill this tree.'
        : `${withData} of ${allInfos.length} elements classified, ${rv} need review.`;
  };

  const rebuild = (reset: boolean): void => {
    if (st.mode !== 'class') return;
    const m = host.model();
    if (!m) return;
    const src = host.source();
    const q = filterQ.trim().toLowerCase();
    const list = q ? allInfos.filter((i) => matchesElement({ name: i.name, globalId: i.globalId, ifcClass: i.ifcClass } as never, q)) : allInfos;
    const cols = src?.columns?.();
    const order = src?.order?.() ?? {};
    const roots = buildClassTree(list, { levels: st.levels, uniformat: uniformatTable(), columns: cols, order });
    shown = roots;
    // Expand the top level (or everything while filtering) on a new grouping; keep the expansion on a data refresh.
    let expand: Set<string> | undefined;
    if (reset || !tree.showsClassification) {
      expand = topKeys(roots);
      if (q) {
        expand = new Set();
        const walk = (n: TreeNode): void => {
          if (n.children.length === 0) return;
          expand!.add(n.key);
          n.children.forEach(walk);
        };
        roots.forEach(walk);
      }
    }
    tree.setRoots(roots, expand);
    paintNote();
  };

  const collect = (): void => {
    const m = host.model();
    allInfos = m ? collectClassInfos(m, host.source()) : [];
  };

  const setMode = (mode: 'model' | 'class'): void => {
    if (st.mode === mode) return;
    st.mode = mode;
    writeState(st);
    syncControls();
    if (mode === 'class') {
      collect();
      rebuild(true);
    } else {
      tree.setRoots(null);
      shown = [];
    }
    host.modeChanged();
  };

  const setLevels = (levels: string[]): void => {
    const l = levels.filter(Boolean).slice(0, MAX_LEVELS);
    if (l.length === 0) return;
    st.levels = l;
    const p = PRESETS.find((x: ClassPreset) => sameLevels(x.levels, l));
    st.preset = p ? p.id : 'custom';
    writeState(st);
    syncControls();
    rebuild(true);
  };

  bModel.addEventListener('click', () => setMode('model'));
  bClass.addEventListener('click', () => setMode('class'));
  presetSel.addEventListener('change', () => {
    const p = PRESETS.find((x) => x.id === presetSel.value);
    if (p) setLevels(p.levels.slice());
    else {
      st.preset = 'custom';
      writeState(st);
      syncControls();
    }
  });
  levelSels.forEach((s) =>
    s.addEventListener('change', () => {
      const next: string[] = [];
      for (const x of levelSels) {
        if (!x.value) break;
        next.push(x.value);
      }
      // A level chosen after an empty one is dropped; the first level is never empty.
      setLevels(next);
    }),
  );
  mapBtn.addEventListener('click', () => mapFile.click());
  mapFile.addEventListener('change', () => {
    const f = mapFile.files?.[0];
    mapFile.value = '';
    if (!f) return;
    void f.text().then((txt) => {
      let json: unknown;
      try {
        json = JSON.parse(txt);
      } catch {
        note.textContent = 'The file is not valid JSON.';
        return;
      }
      const r = parseUniformat(json);
      if (!r.table) {
        note.textContent = `Mapping not used: ${r.errors[0] ?? 'unknown problem'}`;
        return;
      }
      try {
        localStorage.setItem(UF_KEY, txt);
      } catch {
        /* the mapping is used for this page only */
      }
      syncControls();
      rebuild(true);
      note.textContent = `Mapping loaded: ${r.table.title}, ${r.table.rules.length} rules.`;
    });
  });
  mapReset.addEventListener('click', () => {
    try {
      localStorage.removeItem(UF_KEY);
    } catch {
      /* ignore */
    }
    syncControls();
    rebuild(true);
  });

  syncControls();

  return {
    root,
    get active() {
      return st.mode === 'class';
    },
    state: () => ({ ...st, levels: st.levels.slice() }),
    setMode,
    setLevels,
    refresh(o) {
      if (o?.reset) filterQ = '';
      if (st.mode !== 'class') return;
      collect();
      rebuild(o?.reset === true);
    },
    setFilter(q) {
      filterQ = q;
      rebuild(true);
    },
    save: doSave,
    roots: () => shown,
  };
}
