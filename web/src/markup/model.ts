// Markup data model: markup sets (one saved view and its markups), comments, and the `xray-markup-set/1` JSON document
// (read, validate, write, model identity). Pure: no DOM, no three.js. Tested in tests/markup-model.test.ts.
//
// Positions follow the BCF side file (src/bcf/sidecar.ts): 3D anchors are IFC project coordinates (metres, Z up) with an
// optional element GlobalId and offset, so they follow elements and survive a re-conversion of the model; shapes are
// points as fractions of the view of the set's camera on a plane `depth` metres along the view direction. A shape also has
// an `attach` (src/bcf/attach.ts): what it is bound to in 3D (elements, surface, measurement, penetration, region) or
// `none` (view-locked); the fractions stay as the view-locked form.

import { sanitizeView } from '../views/model';
import type { SavedView } from '../views/model';
import type { BcfAnchor, BcfMeasureLink, BcfShape, BcfSnapshotView, Vec3 } from '../bcf/model';
import { attachGuids, attachmentOfAnchor, cleanAttachment } from '../bcf/attach';
import type { Attachment } from '../bcf/attach';

export type { Vec3 } from '../bcf/model';

export const MARKUP_SCHEMA = 'xray-markup-set/1';
const SCHEMA_PREFIX = 'xray-markup-set/';

/** Shapes drawn on the view (points are fractions) and markups anchored in 3D. */
export const SHAPE_KINDS = ['cloud', 'rect', 'ellipse', 'line', 'arrow', 'polyline', 'polygon', 'highlight', 'highlightBox', 'pen'] as const;
export const ANCHOR_KINDS = ['text', 'callout', 'pointer', 'measure'] as const;
export type ShapeKind = (typeof SHAPE_KINDS)[number];
export type AnchorKind = (typeof ANCHOR_KINDS)[number];
export type MarkupKind = ShapeKind | AnchorKind;
export const MARKUP_KINDS: readonly MarkupKind[] = [...SHAPE_KINDS, ...ANCHOR_KINDS];

export function isShapeKind(k: string): k is ShapeKind {
  return (SHAPE_KINDS as readonly string[]).includes(k);
}
export function isAnchorKind(k: string): k is AnchorKind {
  return (ANCHOR_KINDS as readonly string[]).includes(k);
}
/** Kinds drawn from 2 opposite corners. */
export function isBoxKind(k: MarkupKind): boolean {
  return k === 'rect' || k === 'ellipse' || k === 'highlightBox';
}

export const KIND_LABEL: Record<MarkupKind, string> = {
  cloud: 'Cloud', rect: 'Rectangle', ellipse: 'Ellipse', line: 'Line', arrow: 'Arrow', polyline: 'Polyline', polygon: 'Polygon',
  highlight: 'Highlight', highlightBox: 'Highlight box', pen: 'Pen', text: 'Text', callout: 'Callout', pointer: 'Pointer', measure: 'Measurement',
};

export const COLOURS = {
  red: '#e5262b',
  yellow: '#ffd400',
  blue: '#1f6fe5',
  green: '#1e9e4a',
  black: '#111111',
} as const;
export type ColourKey = keyof typeof COLOURS;
export const COLOUR_KEYS = Object.keys(COLOURS) as ColourKey[];

/** Default colour per kind: red clouds, yellow highlights, red for the rest. */
export function defaultColour(k: MarkupKind): ColourKey {
  return k === 'highlight' || k === 'highlightBox' ? 'yellow' : 'red';
}

export type Weight = 1 | 2 | 3 | 4;
/** Stroke width in CSS pixels per weight; highlights are wide markers. */
export function strokePx(kind: MarkupKind, w: Weight): number {
  const base = [1.5, 2.5, 4, 6][w - 1]!;
  return kind === 'highlight' ? base * 5 : base;
}

export type MarkupStatus = 'open' | 'resolved';

export interface MarkupComment {
  id: string;
  author: string;
  /** ISO time. */
  date: string;
  text: string;
}

export interface Markup {
  id: string;
  /** Stable number on the sheet: the next free number when it was made; never reused inside a set. */
  number: number;
  kind: MarkupKind;
  colour: ColourKey;
  weight: Weight;
  /** Shapes with an inside: translucent fill. */
  fill: boolean;
  /** The label, or the text of a text box, callout, pointer. */
  text: string;
  /** Shape kinds. */
  shape?: BcfShape;
  /**
   * Shape kinds: what the shape is attached to in 3D, or `{ kind: 'none' }` for view-locked. Absent in documents from before
   * attachments (the viewer then tries to attach the shape when the document is opened). `shape` stays: it is the view-locked
   * form, and what the 2D view and the PDF burn-in fall back on.
   */
  attach?: Attachment;
  /** Anchor kinds: 3D anchor in IFC coordinates, and the box offset (fractions of the view height). */
  anchor?: BcfAnchor;
  offset?: [number, number];
  status: MarkupStatus;
  assignee?: string;
  /** Due date, YYYY-MM-DD. */
  due?: string;
  author: string;
  created: string;
  modified?: string;
  comments: MarkupComment[];
}

export interface MarkupSet {
  id: string;
  title: string;
  author: string;
  created: string;
  updated: string;
  /** The saved view: camera, section, hidden and coloured elements, selection, preset, render style (no thumbnail). */
  view: SavedView;
  /** The camera of the view in the IFC frame, with the aspect of the window it was made in: the base of the shapes. */
  camera: BcfSnapshotView;
  markups: Markup[];
  nextNumber: number;
  /** data:image/jpeg thumbnail. */
  thumb?: string;
  /**
   * The model the set was made on (see scope.ts). Absent or null: unknown (a file that names no model); the set is then shown
   * on any model, tagged "model unknown". Sets of another model are hidden while a different model is loaded.
   */
  model?: ModelIdentity | null;
  /** The one-line note of the sketch (src/issues). Sketches have no status and no comment thread. */
  note?: string;
  /**
   * The issue (BCF topic) this sketch is a viewpoint of: topic guid and viewpoint guid. One sketch belongs to at most one issue.
   * The topic's viewpoint holds the same link as `sketchId`; src/issues/link.ts keeps both sides in step.
   */
  issue?: { topic: string; viewpoint: string };
  /**
   * Made from a BCF viewpoint (an imported topic): restoring the sketch applies that viewpoint instead of `view`, which only
   * holds its camera.
   */
  fromViewpoint?: boolean;
}

export interface ModelIdentity {
  name: string;
  elementCount: number;
  /** GlobalIds in the model (elements that have one). */
  guidCount: number;
  /** Hash of the sorted GlobalId list (see globalIdHash). */
  guidHash: string;
}

export interface MarkupDoc {
  schema: typeof MARKUP_SCHEMA;
  generator: string;
  exportedAt: string;
  /** Plain words on how to get back to the marked-up view. */
  instructions: string;
  model: ModelIdentity;
  /** A share link of the first set's view when it fits (http or https pages only). */
  link?: string;
  sets: MarkupSet[];
}

export const INSTRUCTIONS =
  'To get back to this marked-up view: open the same model in the X-ray viewer, then drop this file, or the PDF that carries it, onto the viewer window. ' +
  'You can also open the Markup tool and press Open file. The viewer restores the camera, the section, the hidden and coloured elements and the markups. ' +
  'The model.name, model.elementCount and model.guidHash fields say which model the markup was made on. A different model shows a warning and restores what it can.';

// ---------------------------------------------------------------- ids, hash, time

let idSeq = 0;
export function newMarkupId(prefix = 'm'): string {
  idSeq = (idSeq + 1) % 1e6;
  return `${prefix}${Date.now().toString(36)}${Math.floor(Math.random() * 36 ** 4).toString(36).padStart(4, '0')}${idSeq.toString(36)}`;
}

/**
 * A 64 bit hash (16 hex digits, two FNV-1a runs with different seeds) of the sorted, de-duplicated GlobalId list. It says
 * whether two files hold the same elements, whatever order they list them in.
 */
export function globalIdHash(ids: Iterable<string>): string {
  const sorted = [...new Set(ids)].sort();
  let h1 = 0x811c9dc5;
  let h2 = (0x01000193 ^ 0xdeadbeef) >>> 0;
  const feed = (c: number): void => {
    h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0;
    h2 = Math.imul(h2 ^ c, 0x01000193) >>> 0;
    h2 = (h2 + 0x9e3779b9) >>> 0;
  };
  for (const id of sorted) {
    for (let i = 0; i < id.length; i++) feed(id.charCodeAt(i) & 0xff);
    feed(10);
  }
  return h1.toString(16).padStart(8, '0') + h2.toString(16).padStart(8, '0');
}

export function modelIdentity(name: string, elementCount: number, globalIds: readonly string[]): ModelIdentity {
  const uniq = new Set(globalIds);
  return { name, elementCount, guidCount: uniq.size, guidHash: globalIdHash(uniq) };
}

export type ModelMatch = 'same' | 'revised' | 'different' | 'unknown';

/** How the model a document was made on compares with the loaded one. */
export function compareModels(doc: ModelIdentity | undefined, now: ModelIdentity): { match: ModelMatch; message: string } {
  if (!doc) return { match: 'unknown', message: 'The file does not name its model.' };
  if (doc.guidHash === now.guidHash && doc.elementCount === now.elementCount) return { match: 'same', message: '' };
  const sameName = doc.name.trim().toLowerCase() === now.name.trim().toLowerCase();
  const detail = `made on "${doc.name}" (${doc.elementCount} elements), this model is "${now.name}" (${now.elementCount} elements)`;
  if (sameName) return { match: 'revised', message: `The model has changed since the markup was made: ${detail}. Elements that moved or were removed may not match.` };
  return { match: 'different', message: `This markup was ${detail}. It restores what it can; positions may not fit.` };
}

export function nowIso(): string {
  return new Date().toISOString();
}

// ---------------------------------------------------------------- creating

export function newMarkup(kind: MarkupKind, o: Partial<Markup> & { author: string }): Markup {
  const now = nowIso();
  const m: Markup = {
    id: o.id ?? newMarkupId(),
    number: o.number ?? 0,
    kind,
    colour: o.colour ?? defaultColour(kind),
    weight: o.weight ?? 2,
    fill: o.fill ?? false,
    text: o.text ?? '',
    status: o.status ?? 'open',
    author: o.author,
    created: o.created ?? now,
    comments: o.comments ?? [],
  };
  if (o.shape) m.shape = o.shape;
  if (o.attach) m.attach = o.attach;
  if (o.anchor) m.anchor = o.anchor;
  if (o.offset) m.offset = o.offset;
  if (o.assignee) m.assignee = o.assignee;
  if (o.due) m.due = o.due;
  if (o.modified) m.modified = o.modified;
  return m;
}

/** Add a markup to a set, numbering it with the next free number. */
export function addMarkup(set: MarkupSet, m: Markup): Markup {
  const used = set.markups.reduce((a, x) => Math.max(a, x.number), 0);
  m.number = Math.max(set.nextNumber, used + 1);
  set.nextNumber = m.number + 1;
  set.markups.push(m);
  set.updated = nowIso();
  return m;
}

export function addComment(m: Markup, author: string, text: string, date = nowIso()): MarkupComment {
  const c: MarkupComment = { id: newMarkupId('c'), author: author.trim() || 'unknown', date, text: text.trim() };
  m.comments.push(c);
  m.modified = date;
  return c;
}

export function cloneSet(s: MarkupSet): MarkupSet {
  return JSON.parse(JSON.stringify(s)) as MarkupSet;
}

/**
 * Legacy review data on a sketch: markups with a comment thread, a resolved status, an assignee or a due date. Sketches no
 * longer carry these; they stay in the data, read-only, until the set is raised as an issue (src/issues/link.ts).
 */
export function hasLegacyReview(s: MarkupSet): boolean {
  return s.markups.some((m) => m.comments.length > 0 || m.status === 'resolved' || !!m.assignee || !!m.due);
}

/** The markup counts of a set: open and resolved. */
export function setCounts(s: MarkupSet): { total: number; open: number; resolved: number } {
  const resolved = s.markups.filter((m) => m.status === 'resolved').length;
  return { total: s.markups.length, open: s.markups.length - resolved, resolved };
}

// ---------------------------------------------------------------- GlobalIds referenced

/** Every element GlobalId a set refers to: anchors, linked measurements, and the saved view's selection, hides and pins. */
export function referencedGuids(s: MarkupSet): string[] {
  const out = new Set<string>();
  for (const m of s.markups) {
    if (m.anchor?.elementGuid) out.add(m.anchor.elementGuid);
    for (const g of m.anchor?.measurement?.elementGuids ?? []) out.add(g);
    for (const g of attachGuids(m.attach)) out.add(g);
  }
  for (const g of s.view.selection) out.add(g);
  for (const g of s.view.hides?.ids ?? []) out.add(g);
  for (const g of s.view.pins ?? []) out.add(g);
  return [...out];
}

/** The GlobalIds of a set that `has` rejects (each once). */
export function unknownGuids(s: MarkupSet, has: (g: string) => boolean): string[] {
  return referencedGuids(s).filter((g) => !has(g));
}

/** The attachment of a markup: a shape's own (absent: view-locked), an anchor kind's anchor mapped 1:1. */
export function attachmentOf(m: Markup): Attachment {
  if (m.shape) return m.attach ?? { kind: 'none' };
  return m.anchor ? attachmentOfAnchor(m.anchor) : { kind: 'none' };
}

/** A shape from a document made before attachments: it has no `attach` yet and wants a try at attaching on load. */
export function needsAttach(m: Markup): boolean {
  return !!m.shape && m.attach === undefined;
}

// ---------------------------------------------------------------- reading

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isVec3 = (v: unknown): v is Vec3 => Array.isArray(v) && v.length === 3 && v.every(isNum);
const str = (v: unknown, max = 8000): string | undefined => (typeof v === 'string' ? v.slice(0, max) : undefined);
const isoOr = (v: unknown, fallback: string): string => {
  const s = str(v, 40);
  return s && !Number.isNaN(Date.parse(s)) ? s : fallback;
};
const MAX_POINTS = 2000;

function cleanShape(v: unknown, kind: ShapeKind): BcfShape | null {
  if (!isObj(v) || !Array.isArray(v['points']) || !isNum(v['depth'])) return null;
  const pts: Array<[number, number]> = [];
  for (const p of v['points'].slice(0, MAX_POINTS)) {
    if (!Array.isArray(p) || p.length < 2 || !isNum(p[0]) || !isNum(p[1])) return null;
    pts.push([p[0], p[1]]);
  }
  if (pts.length < 2) return null;
  // Boxes hold 2 opposite corners, or 4 corners (a quad, after Update view); lines and arrows 2 points.
  if (isBoxKind(kind) && pts.length !== 2 && pts.length !== 4) return { points: [pts[0]!, pts[pts.length - 1]!], depth: v['depth'] };
  if ((kind === 'line' || kind === 'arrow') && pts.length !== 2) return { points: [pts[0]!, pts[pts.length - 1]!], depth: v['depth'] };
  return { points: pts, depth: v['depth'] };
}

function cleanMeasure(v: unknown): BcfMeasureLink | undefined {
  if (!isObj(v) || !isVec3(v['a']) || !isVec3(v['b']) || !isNum(v['distance'])) return undefined;
  const m: BcfMeasureLink = { kind: v['kind'] === 'element' ? 'element' : 'point', a: [...v['a']] as Vec3, b: [...v['b']] as Vec3, distance: v['distance'], label: str(v['label'], 60) ?? '' };
  if (Array.isArray(v['elementGuids'])) m.elementGuids = v['elementGuids'].filter((g): g is string => typeof g === 'string').slice(0, 2);
  if (isNum(v['sourceId'])) m.sourceId = v['sourceId'];
  return m;
}

function cleanAnchor(v: unknown): BcfAnchor | null {
  if (!isObj(v) || !isVec3(v['point'])) return null;
  const kind = v['kind'] === 'element' || v['kind'] === 'measurement' ? v['kind'] : 'point';
  const a: BcfAnchor = { kind, point: [...v['point']] as Vec3 };
  const g = str(v['elementGuid'], 64);
  if (g) a.elementGuid = g;
  if (isVec3(v['local'])) a.local = [...v['local']] as Vec3;
  const m = cleanMeasure(v['measurement']);
  if (m) a.measurement = m;
  return a;
}

/** One markup, cleaned; a string says why it was dropped. */
export function sanitizeMarkup(raw: unknown, fallbackAuthor = 'unknown'): Markup | string {
  if (!isObj(raw)) return 'not an object';
  const kind = raw['kind'];
  if (typeof kind !== 'string' || !(MARKUP_KINDS as readonly string[]).includes(kind)) return `unknown kind "${String(kind)}"`;
  const k = kind as MarkupKind;
  const now = nowIso();
  const colour = typeof raw['colour'] === 'string' && raw['colour'] in COLOURS ? (raw['colour'] as ColourKey) : defaultColour(k);
  const weight = raw['weight'] === 1 || raw['weight'] === 2 || raw['weight'] === 3 || raw['weight'] === 4 ? raw['weight'] : 2;
  const m: Markup = {
    id: str(raw['id'], 64) || newMarkupId(),
    number: isNum(raw['number']) && raw['number'] >= 1 ? Math.floor(raw['number']) : 0,
    kind: k,
    colour,
    weight,
    fill: raw['fill'] === true,
    text: str(raw['text']) ?? '',
    status: raw['status'] === 'resolved' ? 'resolved' : 'open',
    author: str(raw['author'], 200) || fallbackAuthor,
    created: isoOr(raw['created'], now),
    comments: [],
  };
  if (isShapeKind(k)) {
    const sh = cleanShape(raw['shape'], k);
    if (!sh) return `${k} without a usable shape`;
    m.shape = sh;
    if (raw['attach'] !== undefined) m.attach = cleanAttachment(raw['attach']) ?? { kind: 'none' };
  } else {
    const a = cleanAnchor(raw['anchor']);
    if (!a) return `${k} without an anchor`;
    if (k === 'measure' && !a.measurement) return 'measure without a measurement';
    m.anchor = a;
    const o = raw['offset'];
    m.offset = Array.isArray(o) && o.length === 2 && isNum(o[0]) && isNum(o[1]) ? [o[0], o[1]] : [0.1, -0.09];
  }
  const asg = str(raw['assignee'], 200);
  if (asg) m.assignee = asg;
  const due = str(raw['due'], 10);
  if (due && /^\d{4}-\d{2}-\d{2}$/.test(due)) m.due = due;
  const mod = str(raw['modified'], 40);
  if (mod && !Number.isNaN(Date.parse(mod))) m.modified = mod;
  if (Array.isArray(raw['comments'])) {
    for (const c of raw['comments'].slice(0, 500)) {
      if (!isObj(c)) continue;
      const text = str(c['text']);
      if (!text) continue;
      m.comments.push({ id: str(c['id'], 64) || newMarkupId('c'), author: str(c['author'], 200) || 'unknown', date: isoOr(c['date'], now), text });
    }
  }
  return m;
}

function cleanCamera(v: unknown): BcfSnapshotView | null {
  if (!isObj(v) || !isVec3(v['position']) || !isVec3(v['direction']) || !isVec3(v['up']) || !isNum(v['fov']) || !isNum(v['aspect'])) return null;
  if (v['fov'] <= 0 || v['fov'] >= 180 || v['aspect'] <= 0) return null;
  return { position: [...v['position']] as Vec3, direction: [...v['direction']] as Vec3, up: [...v['up']] as Vec3, fov: v['fov'], aspect: v['aspect'] };
}

export interface SanitizedSet {
  set: MarkupSet;
  /** Markups that were left out, with the reason. */
  bad: string[];
}

/** One set, cleaned (unknown fields dropped, ids and numbers filled in); a string says why the set was refused. */
export function sanitizeSet(raw: unknown): SanitizedSet | string {
  if (!isObj(raw)) return 'not an object';
  const title = str(raw['title'], 300)?.trim() || 'Markup';
  const view = sanitizeView(isObj(raw['view']) ? { name: title, ...raw['view'] } : null);
  if (typeof view === 'string') return `"${title}": view: ${view}`;
  delete view.thumb;
  const camera = cleanCamera(raw['camera']);
  if (!camera) return `"${title}": camera needs position, direction, up, fov and aspect`;
  const now = nowIso();
  const author = str(raw['author'], 200) || 'unknown';
  const set: MarkupSet = {
    id: str(raw['id'], 64) || newMarkupId('s'),
    title,
    author,
    created: isoOr(raw['created'], now),
    updated: isoOr(raw['updated'], isoOr(raw['created'], now)),
    view,
    camera,
    markups: [],
    nextNumber: 1,
  };
  // The model of the set: absent in older files (the document's model is used), null or unreadable: unknown.
  if ('model' in raw) set.model = cleanIdentity(raw['model']) ?? null;
  const note = str(raw['note'], 400)?.replace(/\s+/g, ' ').trim();
  if (note) set.note = note;
  if (isObj(raw['issue'])) {
    const t = str(raw['issue']['topic'], 64);
    const v = str(raw['issue']['viewpoint'], 64);
    if (t && v) set.issue = { topic: t, viewpoint: v };
  }
  if (raw['fromViewpoint'] === true) set.fromViewpoint = true;
  const thumb = str(raw['thumb'], 400000);
  if (thumb && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(thumb)) set.thumb = thumb;
  const bad: string[] = [];
  const ids = new Set<string>();
  if (Array.isArray(raw['markups'])) {
    raw['markups'].slice(0, 5000).forEach((r, i) => {
      const m = sanitizeMarkup(r, author);
      if (typeof m === 'string') { bad.push(`${title}, markup ${i + 1}: ${m}`); return; }
      if (ids.has(m.id)) m.id = newMarkupId();
      ids.add(m.id);
      set.markups.push(m);
    });
  }
  // Numbers: keep those that are unique and positive, number the rest after the highest.
  const seen = new Set<number>();
  let hi = Math.max(0, ...set.markups.map((m) => m.number));
  for (const m of set.markups) {
    if (m.number < 1 || seen.has(m.number)) m.number = ++hi;
    seen.add(m.number);
  }
  const given = isNum(raw['nextNumber']) ? Math.floor(raw['nextNumber']) : 0;
  set.nextNumber = Math.max(given, hi + 1);
  return { set, bad };
}

export interface ParsedMarkupDoc {
  sets: MarkupSet[];
  model?: ModelIdentity;
  link?: string;
  instructions?: string;
  /** Sets and markups that were left out, with the reason. */
  bad: string[];
  /** Set when the whole document was refused. */
  error?: string;
}

export function cleanIdentity(v: unknown): ModelIdentity | undefined {
  if (!isObj(v)) return undefined;
  const name = str(v['name'], 400);
  if (name === undefined || !isNum(v['elementCount'])) return undefined;
  const hash = str(v['guidHash'], 64) ?? '';
  return { name, elementCount: Math.floor(v['elementCount']), guidCount: isNum(v['guidCount']) ? Math.floor(v['guidCount']) : 0, guidHash: hash };
}

/** Read an `xray-markup-set/1` document from text or an object. A newer major version is refused with a message. */
export function parseMarkupDoc(input: unknown): ParsedMarkupDoc {
  const fail = (error: string): ParsedMarkupDoc => ({ sets: [], bad: [], error });
  let doc: unknown = input;
  if (typeof input === 'string') {
    try {
      doc = JSON.parse(input);
    } catch {
      return fail('The file is not JSON.');
    }
  }
  if (!isObj(doc)) return fail('The file is not a markup document.');
  const schema = doc['schema'];
  if (typeof schema !== 'string' || !schema.startsWith(SCHEMA_PREFIX)) return fail('The file is not an X-ray markup document (schema xray-markup-set/1).');
  const major = Number(schema.slice(SCHEMA_PREFIX.length));
  if (!Number.isFinite(major) || major < 1) return fail(`Unknown markup schema "${schema}".`);
  if (major > 1) return fail(`This markup file is version ${major}; this viewer reads version 1. Update the viewer to open it.`);
  if (!Array.isArray(doc['sets'])) return fail('The markup document has no sets.');
  const out: ParsedMarkupDoc = { sets: [], bad: [] };
  const model = cleanIdentity(doc['model']);
  if (model) out.model = model;
  const link = str(doc['link'], 20000);
  if (link) out.link = link;
  const ins = str(doc['instructions'], 4000);
  if (ins) out.instructions = ins;
  for (const r of doc['sets'].slice(0, 200)) {
    const s = sanitizeSet(r);
    if (typeof s === 'string') out.bad.push(s);
    else {
      if (s.set.model === undefined && model) s.set.model = model;
      out.sets.push(s.set);
      out.bad.push(...s.bad);
    }
  }
  if (!out.sets.length) out.error = 'The markup document has no usable set.';
  return out;
}

// ---------------------------------------------------------------- writing

/** The JSON document of some sets. Thumbnails are left out unless `withThumbs`. */
export function buildMarkupDoc(model: ModelIdentity, sets: readonly MarkupSet[], o: { link?: string; withThumbs?: boolean; now?: Date } = {}): MarkupDoc {
  const doc: MarkupDoc = {
    schema: MARKUP_SCHEMA,
    generator: 'X-ray mode for BIM reference viewer, markup',
    exportedAt: (o.now ?? new Date()).toISOString(),
    instructions: INSTRUCTIONS,
    model,
    sets: sets.map((s) => {
      const c = cloneSet(s);
      delete c.view.thumb;
      if (!o.withThumbs) delete c.thumb;
      // Each set says which model it was made on (null: unknown), so a file with sets of several models stays correct.
      c.model = s.model ?? null;
      return c;
    }),
  };
  if (o.link) doc.link = o.link;
  return doc;
}

export function markupDocJson(doc: MarkupDoc): string {
  return `${JSON.stringify(doc, null, 2)}\n`;
}

/** Merge incoming sets into a list: a set with an id already present replaces it; others are added (titles made unique). */
export function mergeSets(have: readonly MarkupSet[], incoming: readonly MarkupSet[]): { sets: MarkupSet[]; added: number; replaced: number } {
  const out = [...have];
  let added = 0;
  let replaced = 0;
  for (const s of incoming) {
    const i = out.findIndex((x) => x.id === s.id);
    if (i >= 0) { out[i] = s; replaced++; continue; }
    let title = s.title;
    for (let n = 2; out.some((x) => x.title === title); n++) title = `${s.title} (${n})`;
    out.push({ ...s, title });
    added++;
  }
  return { sets: out, added, replaced };
}

export function uniqueSetTitle(title: string, sets: readonly MarkupSet[], except?: string): string {
  const base = title.trim() || 'Markup';
  let t = base;
  for (let n = 2; sets.some((x) => x.title === t && x.id !== except); n++) t = `${base} (${n})`;
  return t;
}

export function defaultSetTitle(sets: readonly MarkupSet[]): string {
  for (let n = sets.length + 1; ; n++) if (!sets.some((x) => x.title === `Markup ${n}`)) return `Markup ${n}`;
}
