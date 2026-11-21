// The block of new lines (design 1.1, 1.4 to 1.6). Pure text: same state in, same bytes out.

import { overallConfidence } from '../classify/review';
import { propertyNames, schemaHash } from '../classify/schema';
import type { ClassificationSchema, ClassifyResult, SchemaSystemMeta } from '../classify/types';
import { classificationLine, classificationReferenceLine, dateType, ownerHistoryChain, propertySetLine, propertySingleValueLine, relAssociatesClassificationLine, relDefinesByPropertiesLine } from './families';
import type { PropSpec, SchemaFamily } from './families';
import { xrayGuid } from './ifcGuid';
import { XRAY_DEFAULTS } from './plan';
import { emitWorkSchedule, workScheduleSupported } from './workSchedule';
import type { ElementSave, FileSavePlan, SaveOptions } from './plan';

export const BLOCK_FORMAT = 'xray-ifc-additions/1';
export const MARKER_BEGIN = 'XRAY-BEGIN';
export const MARKER_END = 'XRAY-END';

// ---------------------------------------------------------------- classification references

export type SystemKey = 'discipline' | 'masterformat';

export interface RefSpec {
  system: SystemKey;
  /** The identification as written (IFC2X3 sub-disciplines and sections are dotted or spaced so they stay unique). */
  code: string;
  label: string;
  parent?: RefSpec;
}

/** The references of one result: the most specific one per system (sub-discipline over discipline, section over division). */
export function referencesOf(r: ClassifyResult, family: SchemaFamily): RefSpec[] {
  const out: RefSpec[] = [];
  const disc: RefSpec = { system: 'discipline', code: r.discipline.code, label: r.discipline.label };
  if (r.subDiscipline) out.push({ system: 'discipline', code: family === '2x3' ? `${r.discipline.code}.${r.subDiscipline.code}` : r.subDiscipline.code, label: r.subDiscipline.label, parent: disc });
  else out.push(disc);
  const m = r.masterformat;
  if (m && m.division) {
    const div: RefSpec = { system: 'masterformat', code: m.division, label: m.title };
    out.push(m.section ? { system: 'masterformat', code: m.section, label: m.title, parent: div } : div);
  }
  return out;
}

export function systemMeta(schema: ClassificationSchema, system: SystemKey): Required<Pick<SchemaSystemMeta, 'name' | 'source' | 'edition'>> & Pick<SchemaSystemMeta, 'editionDate' | 'location'> {
  const given = schema.systems?.[system];
  if (system === 'discipline') {
    return {
      name: given?.name ?? schema.codeList ?? schema.title,
      source: given?.source ?? XRAY_DEFAULTS.disciplineSystemSource,
      edition: given?.edition ?? schema.edition ?? schema.version ?? 'unspecified',
      ...(given?.editionDate ? { editionDate: given.editionDate } : {}),
      ...(given?.location ? { location: given.location } : {}),
    };
  }
  return {
    name: given?.name ?? XRAY_DEFAULTS.divisionSystemName,
    source: given?.source ?? XRAY_DEFAULTS.divisionSystemSource,
    edition: given?.edition ?? schema.masterformat.edition ?? 'unspecified',
    ...(given?.editionDate ? { editionDate: given.editionDate } : {}),
    ...(given?.location ? { location: given.location } : {}),
  };
}

// ---------------------------------------------------------------- properties

const round2 = (x: number): number => Math.round(x * 100) / 100;

export interface ElementProps {
  /** The classification output set (`schema.psetName`). */
  classification: PropSpec[];
  /** `Xray_Review`. */
  review: PropSpec[];
  /** `Xray_Cleanup`. */
  cleanup: PropSpec[];
  /** `Xray_4D`: Location, Trade, Zone, ActivityIds. */
  fourD: PropSpec[];
}

const hashCache = new WeakMap<ClassificationSchema, string>();
/** `schemaHash` walks the whole schema: once per schema object, not once per element (100k elements cost seconds otherwise). */
const schemaHashOf = (schema: ClassificationSchema): string => {
  let h = hashCache.get(schema);
  if (h === undefined) hashCache.set(schema, (h = schemaHash(schema)));
  return h;
};

/** The properties of one element, in the fixed order of the design. Empty values are left out. */
export function elementProps(e: ElementSave, schema: ClassificationSchema, family: SchemaFamily, o: SaveOptions): ElementProps {
  const out: ElementProps = { classification: [], review: [], cleanup: [], fourD: [] };
  const r = e.result;
  if (r) {
    const n = propertyNames(schema);
    const c = out.classification;
    const put = (name: string, type: PropSpec['type'], value: string | number | boolean | undefined): void => {
      if (value === undefined || value === '') return;
      c.push({ name, type, value });
    };
    put(n.discipline, 'IfcLabel', r.discipline.code);
    put(n.subDiscipline, 'IfcLabel', r.subDiscipline?.code);
    put(n.masterformatDivision, 'IfcLabel', r.masterformat?.division);
    put(n.masterformatTitle, 'IfcLabel', r.masterformat?.title);
    put(n.masterformatSection, 'IfcLabel', r.masterformat?.section);
    put(n.confidence, 'IfcNormalisedRatioMeasure', overallConfidence(r));
    put(n.source, 'IfcLabel', r.source);
    put(n.model, 'IfcLabel', r.model);
    put(n.needsReview, 'IfcBoolean', r.needsReview);

    const v = out.review;
    const add = (name: string, type: PropSpec['type'], value: string | number | boolean | undefined): void => {
      if (value === undefined || value === '') return;
      v.push({ name, type, value });
    };
    add('Status', 'IfcLabel', r.source === 'confirmed' || r.source === 'corrected' || r.source === 'manual' ? r.source : 'unreviewed');
    add('Unsure', 'IfcBoolean', r.unsure === true);
    add('NeedsReview', 'IfcBoolean', r.needsReview);
    add('Confidence', 'IfcNormalisedRatioMeasure', overallConfidence(r));
    add('DisciplineConfidence', 'IfcNormalisedRatioMeasure', round2(r.discipline.confidence));
    add('SubDisciplineConfidence', 'IfcNormalisedRatioMeasure', r.subDiscipline ? round2(r.subDiscipline.confidence) : undefined);
    add('DivisionConfidence', 'IfcNormalisedRatioMeasure', r.masterformat ? round2(r.masterformat.confidence) : undefined);
    add('BuildingElementProbability', 'IfcNormalisedRatioMeasure', round2(r.buildingElement));
    add('ProposedBy', 'IfcLabel', r.source === 'rules' || r.rationale ? 'rules' : r.model ? r.model : r.source === 'manual' ? 'manual' : undefined);
    add('Rationale', 'IfcText', r.rationale);
    add('ReviewedAt', dateType(family), r.confirmedAt ? isoDateTime(r.confirmedAt) : undefined);
    add('CommitId', 'IfcIdentifier', r.commitId);
    add('SchemaHash', 'IfcIdentifier', schemaHashOf(schema));
    if (e.revision) {
      add('RevisionStatus', 'IfcLabel', e.revision.status);
      add('RevisionBaseline', 'IfcLabel', e.revision.baseline);
    }
    if (o.includeReviewers) {
      add('ReviewedBy', 'IfcLabel', r.confirmedBy);
      add('Comment', 'IfcText', e.comment);
    }
  }
  if (e.cleanup && o.includeCleanupMarks) {
    out.cleanup.push({ name: 'FlaggedForRemoval', type: 'IfcBoolean', value: true });
    if (e.cleanup.rules.length) out.cleanup.push({ name: 'Rules', type: 'IfcLabel', value: e.cleanup.rules.join(';') });
    if (e.cleanup.reasons.length) out.cleanup.push({ name: 'Reason', type: 'IfcText', value: e.cleanup.reasons.join('; ') });
    if (e.cleanup.keptBecause) out.cleanup.push({ name: 'KeptBecause', type: 'IfcLabel', value: e.cleanup.keptBecause });
  }
  if (e.fourD && o.includeFourD) {
    const f = e.fourD;
    for (const [name, v] of [['Location', f.location], ['Trade', f.trade], ['Zone', f.zone]] as const) if (v) out.fourD.push({ name, type: 'IfcLabel', value: v });
    if (f.activityIds) out.fourD.push({ name: 'ActivityIds', type: 'IfcText', value: f.activityIds });
  }
  return out;
}

/** An ISO timestamp without fractional seconds. */
function isoDateTime(s: string): string {
  return s.replace(/(\d\d:\d\d:\d\d)\.\d+/, '$1');
}

// ---------------------------------------------------------------- the block

export interface Additions {
  text: string;
  /** Entity lines, not counting the two marker comments. */
  lines: number;
  /** Highest express id used (the plan's base when nothing was written). */
  lastId: number;
}

const refRank = (r: RefSpec): number => (r.system === 'discipline' ? (r.parent ? 1 : 0) : r.parent ? 3 : 2);
const sysName = (r: RefSpec): string => r.system;

const sameEdition = (a: string | null, b: string): boolean => !a || !b || b === 'unspecified' || a.toLowerCase() === b.toLowerCase();

/** Lines of the block, then the block with its markers. With nothing to write the text is empty (which removes an old block). */
export function emitAdditions(plan: FileSavePlan, schema: ClassificationSchema, o: SaveOptions, note?: string): Additions {
  const f = plan.family;
  const lines: string[] = [];
  let next = plan.preserved ? Math.max(plan.base, plan.preserved.lastId) : plan.base;
  const alloc = (): number => ++next;

  // ---- collect references
  interface RefUse {
    spec: RefSpec;
    members: number[];
  }
  const refs = new Map<string, RefUse>();
  const touch = (spec: RefSpec, member: number | null): void => {
    const key = `${sysName(spec)}|${spec.code}`;
    let u = refs.get(key);
    if (!u) refs.set(key, (u = { spec, members: [] }));
    if (member !== null) u.members.push(member);
    if (spec.parent) touch(spec.parent, null);
  };
  const props = new Map<number, ElementProps>();
  for (const e of plan.elements) {
    if (e.result) for (const spec of referencesOf(e.result, f)) touch(spec, e.expressId);
    props.set(e.expressId, elementProps(e, schema, f, o));
  }
  const orderedRefs = [...refs.values()].sort((a, b) => refRank(a.spec) - refRank(b.spec) || a.spec.code.localeCompare(b.spec.code, 'en'));

  // ---- property set groups (identical property tuples share one set and one relation)
  interface Group {
    setName: string;
    props: PropSpec[];
    members: ElementSave[];
  }
  const kinds: Array<{ kind: keyof ElementProps; setName: string }> = [
    { kind: 'classification', setName: schema.psetName },
    { kind: 'review', setName: XRAY_DEFAULTS.psetReview },
    { kind: 'cleanup', setName: XRAY_DEFAULTS.psetCleanup },
    { kind: 'fourD', setName: XRAY_DEFAULTS.psetFourD },
  ];
  const groups: Group[] = [];
  for (const { kind, setName } of kinds) {
    const m = new Map<string, Group>();
    for (const e of plan.elements) {
      const ps = props.get(e.expressId)![kind];
      if (!ps.length) continue;
      const key = ps.map(propKey).join('\n');
      let g = m.get(key);
      if (!g) m.set(key, (g = { setName, props: ps, members: [] }));
      g.members.push(e);
    }
    groups.push(...m.values());
  }

  const work = plan.workSchedule && workScheduleSupported(f) && plan.workSchedule.tasks.length > 0 ? plan.workSchedule : null;
  if (!orderedRefs.length && !groups.length && !note && !work && !plan.preserved?.lines.length) return { text: '', lines: 0, lastId: plan.base };

  if (plan.preserved) lines.push(...plan.preserved.lines);

  // ---- owner history
  let owner: number | null = plan.ownerHistoryId;
  if (f === '2x3' && owner === null) {
    const first = next + 1;
    next += 5;
    lines.push(...ownerHistoryChain(first, o.toolVersion ?? 'dev'));
    owner = first + 4;
  }

  // ---- classifications
  const classId = new Map<SystemKey, number>();
  for (const system of ['discipline', 'masterformat'] as const) {
    if (!orderedRefs.some((r) => r.spec.system === system)) continue;
    const meta = systemMeta(schema, system);
    const existing = plan.existingClassifications.find((c) => c.name.toLowerCase() === meta.name.toLowerCase() && sameEdition(c.edition, meta.edition));
    if (existing) {
      classId.set(system, existing.id);
      continue;
    }
    const id = alloc();
    classId.set(system, id);
    lines.push(classificationLine(f, id, { source: meta.source, edition: meta.edition, ...(meta.editionDate ? { editionDate: meta.editionDate } : {}), name: meta.name, ...(meta.location ? { location: meta.location } : {}) }));
  }

  // ---- references, then one association per reference
  const refId = new Map<string, number>();
  for (const u of orderedRefs) {
    const id = alloc();
    refId.set(`${sysName(u.spec)}|${u.spec.code}`, id);
    const parent = u.spec.parent ? refId.get(`${sysName(u.spec.parent)}|${u.spec.parent.code}`)! : null;
    lines.push(classificationReferenceLine(f, id, u.spec.code, u.spec.label, classId.get(u.spec.system)!, parent));
  }
  for (const u of orderedRefs) {
    if (!u.members.length) continue;
    const id = alloc();
    const guid = xrayGuid('assoc', `${systemMeta(schema, u.spec.system).name}|${u.spec.code}`);
    lines.push(relAssociatesClassificationLine(f, id, guid, owner, XRAY_DEFAULTS.relClassificationName, [...new Set(u.members)].sort((a, b) => a - b), refId.get(`${sysName(u.spec)}|${u.spec.code}`)!));
  }

  // ---- pooled single values, then sets and relations
  const pool = new Map<string, number>();
  for (const g of groups)
    for (const p of g.props) {
      const k = propKey(p);
      if (!pool.has(k)) {
        const id = alloc();
        pool.set(k, id);
        lines.push(propertySingleValueLine(id, p));
      }
    }
  for (const g of groups) {
    const sortedGuids = g.members.map((m) => m.globalId).sort().join(',');
    const psetId = alloc();
    lines.push(propertySetLine(f, psetId, xrayGuid('pset', `${g.setName}|${sortedGuids}`), owner, g.setName, g.props.map((p) => pool.get(propKey(p))!)));
    const relId = alloc();
    lines.push(relDefinesByPropertiesLine(f, relId, xrayGuid('reldef', `${g.setName}|${sortedGuids}`), owner, XRAY_DEFAULTS.relPropertiesName, g.members.map((m) => m.expressId), psetId));
  }

  // ---- the 4D work schedule: the last section, between its own markers so a later write can replace just this part
  if (work) {
    const w = emitWorkSchedule(work, next + 1);
    lines.push(...w.lines);
    next = w.lastId;
  }

  // ---- markers
  const tool = `xray-viewer/${(o.toolVersion ?? 'dev').replace(/[^A-Za-z0-9._+-]/g, '_')}`;
  const begin = `/* ${MARKER_BEGIN} ${BLOCK_FORMAT} base=${plan.base} lines=${entityCount(lines)} tool=${tool}${note ? ` ${note.replace(/[^A-Za-z0-9._=+ -]/g, '_')}` : ''} */\n`;
  const body = begin + lines.map((l) => l + '\n').join('');
  const bytes = body.length; // ASCII only: every non-ASCII character is escaped in the lines
  return { text: `${body}/* ${MARKER_END} bytes=${bytes} */\n`, lines: entityCount(lines), lastId: next };
}

const entityCount = (ls: readonly string[]): number => ls.reduce((n, l) => n + (l.startsWith('#') ? 1 : 0), 0);

/** Identity of a property (name, type, value). Cheaper than the step text; the text is built once per distinct property. */
const propKey = (p: PropSpec): string => `${p.name}|${p.type}|${p.value}`;
