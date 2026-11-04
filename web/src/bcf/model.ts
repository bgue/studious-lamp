// BCF data model and the coordinate mapping between BCF (IFC project coordinates: metres, Z up) and the viewer
// (metres, Y up, shifted by the sidecar originShift).
//
// The converter (tools/glb_common.py write_model, web/src/model/ifcImport.ts) maps an IFC point p to the viewer as
//   v = ( p.x - s.x,  p.z - s.z,  -(p.y - s.y) )        s = originShift (IFC frame)
// that is: subtract the shift in the IFC frame, then rotate -90 degrees about X, (x, y, z) -> (x, z, -y).
// Directions only rotate: (x, y, z) -> (x, z, -y). The inverse is p = ( v.x + s.x,  -v.z + s.y,  v.y + s.z ).

export type Vec3 = [number, number, number];
export type BcfVersion = '2.1' | '3.0';

export function ifcToViewer(p: Vec3, shift: Vec3): Vec3 {
  return [p[0] - shift[0], p[2] - shift[2], -(p[1] - shift[1])];
}
export function viewerToIfc(v: Vec3, shift: Vec3): Vec3 {
  return [v[0] + shift[0], -v[2] + shift[1], v[1] + shift[2]];
}
export function dirIfcToViewer(d: Vec3): Vec3 {
  return [d[0], d[2], -d[1]];
}
export function dirViewerToIfc(d: Vec3): Vec3 {
  return [d[0], -d[2], d[1]];
}

// ---------------------------------------------------------------- viewpoint

export interface BcfCamera {
  kind: 'perspective' | 'orthogonal';
  /** CameraViewPoint (IFC coordinates). */
  position: Vec3;
  /** CameraDirection (IFC coordinates, not necessarily unit length). */
  direction: Vec3;
  up: Vec3;
  /** Perspective: vertical field of view in degrees. */
  fov?: number;
  /** Orthogonal: ViewToWorldScale (metres of visible height, BCF 3.0 semantics). */
  viewToWorldScale?: number;
  /** Width over height. Absent in BCF 2.x files (1.0 is assumed by the spec). */
  aspect?: number;
}

export interface BcfComponent {
  ifcGuid?: string;
  originatingSystem?: string;
  authoringToolId?: string;
}

export interface BcfVisibility {
  /** BCF 3.0 default is false. */
  defaultVisibility: boolean;
  exceptions: BcfComponent[];
  hints?: { spacesVisible?: boolean; spaceBoundariesVisible?: boolean; openingsVisible?: boolean };
}

export interface BcfColoring {
  /** Hex RRGGBB or RRGGBBAA, upper case. */
  color: string;
  components: BcfComponent[];
}

export interface BcfClippingPlane {
  location: Vec3;
  /** Points into the clipped (invisible) half-space. */
  direction: Vec3;
}

export interface BcfViewpoint {
  guid: string;
  camera: BcfCamera | null;
  selection: BcfComponent[];
  /** Null when the file has no Visibility element (nothing to apply). */
  visibility: BcfVisibility | null;
  coloring: BcfColoring[];
  clipping: BcfClippingPlane[];
  lines: Array<{ start: Vec3; end: Vec3 }>;
  /** Number of Bitmap elements that were read and ignored. */
  bitmapsIgnored?: number;
}

// ---------------------------------------------------------------- topic and project

export interface BcfViewpointRef {
  guid: string;
  /** File name of the .bcfv inside the topic folder. */
  viewpointFile?: string;
  /** File name of the snapshot inside the topic folder. */
  snapshotFile?: string;
  index?: number;
  /** Parsed .bcfv (null when the file is missing or unreadable). */
  data: BcfViewpoint | null;
  /** Snapshot bytes (PNG or JPEG). */
  snapshot?: Uint8Array;
  snapshotMime?: 'image/png' | 'image/jpeg';
  /** Why the viewpoint file could not be read. */
  problem?: string;
  /** Viewer markup on this viewpoint (side file xray-markup.json, see sidecar.ts). */
  annotations?: BcfAnnotation[];
  /** The camera that took the snapshot (IFC coordinates). Used to burn the markup into the snapshot. */
  snapshotView?: BcfSnapshotView;
}

// ---------------------------------------------------------------- viewer markup (pins and annotations)
// BCF 2.1 / 3.0 have no place for these. They live in a side file of the topic folder (sidecar.ts); all points are IFC
// project coordinates, like the viewpoint cameras.

/** The 3D point a topic is pinned to. */
export interface BcfPin {
  position: Vec3;
  /** IfcGuid of the element under the pin, when it was picked on one. */
  elementGuid?: string;
}

/** A measurement captured into an annotation, so it survives without the measure tool. IFC coordinates. */
export interface BcfMeasureLink {
  kind: 'point' | 'element';
  a: Vec3;
  b: Vec3;
  /** Metres. */
  distance: number;
  /** The label as shown, such as "2.345 m". */
  label: string;
  elementGuids?: string[];
  /** The measure tool id at link time (informational). */
  sourceId?: number;
}

export interface BcfAnchor {
  kind: 'element' | 'measurement' | 'point';
  /** IFC coordinates. Element: the picked point on it. Measurement: the middle of the dimension line. */
  point: Vec3;
  elementGuid?: string;
  measurement?: BcfMeasureLink;
}

export const ANNOTATION_TYPES = ['callout', 'note', 'arrow'] as const;
export type BcfAnnotationType = (typeof ANNOTATION_TYPES)[number];

export interface BcfAnnotation {
  guid: string;
  type: BcfAnnotationType;
  text: string;
  anchor: BcfAnchor;
  /** Text box position relative to the anchor, as fractions of the view height (x right, y down). */
  offset: [number, number];
  author?: string;
  date?: string;
}

export interface BcfSnapshotView {
  position: Vec3;
  direction: Vec3;
  up: Vec3;
  /** Vertical field of view, degrees. */
  fov: number;
  aspect: number;
}

export interface BcfComment {
  guid: string;
  date: string;
  author: string;
  text: string;
  viewpointGuid?: string;
  modifiedDate?: string;
  modifiedAuthor?: string;
}

export interface BcfHeaderFile {
  filename?: string;
  date?: string;
  reference?: string;
  ifcProject?: string;
  ifcSpatialStructureElement?: string;
  isExternal?: boolean;
}

export interface BcfDocumentReference {
  guid?: string;
  /** Internal document guid, or the url / file name when external. */
  target?: string;
  external: boolean;
  description?: string;
}

export interface BcfSnippet {
  snippetType: string;
  isExternal: boolean;
  reference: string;
  referenceSchema: string;
}

export interface BcfTopic {
  guid: string;
  serverAssignedId?: string;
  topicType: string;
  topicStatus: string;
  title: string;
  priority?: string;
  index?: number;
  labels: string[];
  referenceLinks: string[];
  creationDate: string;
  creationAuthor: string;
  modifiedDate?: string;
  modifiedAuthor?: string;
  dueDate?: string;
  assignedTo?: string;
  stage?: string;
  description?: string;
  headerFiles: BcfHeaderFile[];
  snippet?: BcfSnippet;
  documentReferences: BcfDocumentReference[];
  relatedTopics: string[];
  comments: BcfComment[];
  viewpoints: BcfViewpointRef[];
  /** Viewer markup: the 3D point of the topic (side file, see sidecar.ts). */
  pin?: BcfPin;
}

export interface BcfExtensions {
  topicTypes: string[];
  topicStatuses: string[];
  priorities: string[];
  topicLabels: string[];
  users: string[];
  snippetTypes: string[];
  stages: string[];
}

export interface BcfDocument {
  guid: string;
  filename: string;
  description?: string;
  data?: Uint8Array;
}

export interface BcfProject {
  /** Version found in bcf.version (or the version to write). Older files report their own id here as text. */
  versionId: string;
  projectId?: string;
  projectName?: string;
  extensions: BcfExtensions;
  documents: BcfDocument[];
  topics: BcfTopic[];
  /** Non-fatal problems met while reading. */
  warnings: string[];
}

export function emptyExtensions(): BcfExtensions {
  return { topicTypes: [], topicStatuses: [], priorities: [], topicLabels: [], users: [], snippetTypes: [], stages: [] };
}

export function emptyProject(version: BcfVersion = '2.1'): BcfProject {
  return { versionId: version, extensions: emptyExtensions(), documents: [], topics: [], warnings: [] };
}

// ---------------------------------------------------------------- ids and validation helpers

/** RFC 4122 version 4 UUID, lower case. */
export function newGuid(): string {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  const b = new Uint8Array(16);
  if (c && typeof c.getRandomValues === 'function') c.getRandomValues(b);
  else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export const GUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
export const IFC_GUID_RE = /^[0-9A-Za-z_$]{22}$/;

export function isGuid(s: string | undefined): s is string {
  return !!s && GUID_RE.test(s);
}

/** The IfcGuid to write for a viewer GlobalId: federation suffixes (`<id>~2`) are removed; null when not a valid IfcGuid. */
export function toIfcGuid(globalId: string): string | null {
  const g = globalId.replace(/~\d+$/, '');
  return IFC_GUID_RE.test(g) ? g : null;
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function componentGuids(cs: BcfComponent[]): string[] {
  const out: string[] = [];
  for (const c of cs) if (c.ifcGuid) out.push(c.ifcGuid);
  return out;
}

export function normaliseColor(c: string): string | null {
  const m = /^#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$/.exec(c.trim());
  return m ? (m[1]! + (m[2] ?? '')).toUpperCase() : null;
}

export function cloneTopicShallow(t: BcfTopic): BcfTopic {
  return { ...t, labels: [...t.labels], comments: [...t.comments], viewpoints: [...t.viewpoints] };
}
