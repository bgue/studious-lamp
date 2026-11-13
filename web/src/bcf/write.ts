// Writing BCF 2.1 and 3.0: markup.bcf, .bcfv, bcf.version, extensions.xml (3.0), project.bcfp, documents.xml (3.0) and the zip.
// Element order follows the official XSDs (tests/fixtures/bcf/xsd, validated by tests/bcf-xsd.test.ts and
// tests/fixtures/bcf/validate_xsd.py). Differences handled here:
//   2.1: Comment and Viewpoints are Markup children, Labels / ReferenceLink / DocumentReference repeat, ViewSetupHints sits next to
//        Visibility, Visibility is required when Components exists, Selection needs one Component, FieldOfView is 45..60, no AspectRatio.
//   3.0: wrapper elements (Comments, Labels, ViewPoints, Files ...), non-empty strings, lower-case guids, TopicType and
//        TopicStatus required, camera required, AspectRatio required, ViewSetupHints inside Visibility.
// ClippingPlane Direction points into the clipped (invisible) half-space, as the BCF 3.0 documentation states; the 2.1
// documentation is silent and viewers follow the same convention.

import { writeZip } from './zip';
import type { ZipInput } from './zip';
import { esc, num } from './xml';
import { IFC_GUID_RE, GUID_RE, newGuid, nowIso } from './model';
import { SIDECAR_NAME, annotationGuids, baseSnapshotName, needsBurn, sidecarJson } from './sidecar';
import { attachmentSegments, segmentKey } from './attach';
import type {
  BcfColoring, BcfComment, BcfComponent, BcfProject, BcfTopic, BcfVersion, BcfViewpoint, BcfViewpointRef,
} from './model';

const XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>';

class W {
  private lines: string[] = [XML_DECL];
  private depth = 0;
  private stack: string[] = [];

  private pad(): string {
    return '  '.repeat(this.depth);
  }
  private attrs(a?: Record<string, string | number | boolean | undefined>): string {
    if (!a) return '';
    let s = '';
    for (const [k, v] of Object.entries(a)) if (v !== undefined) s += ` ${k}="${esc(String(v))}"`;
    return s;
  }
  open(name: string, a?: Record<string, string | number | boolean | undefined>): this {
    this.lines.push(`${this.pad()}<${name}${this.attrs(a)}>`);
    this.stack.push(name);
    this.depth++;
    return this;
  }
  close(): this {
    const n = this.stack.pop();
    this.depth--;
    this.lines.push(`${this.pad()}</${n}>`);
    return this;
  }
  leaf(name: string, text: string, a?: Record<string, string | number | boolean | undefined>): this {
    this.lines.push(`${this.pad()}<${name}${this.attrs(a)}>${esc(text)}</${name}>`);
    return this;
  }
  empty(name: string, a?: Record<string, string | number | boolean | undefined>): this {
    this.lines.push(`${this.pad()}<${name}${this.attrs(a)}/>`);
    return this;
  }
  toString(): string {
    return `${this.lines.join('\n')}\n`;
  }
}

const DATETIME_RE = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)?$/;
function dateTime(s: string | undefined): string {
  if (s && DATETIME_RE.test(s)) return s;
  if (s) {
    const d = new Date(s);
    if (!Number.isNaN(d.getTime())) return d.toISOString();
  }
  return nowIso();
}

function blank(s: string | undefined): s is undefined {
  return s === undefined || s.trim() === '';
}

// ---------------------------------------------------------------- viewpoint

function validComponent(c: BcfComponent): boolean {
  return (c.ifcGuid !== undefined && IFC_GUID_RE.test(c.ifcGuid)) || !blank(c.authoringToolId) || !blank(c.originatingSystem);
}

function writeComponent(w: W, c: BcfComponent, v: BcfVersion): void {
  const guid = c.ifcGuid !== undefined && IFC_GUID_RE.test(c.ifcGuid) ? c.ifcGuid : undefined;
  const os = !blank(c.originatingSystem) ? c.originatingSystem : undefined;
  const at = !blank(c.authoringToolId) ? c.authoringToolId : undefined;
  void v;
  if (os === undefined && at === undefined) {
    w.empty('Component', { IfcGuid: guid });
    return;
  }
  w.open('Component', { IfcGuid: guid });
  if (os !== undefined) w.leaf('OriginatingSystem', os);
  if (at !== undefined) w.leaf('AuthoringToolId', at);
  w.close();
}

function point(w: W, name: string, p: readonly [number, number, number]): void {
  w.open(name).leaf('X', num(p[0])).leaf('Y', num(p[1])).leaf('Z', num(p[2])).close();
}

function hex(c: BcfColoring): string {
  return /^[0-9A-F]{6}([0-9A-F]{2})?$/.test(c.color) ? c.color : '';
}

export function writeViewpoint(vp: BcfViewpoint, version: BcfVersion): string {
  const v3 = version === '3.0';
  const w = new W();
  w.open('VisualizationInfo', { Guid: v3 ? vp.guid.toLowerCase() : vp.guid });

  const selection = vp.selection.filter(validComponent);
  const vis = vp.visibility;
  const colorings = vp.coloring.map((c) => ({ color: hex(c), comps: c.components.filter(validComponent) })).filter((c) => c.color && c.comps.length);
  const hints = vis?.hints;
  const hasHints = !!hints && (hints.spacesVisible !== undefined || hints.spaceBoundariesVisible !== undefined || hints.openingsVisible !== undefined);
  const hintAttrs = hints ? { SpacesVisible: hints.spacesVisible, SpaceBoundariesVisible: hints.spaceBoundariesVisible, OpeningsVisible: hints.openingsVisible } : undefined;
  const exceptions = (vis?.exceptions ?? []).filter(validComponent);

  if (v3) {
    if (selection.length || vis || colorings.length) {
      w.open('Components');
      if (selection.length) {
        w.open('Selection');
        for (const c of selection) writeComponent(w, c, version);
        w.close();
      }
      if (vis) {
        w.open('Visibility', { DefaultVisibility: vis.defaultVisibility });
        if (hasHints) w.empty('ViewSetupHints', hintAttrs);
        if (exceptions.length) {
          w.open('Exceptions');
          for (const c of exceptions) writeComponent(w, c, version);
          w.close();
        }
        w.close();
      }
      if (colorings.length) {
        w.open('Coloring');
        for (const c of colorings) {
          w.open('Color', { Color: c.color }).open('Components');
          for (const k of c.comps) writeComponent(w, k, version);
          w.close().close();
        }
        w.close();
      }
      w.close();
    }
  } else if (selection.length || vis || colorings.length) {
    w.open('Components');
    if (hasHints) w.empty('ViewSetupHints', hintAttrs);
    if (selection.length) {
      w.open('Selection');
      for (const c of selection) writeComponent(w, c, version);
      w.close();
    }
    // Visibility is required in 2.1 as soon as Components exists.
    w.open('Visibility', { DefaultVisibility: vis ? vis.defaultVisibility : true });
    if (exceptions.length) {
      w.open('Exceptions');
      for (const c of exceptions) writeComponent(w, c, version);
      w.close();
    }
    w.close();
    if (colorings.length) {
      w.open('Coloring');
      for (const c of colorings) {
        w.open('Color', { Color: c.color });
        for (const k of c.comps) writeComponent(w, k, version);
        w.close();
      }
      w.close();
    }
    w.close();
  }

  // Camera (required in 3.0).
  const cam = vp.camera ?? { kind: 'perspective' as const, position: [0, 0, 0] as [number, number, number], direction: [0, 1, 0] as [number, number, number], up: [0, 0, 1] as [number, number, number], fov: 45 };
  if (cam.kind === 'orthogonal') {
    w.open('OrthogonalCamera');
    point(w, 'CameraViewPoint', cam.position);
    point(w, 'CameraDirection', cam.direction);
    point(w, 'CameraUpVector', cam.up);
    w.leaf('ViewToWorldScale', num(cam.viewToWorldScale && cam.viewToWorldScale > 0 ? cam.viewToWorldScale : 1));
    if (v3) w.leaf('AspectRatio', num(cam.aspect && cam.aspect > 0 ? cam.aspect : 1));
    w.close();
  } else {
    w.open('PerspectiveCamera');
    point(w, 'CameraViewPoint', cam.position);
    point(w, 'CameraDirection', cam.direction);
    point(w, 'CameraUpVector', cam.up);
    let fov = cam.fov && cam.fov > 0 && cam.fov < 180 ? cam.fov : 45;
    if (!v3) fov = Math.min(60, Math.max(45, fov)); // the 2.1 schema restricts FieldOfView to 45..60
    w.leaf('FieldOfView', num(fov));
    if (v3) w.leaf('AspectRatio', num(cam.aspect && cam.aspect > 0 ? cam.aspect : 1));
    w.close();
  }

  if (vp.lines.length) {
    w.open('Lines');
    for (const l of vp.lines) w.open('Line').open('StartPoint').leaf('X', num(l.start[0])).leaf('Y', num(l.start[1])).leaf('Z', num(l.start[2])).close().open('EndPoint').leaf('X', num(l.end[0])).leaf('Y', num(l.end[1])).leaf('Z', num(l.end[2])).close().close();
    w.close();
  }
  if (vp.clipping.length) {
    w.open('ClippingPlanes');
    for (const c of vp.clipping) {
      w.open('ClippingPlane');
      point(w, 'Location', c.location);
      point(w, 'Direction', c.direction);
      w.close();
    }
    w.close();
  }
  w.close();
  return w.toString();
}

// ---------------------------------------------------------------- markup

function viewpointNames(topic: BcfTopic, version: BcfVersion): BcfViewpointRef[] {
  return topic.viewpoints.map((r, i) => {
    const g = version === '3.0' ? r.guid.toLowerCase() : r.guid;
    const ext = r.snapshotMime === 'image/jpeg' ? 'jpg' : 'png';
    return {
      ...r,
      viewpointFile: r.data ? (version === '2.1' && i === 0 ? 'viewpoint.bcfv' : `${g}.bcfv`) : undefined,
      snapshotFile: r.snapshot ? (version === '2.1' && i === 0 ? `snapshot.${ext}` : `${g}.${ext}`) : undefined,
    };
  });
}

function writeCommentEntry(w: W, c: BcfComment, version: BcfVersion): void {
  const v3 = version === '3.0';
  w.open('Comment', { Guid: v3 ? c.guid.toLowerCase() : c.guid });
  w.leaf('Date', dateTime(c.date));
  w.leaf('Author', blank(c.author) ? 'unknown' : c.author);
  if (!v3 || !blank(c.text)) w.leaf('Comment', c.text);
  if (c.viewpointGuid) w.empty('Viewpoint', { Guid: v3 ? c.viewpointGuid.toLowerCase() : c.viewpointGuid });
  if (c.modifiedDate) w.leaf('ModifiedDate', dateTime(c.modifiedDate));
  if (!blank(c.modifiedAuthor)) w.leaf('ModifiedAuthor', c.modifiedAuthor);
  w.close();
}

/** markup.bcf text. Viewpoint file names are taken from the refs (see writeBcf, which assigns them). */
export function writeMarkup(topic: BcfTopic, version: BcfVersion): string {
  const v3 = version === '3.0';
  const lg = (g: string): string => (v3 ? g.toLowerCase() : g);
  const w = new W();
  w.open('Markup');

  const files = topic.headerFiles;
  if (files.length) {
    w.open('Header');
    if (v3) w.open('Files');
    for (const f of files) {
      const a: Record<string, string | boolean | undefined> = {
        IfcProject: f.ifcProject && IFC_GUID_RE.test(f.ifcProject) ? f.ifcProject : undefined,
        IfcSpatialStructureElement: f.ifcSpatialStructureElement && IFC_GUID_RE.test(f.ifcSpatialStructureElement) ? f.ifcSpatialStructureElement : undefined,
      };
      a[v3 ? 'IsExternal' : 'isExternal'] = f.isExternal;
      const kids = [f.filename, f.date, f.reference].some((x) => !blank(x));
      if (!kids) {
        w.empty('File', a);
        continue;
      }
      w.open('File', a);
      if (!blank(f.filename)) w.leaf('Filename', f.filename);
      if (f.date) w.leaf('Date', dateTime(f.date));
      if (!blank(f.reference)) w.leaf('Reference', f.reference);
      w.close();
    }
    if (v3) w.close();
    w.close();
  }

  const topicAttrs: Record<string, string | undefined> = { Guid: lg(topic.guid) };
  if (v3 && !blank(topic.serverAssignedId)) topicAttrs['ServerAssignedId'] = topic.serverAssignedId;
  topicAttrs['TopicType'] = !blank(topic.topicType) ? topic.topicType : v3 ? 'Issue' : undefined;
  topicAttrs['TopicStatus'] = !blank(topic.topicStatus) ? topic.topicStatus : v3 ? 'Open' : undefined;
  w.open('Topic', topicAttrs);

  const links = topic.referenceLinks.filter((l) => !blank(l));
  if (v3) {
    if (links.length) {
      w.open('ReferenceLinks');
      for (const l of links) w.leaf('ReferenceLink', l);
      w.close();
    }
  } else for (const l of links) w.leaf('ReferenceLink', l);
  w.leaf('Title', blank(topic.title) ? 'Untitled' : topic.title);
  if (!blank(topic.priority)) w.leaf('Priority', topic.priority);
  if (topic.index !== undefined && Number.isFinite(topic.index)) w.leaf('Index', String(Math.round(topic.index)));
  const labels = topic.labels.filter((l) => !blank(l));
  if (v3) {
    if (labels.length) {
      w.open('Labels');
      for (const l of labels) w.leaf('Label', l);
      w.close();
    }
  } else for (const l of labels) w.leaf('Labels', l);
  w.leaf('CreationDate', dateTime(topic.creationDate));
  w.leaf('CreationAuthor', blank(topic.creationAuthor) ? 'unknown' : topic.creationAuthor);
  if (topic.modifiedDate) w.leaf('ModifiedDate', dateTime(topic.modifiedDate));
  if (!blank(topic.modifiedAuthor)) w.leaf('ModifiedAuthor', topic.modifiedAuthor);
  if (topic.dueDate) w.leaf('DueDate', dateTime(topic.dueDate));
  if (!blank(topic.assignedTo)) w.leaf('AssignedTo', topic.assignedTo);
  if (!blank(topic.stage)) w.leaf('Stage', topic.stage);
  if (!blank(topic.description)) w.leaf('Description', topic.description);

  const sn = topic.snippet;
  if (sn && !blank(sn.snippetType) && !blank(sn.reference) && !blank(sn.referenceSchema)) {
    w.open('BimSnippet', { SnippetType: sn.snippetType, [v3 ? 'IsExternal' : 'isExternal']: sn.isExternal });
    w.leaf('Reference', sn.reference).leaf('ReferenceSchema', sn.referenceSchema).close();
  }

  const docs = topic.documentReferences.filter((d) => !blank(d.target));
  if (v3) {
    if (docs.length) {
      w.open('DocumentReferences');
      for (const d of docs) {
        w.open('DocumentReference', { Guid: d.guid && GUID_RE.test(d.guid) ? d.guid.toLowerCase() : newGuid() });
        if (!d.external && GUID_RE.test(d.target!)) w.leaf('DocumentGuid', d.target!.toLowerCase());
        else w.leaf('Url', d.target!);
        if (!blank(d.description)) w.leaf('Description', d.description);
        w.close();
      }
      w.close();
    }
  } else {
    for (const d of docs) {
      w.open('DocumentReference', { Guid: d.guid && GUID_RE.test(d.guid) ? d.guid : undefined, isExternal: d.external });
      w.leaf('ReferencedDocument', d.target!);
      if (!blank(d.description)) w.leaf('Description', d.description);
      w.close();
    }
  }

  const related = topic.relatedTopics.filter((g) => GUID_RE.test(g));
  if (v3) {
    if (related.length) {
      w.open('RelatedTopics');
      for (const g of related) w.empty('RelatedTopic', { Guid: g.toLowerCase() });
      w.close();
    }
  } else for (const g of related) w.empty('RelatedTopic', { Guid: g });

  const vpRefs = topic.viewpoints;
  const comments = topic.comments.filter((c) => !v3 || !blank(c.text) || c.viewpointGuid);
  if (v3) {
    if (comments.length) {
      w.open('Comments');
      for (const c of comments) writeCommentEntry(w, c, version);
      w.close();
    }
    if (vpRefs.length) {
      w.open('Viewpoints');
      for (const r of vpRefs) writeViewpointRef(w, r, version, 'ViewPoint');
      w.close();
    }
    w.close(); // Topic
  } else {
    w.close(); // Topic
    for (const c of comments) writeCommentEntry(w, c, version);
    for (const r of vpRefs) writeViewpointRef(w, r, version, 'Viewpoints');
  }
  w.close();
  return w.toString();
}

function writeViewpointRef(w: W, r: BcfViewpointRef, version: BcfVersion, tag: string): void {
  w.open(tag, { Guid: version === '3.0' ? r.guid.toLowerCase() : r.guid });
  if (r.viewpointFile) w.leaf('Viewpoint', r.viewpointFile);
  if (r.snapshotFile) w.leaf('Snapshot', r.snapshotFile);
  if (r.index !== undefined && Number.isFinite(r.index)) w.leaf('Index', String(Math.round(r.index)));
  w.close();
}

// ---------------------------------------------------------------- container

function uniq(list: Iterable<string | undefined>): string[] {
  const out = new Set<string>();
  for (const s of list) if (!blank(s)) out.add(s);
  return [...out];
}

function writeExtensions(project: BcfProject): string {
  const t = project.topics;
  const e = project.extensions;
  const w = new W();
  w.open('Extensions');
  const lists: Array<[string, string, string[]]> = [
    ['TopicTypes', 'TopicType', uniq([...e.topicTypes, ...t.map((x) => x.topicType)])],
    ['TopicStatuses', 'TopicStatus', uniq([...e.topicStatuses, ...t.map((x) => x.topicStatus)])],
    ['Priorities', 'Priority', uniq([...e.priorities, ...t.map((x) => x.priority)])],
    ['TopicLabels', 'TopicLabel', uniq([...e.topicLabels, ...t.flatMap((x) => x.labels)])],
    ['Users', 'User', uniq([...e.users, ...t.flatMap((x) => [x.creationAuthor, x.modifiedAuthor, x.assignedTo, ...x.comments.map((c) => c.author)])])],
    ['SnippetTypes', 'SnippetType', uniq([...e.snippetTypes, ...t.map((x) => x.snippet?.snippetType)])],
    ['Stages', 'Stage', uniq([...e.stages, ...t.map((x) => x.stage)])],
  ];
  for (const [wrap, item, vals] of lists) {
    if (!vals.length) continue;
    w.open(wrap);
    for (const v of vals) w.leaf(item, v);
    w.close();
  }
  w.close();
  return w.toString();
}

export interface WriteOptions {
  date?: Date;
  compress?: boolean;
  /**
   * Burn the viewer markup (pin, annotations) into a snapshot: returns the new PNG, or null to keep the snapshot as is.
   * Called for each viewpoint whose topic has a pin or which has annotations. Browser only (needs a canvas).
   */
  composeSnapshot?: (topic: BcfTopic, ref: BcfViewpointRef) => Promise<Uint8Array | null>;
}

/**
 * 3D lines of the annotations of a viewpoint (IFC frame): the projected path of a surface shape, the edges of a region. Lines
 * that came from a foreign file (`lines` attachments) are in the viewpoint already and are not repeated.
 */
export function annotationLines(ref: BcfViewpointRef): Array<{ start: [number, number, number]; end: [number, number, number] }> {
  const out: Array<{ start: [number, number, number]; end: [number, number, number] }> = [];
  for (const a of ref.annotations ?? []) {
    if (a.attach?.kind === 'lines') continue;
    for (const [p, q] of attachmentSegments(a.attach)) out.push({ start: p, end: q });
  }
  return out;
}

/**
 * The viewpoint as written: the elements the annotations point at join the selection (merged with what is there), so other
 * tools highlight them, and attached shapes become real 3D `<Lines>` (merged with the viewpoint's own, which stay; the lines
 * of an earlier export of ours are replaced, not doubled).
 */
export function viewpointWithMarkup(vp: BcfViewpoint, ref: BcfViewpointRef): BcfViewpoint {
  let out = vp;
  const extra = annotationGuids(ref.annotations);
  if (extra.length) {
    const have = new Set(vp.selection.map((c) => c.ifcGuid).filter(Boolean));
    const add = extra.filter((g) => !have.has(g)).map((g) => ({ ifcGuid: g }));
    if (add.length) out = { ...out, selection: [...vp.selection, ...add] };
  }
  const gen = annotationLines(ref);
  if (gen.length) {
    const own = new Set(gen.map((l) => segmentKey([l.start, l.end])));
    out = { ...out, lines: [...vp.lines.filter((l) => !own.has(segmentKey([l.start, l.end]))), ...gen] };
  }
  return out;
}

/** Serialise a project as a .bcf / .bcfzip archive of the given version. */
export async function writeBcf(project: BcfProject, version: BcfVersion = '2.1', opts: WriteOptions = {}): Promise<Uint8Array> {
  const enc = new TextEncoder();
  const v3 = version === '3.0';
  const files: ZipInput[] = [];
  const add = (name: string, text: string): void => void files.push({ name, data: enc.encode(text) });

  add('bcf.version', v3
    ? `${XML_DECL}\n<Version VersionId="3.0"/>\n`
    : `${XML_DECL}\n<Version VersionId="2.1">\n  <DetailedVersion>2.1</DetailedVersion>\n</Version>\n`);
  if (v3) add('extensions.xml', writeExtensions(project));
  if (!blank(project.projectId)) {
    const w = new W();
    if (v3) w.open('ProjectInfo');
    else w.open('ProjectExtension');
    if (blank(project.projectName)) w.empty('Project', { ProjectId: project.projectId });
    else w.open('Project', { ProjectId: project.projectId }).leaf('Name', project.projectName).close();
    if (!v3) w.leaf('ExtensionSchema', '');
    w.close();
    add('project.bcfp', w.toString());
  }
  if (v3 && project.documents.length) {
    const w = new W();
    w.open('DocumentInfo').open('Documents');
    for (const d of project.documents) {
      const g = d.guid.toLowerCase();
      w.open('Document', { Guid: g }).leaf('Filename', blank(d.filename) ? g : d.filename);
      if (!blank(d.description)) w.leaf('Description', d.description);
      w.close();
      if (d.data) files.push({ name: `Documents/${g}`, data: d.data });
    }
    w.close().close();
    add('documents.xml', w.toString());
  }

  for (const t of project.topics) {
    const folder = v3 ? t.guid.toLowerCase() : t.guid;
    const refs = viewpointNames(t, version);
    add(`${folder}/markup.bcf`, writeMarkup({ ...t, viewpoints: refs }, version));
    const bases = new Map<string, string>();
    for (const r of refs) {
      if (r.viewpointFile && r.data) add(`${folder}/${r.viewpointFile}`, writeViewpoint(viewpointWithMarkup({ ...r.data, guid: r.guid }, r), version));
      if (r.snapshotFile && r.snapshot) {
        // Burned snapshot under the name the markup gives (what every BCF tool shows); the clean one beside it for us.
        const burned = opts.composeSnapshot && needsBurn(t, r) ? await opts.composeSnapshot(t, r) : null;
        if (burned) {
          const base = baseSnapshotName(r.guid, version);
          bases.set(r.guid, base);
          files.push({ name: `${folder}/${r.snapshotFile}`, data: burned, store: true });
          files.push({ name: `${folder}/${base}`, data: r.snapshot, store: true });
        } else files.push({ name: `${folder}/${r.snapshotFile}`, data: r.snapshot, store: true });
      }
    }
    const side = sidecarJson(t, version, bases);
    if (side) add(`${folder}/${SIDECAR_NAME}`, side);
  }
  return writeZip(files, opts);
}
