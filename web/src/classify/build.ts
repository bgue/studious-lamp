// Build the classifier input of an element from the viewer's model: the flat property list (`Pset.Prop` keys), the storey, the
// systems and the host elements. No DOM. A model that the viewer loaded has no site or building objects, so the
// hierarchy path holds the storey (and the assembly when there is one).

import type { ElementId, ElementRecord, SceneModel } from '../types';
import { isProcessModel, processEvidenceOf } from './rules';
import type { ClassifyInput, PsetRecord, PsetValue, RelatedElement } from './types';

const QTO = /^(Qto_|BaseQuantities$)/;

/** Split flat `Set.Prop` keys into property sets and quantity sets. */
export function splitProps(props: Record<string, string | number | boolean> | undefined): { psets: PsetRecord; quantities: PsetRecord } {
  const psets: PsetRecord = {};
  const quantities: PsetRecord = {};
  if (props) {
    for (const [key, v] of Object.entries(props)) {
      const dot = key.indexOf('.');
      if (dot <= 0) continue;
      const set = key.slice(0, dot);
      const target = QTO.test(set) ? quantities : psets;
      (target[set] ??= {})[key.slice(dot + 1)] = v as PsetValue;
    }
  }
  return { psets, quantities };
}

interface Index {
  systems: Map<ElementId, string[]>;
  hosts: Map<ElementId, ElementId[]>;
  storeys: Map<number, string>;
  /** True when the model as a whole shows a process context (rules.ts, isProcessModel). */
  process: boolean;
}
const indexes = new WeakMap<SceneModel, Index>();

function indexOf(model: SceneModel): Index {
  let ix = indexes.get(model);
  if (ix) return ix;
  ix = { systems: new Map(), hosts: new Map(), storeys: new Map(model.storeys.map((s) => [s.id, s.name])), process: false };
  for (const s of model.relations.systems) for (const id of s.elements) (ix.systems.get(id) ?? ix.systems.set(id, []).get(id)!).push(s.name);
  for (const [filler, host] of model.relations.hosts) (ix.hosts.get(filler) ?? ix.hosts.set(filler, []).get(filler)!).push(host);
  const evidence = model.elements.map((e) => processEvidenceOf({ id: e.globalId, ifcClass: e.ifcClass, name: e.name ?? '', psets: splitProps(e.props).psets, systems: ix!.systems.get(e.id) }));
  ix.process = isProcessModel(evidence);
  indexes.set(model, ix);
  return ix;
}

const related = (e: ElementRecord, cls = e.ifcClass): RelatedElement => ({ ifcClass: cls, name: e.name ?? '', psets: splitProps(e.props).psets });

/** The classifier input of one element. Null for an id that the model does not have. */
export function buildInput(model: SceneModel, idOrGlobalId: ElementId | string): ClassifyInput | null {
  const id = typeof idOrGlobalId === 'string' ? model.byGlobalId.get(idOrGlobalId) : idOrGlobalId;
  const e = id === undefined ? undefined : model.elements[id];
  if (!e || id === undefined) return null;
  const ix = indexOf(model);
  const { psets, quantities } = splitProps(e.props);
  const objectType = psets['Attr']?.['ObjectType'];
  const out: ClassifyInput = { id: e.globalId, ifcClass: e.ifcClass, name: e.name ?? '', psets };
  if (Object.keys(quantities).length) out.quantities = quantities;
  if (typeof objectType === 'string' && objectType) out.type = { ifcClass: `${e.ifcClass}Type`, name: objectType, psets: {} };
  const path: NonNullable<ClassifyInput['hierarchy']>['path'] = [];
  const storey = e.storey === null ? undefined : ix.storeys.get(e.storey);
  if (storey !== undefined) path.push({ ifcClass: 'IfcBuildingStorey', name: storey, globalId: `storey:${e.storey}` });
  const hostIds = ix.hosts.get(id) ?? [];
  const parents = hostIds.map((h) => model.elements[h]).filter((h): h is ElementRecord => !!h).slice(0, 4).map((h) => related(h));
  if (path.length || parents.length) out.hierarchy = { path, ...(parents.length ? { parents } : {}) };
  const systems = ix.systems.get(id);
  if (systems?.length) out.systems = systems;
  if (e.material) out.material = e.material;
  if (ix.process) out.processContext = true;
  return out;
}

export function buildInputs(model: SceneModel, ids?: Iterable<ElementId>): ClassifyInput[] {
  const list = ids ?? model.elements.map((e) => e.id);
  const out: ClassifyInput[] = [];
  for (const id of list) {
    const i = buildInput(model, id);
    if (i) out.push(i);
  }
  return out;
}
