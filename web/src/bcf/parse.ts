// Reading BCF 2.0 / 2.1 / 3.0: markup.bcf, .bcfv viewpoints, extensions / documents / project files and the zip container.
// The reader is deliberately form-agnostic: BCF 2.1 lists Comment, Labels, Viewpoints directly under Markup / Topic, BCF 3.0
// wraps them (Comments, Labels, Viewpoints/ViewPoint), and both are accepted whatever bcf.version says.

import { readZip } from './zip';
import type { ZipEntry } from './zip';
import { child, childNum, childText, childrenOf, decodeXmlBytes, parseXml, textOf } from './xml';
import type { XNode } from './xml';
import { emptyExtensions, newGuid, nowIso, normaliseColor } from './model';
import type {
  BcfCamera, BcfClippingPlane, BcfColoring, BcfComment, BcfComponent, BcfDocument, BcfDocumentReference, BcfHeaderFile,
  BcfProject, BcfSnippet, BcfTopic, BcfViewpoint, BcfViewpointRef, BcfVisibility, Vec3,
} from './model';

function boolAttr(n: XNode, name: string): boolean | undefined {
  const v = n.attrs[name];
  if (v === undefined) return undefined;
  const t = v.trim().toLowerCase();
  if (t === 'true' || t === '1') return true;
  if (t === 'false' || t === '0') return false;
  return undefined;
}

function vec(n: XNode | undefined): Vec3 | null {
  if (!n) return null;
  const x = childNum(n, 'X');
  const y = childNum(n, 'Y');
  const z = childNum(n, 'Z');
  if (x === undefined || y === undefined || z === undefined) return null;
  return [x, y, z];
}

function component(n: XNode): BcfComponent {
  const c: BcfComponent = {};
  if (n.attrs['IfcGuid']) c.ifcGuid = n.attrs['IfcGuid'];
  const os = childText(n, 'OriginatingSystem');
  if (os) c.originatingSystem = os;
  const at = childText(n, 'AuthoringToolId');
  if (at) c.authoringToolId = at;
  return c;
}

// ---------------------------------------------------------------- viewpoint (.bcfv)

export function parseViewpoint(xml: string | XNode, fallbackGuid?: string): BcfViewpoint {
  const root = typeof xml === 'string' ? parseXml(xml) : xml;
  if (root.name !== 'VisualizationInfo') throw new Error(`expected VisualizationInfo, found ${root.name}`);
  const vp: BcfViewpoint = {
    guid: root.attrs['Guid'] ?? fallbackGuid ?? newGuid(),
    camera: null,
    selection: [],
    visibility: null,
    coloring: [],
    clipping: [],
    lines: [],
  };

  const persp = child(root, 'PerspectiveCamera');
  const ortho = child(root, 'OrthogonalCamera');
  const camNode = persp ?? ortho;
  if (camNode) {
    const pos = vec(child(camNode, 'CameraViewPoint'));
    const dir = vec(child(camNode, 'CameraDirection'));
    const up = vec(child(camNode, 'CameraUpVector'));
    if (pos && dir && up) {
      const cam: BcfCamera = { kind: persp ? 'perspective' : 'orthogonal', position: pos, direction: dir, up };
      if (persp) cam.fov = childNum(persp, 'FieldOfView');
      else cam.viewToWorldScale = childNum(ortho, 'ViewToWorldScale');
      const ar = childNum(camNode, 'AspectRatio');
      if (ar !== undefined && ar > 0) cam.aspect = ar;
      vp.camera = cam;
    }
  }

  const comps = child(root, 'Components');
  if (comps) {
    const sel = child(comps, 'Selection');
    for (const c of childrenOf(sel, 'Component')) vp.selection.push(component(c));
    const vis = child(comps, 'Visibility');
    if (vis) {
      const v: BcfVisibility = {
        defaultVisibility: boolAttr(vis, 'DefaultVisibility') ?? false,
        exceptions: childrenOf(child(vis, 'Exceptions'), 'Component').map(component),
      };
      // 2.1 puts ViewSetupHints next to Visibility, 3.0 inside it.
      const hints = child(vis, 'ViewSetupHints') ?? child(comps, 'ViewSetupHints');
      if (hints) {
        v.hints = {};
        const s = boolAttr(hints, 'SpacesVisible');
        const b = boolAttr(hints, 'SpaceBoundariesVisible');
        const o = boolAttr(hints, 'OpeningsVisible');
        if (s !== undefined) v.hints.spacesVisible = s;
        if (b !== undefined) v.hints.spaceBoundariesVisible = b;
        if (o !== undefined) v.hints.openingsVisible = o;
      }
      vp.visibility = v;
    }
    const col = child(comps, 'Coloring');
    for (const c of childrenOf(col, 'Color')) {
      const color = normaliseColor(c.attrs['Color'] ?? '');
      if (!color) continue;
      const list: BcfComponent[] = [];
      for (const k of c.children) {
        if (k.name === 'Component') list.push(component(k));
        else if (k.name === 'Components') for (const cc of childrenOf(k, 'Component')) list.push(component(cc));
      }
      const entry: BcfColoring = { color, components: list };
      vp.coloring.push(entry);
    }
  }

  for (const c of childrenOf(child(root, 'ClippingPlanes'), 'ClippingPlane')) {
    const loc = vec(child(c, 'Location'));
    const dir = vec(child(c, 'Direction'));
    if (loc && dir) {
      const p: BcfClippingPlane = { location: loc, direction: dir };
      vp.clipping.push(p);
    }
  }
  for (const l of childrenOf(child(root, 'Lines'), 'Line')) {
    const a = vec(child(l, 'StartPoint'));
    const b = vec(child(l, 'EndPoint'));
    if (a && b) vp.lines.push({ start: a, end: b });
  }
  const bitmaps = childrenOf(root, 'Bitmap').length + childrenOf(child(root, 'Bitmaps'), 'Bitmap').length;
  if (bitmaps) vp.bitmapsIgnored = bitmaps;
  return vp;
}

// ---------------------------------------------------------------- markup (.bcf)

function opt(n: XNode | undefined, name: string): string | undefined {
  const t = childText(n, name);
  return t === undefined || t === '' ? undefined : t;
}

function parseComment(n: XNode): BcfComment {
  const c: BcfComment = {
    guid: n.attrs['Guid'] ?? newGuid(),
    date: opt(n, 'Date') ?? nowIso(),
    author: opt(n, 'Author') ?? '',
    text: childText(n, 'Comment') ?? '',
  };
  const vg = child(n, 'Viewpoint')?.attrs['Guid'];
  if (vg) c.viewpointGuid = vg;
  const md = opt(n, 'ModifiedDate');
  if (md) c.modifiedDate = md;
  const ma = opt(n, 'ModifiedAuthor');
  if (ma) c.modifiedAuthor = ma;
  return c;
}

function parseViewpointRef(n: XNode): BcfViewpointRef {
  const r: BcfViewpointRef = { guid: n.attrs['Guid'] ?? newGuid(), data: null };
  const vf = opt(n, 'Viewpoint');
  if (vf) r.viewpointFile = vf;
  const sf = opt(n, 'Snapshot');
  if (sf) r.snapshotFile = sf;
  const ix = childNum(n, 'Index');
  if (ix !== undefined) r.index = ix;
  return r;
}

function parseHeaderFile(n: XNode): BcfHeaderFile {
  const f: BcfHeaderFile = {};
  const fn = opt(n, 'Filename');
  if (fn) f.filename = fn;
  const d = opt(n, 'Date');
  if (d) f.date = d;
  const r = opt(n, 'Reference');
  if (r) f.reference = r;
  if (n.attrs['IfcProject']) f.ifcProject = n.attrs['IfcProject'];
  if (n.attrs['IfcSpatialStructureElement']) f.ifcSpatialStructureElement = n.attrs['IfcSpatialStructureElement'];
  const ext = boolAttr(n, 'IsExternal') ?? boolAttr(n, 'isExternal');
  if (ext !== undefined) f.isExternal = ext;
  return f;
}

/** Parse markup.bcf text. Viewpoint references are returned with `data: null`; the container fills them in. */
export function parseMarkup(xml: string | XNode): BcfTopic {
  const root = typeof xml === 'string' ? parseXml(xml) : xml;
  if (root.name !== 'Markup') throw new Error(`expected Markup, found ${root.name}`);
  const t = child(root, 'Topic');
  if (!t) throw new Error('markup.bcf has no Topic element');

  const topic: BcfTopic = {
    guid: t.attrs['Guid'] ?? newGuid(),
    topicType: t.attrs['TopicType'] ?? '',
    topicStatus: t.attrs['TopicStatus'] ?? '',
    title: childText(t, 'Title') ?? '',
    labels: [],
    referenceLinks: [],
    creationDate: opt(t, 'CreationDate') ?? '',
    creationAuthor: opt(t, 'CreationAuthor') ?? '',
    headerFiles: [],
    documentReferences: [],
    relatedTopics: [],
    comments: [],
    viewpoints: [],
  };
  if (t.attrs['ServerAssignedId']) topic.serverAssignedId = t.attrs['ServerAssignedId'];
  const set = <K extends 'priority' | 'modifiedDate' | 'modifiedAuthor' | 'dueDate' | 'assignedTo' | 'stage' | 'description'>(k: K, name: string): void => {
    const v = opt(t, name);
    if (v !== undefined) topic[k] = v;
  };
  set('priority', 'Priority');
  set('modifiedDate', 'ModifiedDate');
  set('modifiedAuthor', 'ModifiedAuthor');
  set('dueDate', 'DueDate');
  set('assignedTo', 'AssignedTo');
  set('stage', 'Stage');
  // Description may legitimately contain only whitespace-significant text; keep it untrimmed apart from the ends.
  set('description', 'Description');
  const ix = childNum(t, 'Index');
  if (ix !== undefined) topic.index = ix;

  for (const l of childrenOf(t, 'ReferenceLink')) {
    const v = textOf(l);
    if (v) topic.referenceLinks.push(v);
  }
  for (const w of childrenOf(t, 'ReferenceLinks')) for (const l of childrenOf(w, 'ReferenceLink')) {
    const v = textOf(l);
    if (v) topic.referenceLinks.push(v);
  }
  for (const l of childrenOf(t, 'Labels')) {
    const inner = childrenOf(l, 'Label');
    if (inner.length) for (const i of inner) { const v = textOf(i); if (v) topic.labels.push(v); }
    else { const v = textOf(l); if (v) topic.labels.push(v); }
  }

  // Header: 2.1 has File directly, 3.0 has Files/File.
  const header = child(root, 'Header');
  for (const f of childrenOf(header, 'File')) topic.headerFiles.push(parseHeaderFile(f));
  for (const f of childrenOf(child(header, 'Files'), 'File')) topic.headerFiles.push(parseHeaderFile(f));

  const sn = child(t, 'BimSnippet');
  if (sn) {
    const s: BcfSnippet = {
      snippetType: sn.attrs['SnippetType'] ?? '',
      isExternal: (boolAttr(sn, 'IsExternal') ?? boolAttr(sn, 'isExternal')) === true,
      reference: childText(sn, 'Reference') ?? '',
      referenceSchema: childText(sn, 'ReferenceSchema') ?? '',
    };
    topic.snippet = s;
  }
  const docRefs = [...childrenOf(t, 'DocumentReference'), ...childrenOf(child(t, 'DocumentReferences'), 'DocumentReference')];
  for (const d of docRefs) {
    const url = opt(d, 'Url');
    const dg = opt(d, 'DocumentGuid');
    const rd = opt(d, 'ReferencedDocument');
    const ref: BcfDocumentReference = {
      target: url ?? dg ?? rd,
      external: url !== undefined ? true : dg !== undefined ? false : boolAttr(d, 'isExternal') === true,
    };
    if (d.attrs['Guid']) ref.guid = d.attrs['Guid'];
    const desc = opt(d, 'Description');
    if (desc) ref.description = desc;
    topic.documentReferences.push(ref);
  }
  for (const r of [...childrenOf(t, 'RelatedTopic'), ...childrenOf(child(t, 'RelatedTopics'), 'RelatedTopic')]) {
    if (r.attrs['Guid']) topic.relatedTopics.push(r.attrs['Guid']);
  }

  for (const c of [...childrenOf(root, 'Comment'), ...childrenOf(child(t, 'Comments'), 'Comment'), ...childrenOf(child(root, 'Comments'), 'Comment')]) {
    topic.comments.push(parseComment(c));
  }
  for (const v of [...childrenOf(root, 'Viewpoints'), ...childrenOf(child(t, 'Viewpoints'), 'ViewPoint'), ...childrenOf(child(t, 'Viewpoints'), 'Viewpoint')]) {
    topic.viewpoints.push(parseViewpointRef(v));
  }
  return topic;
}

// ---------------------------------------------------------------- container

function textList(root: XNode | undefined, wrapper: string, item: string): string[] {
  const out: string[] = [];
  for (const n of childrenOf(child(root, wrapper), item)) {
    const v = textOf(n);
    if (v) out.push(v);
  }
  return out;
}

const PNG_SIG = [0x89, 0x50, 0x4e, 0x47];
function sniffImage(b: Uint8Array): 'image/png' | 'image/jpeg' | undefined {
  if (b.length > 4 && PNG_SIG.every((v, i) => b[i] === v)) return 'image/png';
  if (b.length > 3 && b[0] === 0xff && b[1] === 0xd8) return 'image/jpeg';
  return undefined;
}

export interface ParseOptions {
  /** Load snapshot bytes (default true). */
  snapshots?: boolean;
}

/** Parse a .bcf / .bcfzip archive. Never throws for a broken topic: the problem goes to `warnings` and the topic is skipped. */
export async function parseBcf(data: Uint8Array | ArrayBuffer, opts: ParseOptions = {}): Promise<BcfProject> {
  const entries = readZip(data);
  const byLower = new Map<string, ZipEntry>();
  for (const e of entries) if (!e.isDirectory) byLower.set(e.name.toLowerCase(), e);
  const get = (name: string): ZipEntry | undefined => byLower.get(name.replace(/\\/g, '/').replace(/^\.\//, '').toLowerCase());

  const project: BcfProject = { versionId: '', extensions: emptyExtensions(), documents: [], topics: [], warnings: [] };
  const warn = (m: string): void => void project.warnings.push(m);
  const readXml = async (e: ZipEntry): Promise<XNode> => parseXml(decodeXmlBytes(await e.read()));

  const ver = get('bcf.version');
  if (ver) {
    try {
      const n = await readXml(ver);
      project.versionId = n.attrs['VersionId'] ?? childText(n, 'DetailedVersion') ?? '';
    } catch (e) {
      warn(`bcf.version: ${(e as Error).message}`);
    }
  } else {
    warn('bcf.version is missing');
  }
  if (!project.versionId) project.versionId = '2.1';
  else if (!/^(1\.0|2\.0|2\.1|3\.0)/.test(project.versionId)) warn(`unknown BCF version "${project.versionId}", reading as 2.1`);

  for (const pname of ['project.bcfp', 'project.bcf']) {
    const pe = get(pname);
    if (!pe) continue;
    try {
      const n = await readXml(pe);
      const p = child(n, 'Project');
      if (p) {
        if (p.attrs['ProjectId']) project.projectId = p.attrs['ProjectId'];
        const nm = childText(p, 'Name');
        if (nm) project.projectName = nm;
      }
    } catch (e) {
      warn(`${pname}: ${(e as Error).message}`);
    }
    break;
  }

  const ext = get('extensions.xml');
  if (ext) {
    try {
      const n = await readXml(ext);
      project.extensions = {
        topicTypes: textList(n, 'TopicTypes', 'TopicType'),
        topicStatuses: textList(n, 'TopicStatuses', 'TopicStatus'),
        priorities: textList(n, 'Priorities', 'Priority'),
        topicLabels: textList(n, 'TopicLabels', 'TopicLabel'),
        users: textList(n, 'Users', 'User'),
        snippetTypes: textList(n, 'SnippetTypes', 'SnippetType'),
        stages: textList(n, 'Stages', 'Stage'),
      };
    } catch (e) {
      warn(`extensions.xml: ${(e as Error).message}`);
    }
  }

  const docs = get('documents.xml');
  if (docs) {
    try {
      const n = await readXml(docs);
      for (const d of childrenOf(child(n, 'Documents'), 'Document')) {
        const guid = d.attrs['Guid'];
        if (!guid) continue;
        const doc: BcfDocument = { guid, filename: childText(d, 'Filename') ?? guid };
        const desc = childText(d, 'Description');
        if (desc) doc.description = desc;
        const de = get(`Documents/${guid}`);
        if (de) doc.data = await de.read();
        project.documents.push(doc);
      }
    } catch (e) {
      warn(`documents.xml: ${(e as Error).message}`);
    }
  }

  // Topic folders: any folder holding a markup.bcf.
  const markups = entries.filter((e) => !e.isDirectory && /(^|\/)markup\.bcf$/i.test(e.name));
  for (const m of markups) {
    const folder = m.name.includes('/') ? m.name.slice(0, m.name.lastIndexOf('/') + 1) : '';
    try {
      const topic = parseMarkup(await readXml(m));
      if (!topic.guid || folder === '') {
        // A folder-less markup (non-conforming) is still readable.
      } else if (folder.slice(0, -1).toLowerCase() !== topic.guid.toLowerCase()) {
        warn(`topic ${topic.guid}: folder name "${folder.slice(0, -1)}" differs from the topic Guid`);
      }
      // BCF 1.0 / 2.0 without a Viewpoints list: viewpoint.bcfv and snapshot.png next to the markup.
      if (topic.viewpoints.length === 0) {
        const v = get(`${folder}viewpoint.bcfv`);
        if (v) {
          const ref: BcfViewpointRef = { guid: newGuid(), viewpointFile: 'viewpoint.bcfv', data: null };
          const s = get(`${folder}snapshot.png`);
          if (s) ref.snapshotFile = 'snapshot.png';
          topic.viewpoints.push(ref);
        }
      }
      for (const ref of topic.viewpoints) {
        if (ref.viewpointFile) {
          const ve = get(folder + ref.viewpointFile);
          if (!ve) {
            ref.problem = `viewpoint file ${ref.viewpointFile} is missing`;
          } else {
            try {
              ref.data = parseViewpoint(decodeXmlBytes(await ve.read()), ref.guid);
              // The markup reference guid is authoritative for linking comments.
              ref.data.guid = ref.guid;
            } catch (e) {
              ref.problem = `${ref.viewpointFile}: ${(e as Error).message}`;
            }
          }
        }
        if (ref.snapshotFile && opts.snapshots !== false) {
          const se = get(folder + ref.snapshotFile);
          if (se) {
            try {
              const bytes = await se.read();
              const mime = sniffImage(bytes);
              if (mime) {
                ref.snapshot = bytes;
                ref.snapshotMime = mime;
              }
            } catch (e) {
              warn(`snapshot ${ref.snapshotFile}: ${(e as Error).message}`);
            }
          }
        }
        if (ref.problem) warn(`topic ${topic.guid}: ${ref.problem}`);
      }
      project.topics.push(topic);
    } catch (e) {
      warn(`${m.name}: ${(e as Error).message}`);
    }
  }
  if (project.topics.length === 0 && markups.length === 0) warn('the archive contains no markup.bcf');
  return project;
}
