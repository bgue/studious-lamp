import { describe, expect, it } from 'vitest';
import { parseBcf, parseViewpoint } from '../src/bcf/parse';
import { writeBcf, writeMarkup, writeViewpoint } from '../src/bcf/write';
import { emptyProject, newGuid } from '../src/bcf/model';
import type { BcfProject, BcfTopic, BcfVersion, BcfViewpoint } from '../src/bcf/model';
import { readZip } from '../src/bcf/zip';
import { G1, G2, fixtureZip } from './bcf-helpers';

const SLACK = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.['XRAY_PERF'] === '1' ? 1 : 5;

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4, 5, 6, 7, 8]);

function sampleViewpoint(): BcfViewpoint {
  return {
    guid: newGuid(),
    camera: { kind: 'perspective', position: [1.5, -8.25, 3], direction: [0, 0.9, -0.1], up: [0, 0.1, 0.9], fov: 55, aspect: 1.6 },
    selection: [{ ifcGuid: G1 }, { ifcGuid: G2 }],
    visibility: { defaultVisibility: true, exceptions: [{ ifcGuid: G2 }], hints: { spacesVisible: false, openingsVisible: true } },
    coloring: [{ color: 'FF8800', components: [{ ifcGuid: G1 }] }],
    clipping: [{ location: [0, 0, 2.5], direction: [0, 0, 1] }],
    lines: [{ start: [0, 0, 0], end: [1, 2, 3] }],
  };
}

function sampleProject(): BcfProject {
  const p = emptyProject('2.1');
  p.projectId = 'proj-1';
  p.projectName = 'Test <project>';
  const vp = sampleViewpoint();
  const t: BcfTopic = {
    guid: newGuid(), topicType: 'Clash', topicStatus: 'In Progress', title: 'A & B < C', priority: 'High', index: 2,
    labels: ['MEP', 'Level 1'], referenceLinks: ['https://example.org/1'], creationDate: '2024-05-06T07:08:09.123Z', creationAuthor: 'a@b.c',
    modifiedDate: '2024-05-07T00:00:00Z', modifiedAuthor: 'd@e.f', dueDate: '2024-06-01T00:00:00Z', assignedTo: 'g@h.i', stage: 'Design',
    description: 'Line 1\nLine 2 "quoted" äöü \u{1F600}',
    headerFiles: [{ filename: 'a.ifc', date: '2024-01-01T00:00:00Z', isExternal: true, ifcProject: '0J$yPqHBD12v72Y4tGsLzu' }],
    documentReferences: [{ guid: newGuid(), target: 'https://example.org/spec.pdf', external: true, description: 'spec' }],
    relatedTopics: [],
    comments: [],
    viewpoints: [{ guid: vp.guid, data: vp, snapshot: PNG, snapshotMime: 'image/png' }],
  };
  t.comments.push({ guid: newGuid(), date: '2024-05-06T08:00:00Z', author: 'x@y.z', text: 'First <b>comment</b>', viewpointGuid: vp.guid });
  t.comments.push({ guid: newGuid(), date: '2024-05-06T09:00:00Z', author: 'x@y.z', text: 'Second' });
  p.topics.push(t, {
    ...t, guid: newGuid(), title: 'Second topic', labels: [], comments: [], viewpoints: [], documentReferences: [], referenceLinks: [], relatedTopics: [t.guid],
  });
  return p;
}

describe.each(['2.1', '3.0'] as BcfVersion[])('write then parse, BCF %s', (version) => {
  it('round trips topics, comments, viewpoints and snapshots', async () => {
    const src = sampleProject();
    const bytes = await writeBcf(src, version);
    const back = await parseBcf(bytes);
    expect(back.warnings).toEqual([]);
    expect(back.versionId).toBe(version);
    expect(back.projectId).toBe('proj-1');
    expect(back.projectName).toBe('Test <project>');
    expect(back.topics).toHaveLength(2);
    const a = src.topics[0]!;
    const b = back.topics.find((t) => t.guid === a.guid)!;
    for (const k of ['topicType', 'topicStatus', 'title', 'priority', 'index', 'creationDate', 'creationAuthor', 'modifiedDate', 'modifiedAuthor', 'dueDate', 'assignedTo', 'stage', 'description'] as const) {
      expect(b[k], k).toEqual(a[k]);
    }
    expect(b.labels).toEqual(a.labels);
    expect(b.referenceLinks).toEqual(a.referenceLinks);
    expect(b.headerFiles).toEqual(a.headerFiles);
    expect(b.documentReferences).toMatchObject([{ target: 'https://example.org/spec.pdf', external: true, description: 'spec' }]);
    expect(b.comments.map((c) => [c.guid, c.date, c.author, c.text, c.viewpointGuid])).toEqual(a.comments.map((c) => [c.guid, c.date, c.author, c.text, c.viewpointGuid]));
    expect(back.topics.find((t) => t.title === 'Second topic')!.relatedTopics).toEqual([a.guid]);
    const va = a.viewpoints[0]!;
    const vb = b.viewpoints[0]!;
    expect(vb.guid).toBe(va.guid);
    expect(Array.from(vb.snapshot!)).toEqual(Array.from(PNG));
    const d = vb.data!;
    expect(d.camera).toMatchObject({ kind: 'perspective', position: [1.5, -8.25, 3], direction: [0, 0.9, -0.1], up: [0, 0.1, 0.9], fov: 55 });
    if (version === '3.0') expect(d.camera?.aspect).toBe(1.6);
    expect(d.selection).toEqual(va.data!.selection);
    expect(d.visibility).toEqual(va.data!.visibility);
    expect(d.coloring).toEqual(va.data!.coloring);
    expect(d.clipping).toEqual(va.data!.clipping);
    expect(d.lines).toEqual(va.data!.lines);
  });

  it('writes the container layout the BCF guide asks for', async () => {
    const src = sampleProject();
    const names = readZip(await writeBcf(src, version)).map((e) => e.name);
    const g = src.topics[0]!.guid;
    expect(names).toContain('bcf.version');
    expect(names).toContain(`${g}/`);
    expect(names).toContain(`${g}/markup.bcf`);
    expect(names.some((n) => n.startsWith(`${g}/`) && n.endsWith('.bcfv'))).toBe(true);
    expect(names.some((n) => n.startsWith(`${g}/`) && n.endsWith('.png'))).toBe(true);
    expect(names.includes('extensions.xml')).toBe(version === '3.0');
    if (version === '2.1') expect(names).toContain(`${g}/viewpoint.bcfv`);
    expect(names.every((n) => !n.includes('\\'))).toBe(true);
  });

  it('round trips the official-style fixtures', async () => {
    const fx = await parseBcf(await fixtureZip(version === '2.1' ? 'bcf21' : 'bcf30'));
    const back = await parseBcf(await writeBcf(fx, version));
    expect(back.warnings).toEqual([]);
    expect(back.topics.map((t) => t.title).sort()).toEqual(fx.topics.map((t) => t.title).sort());
    const f = fx.topics.find((t) => t.viewpoints.length)!;
    const g = back.topics.find((t) => t.guid === f.guid)!;
    expect(g.viewpoints[0]!.data!.selection).toEqual(f.viewpoints[0]!.data!.selection);
    expect(g.viewpoints[0]!.data!.coloring.map((c) => c.color)).toEqual(f.viewpoints[0]!.data!.coloring.map((c) => c.color));
    expect(g.comments.length).toBe(f.comments.length);
  });
});

describe('writer details', () => {
  it('clamps the 2.1 field of view and omits AspectRatio there', () => {
    const vp = sampleViewpoint();
    vp.camera!.fov = 90;
    const x21 = writeViewpoint(vp, '2.1');
    expect(x21).toContain('<FieldOfView>60</FieldOfView>');
    expect(x21).not.toContain('AspectRatio');
    const x30 = writeViewpoint(vp, '3.0');
    expect(x30).toContain('<FieldOfView>90</FieldOfView>');
    expect(x30).toContain('<AspectRatio>1.6</AspectRatio>');
  });

  it('drops invalid IfcGuids and lower-cases 3.0 guids', () => {
    const vp = sampleViewpoint();
    vp.selection.push({ ifcGuid: 'short' });
    const x = writeViewpoint({ ...vp, guid: 'ABCDEF01-0000-4000-8000-000000000001' }, '3.0');
    expect(x).not.toContain('short');
    expect(x).toContain('Guid="abcdef01-0000-4000-8000-000000000001"');
    expect(parseViewpoint(x).selection).toHaveLength(2);
  });

  it('writes required 3.0 values even for sparse topics', () => {
    const t = sampleProject().topics[0]!;
    const sparse: BcfTopic = { ...t, topicType: '', topicStatus: '', title: '', creationAuthor: '', creationDate: '', priority: undefined, description: '', labels: [], comments: [{ guid: newGuid(), date: '', author: '', text: '' }], viewpoints: [] };
    const x = writeMarkup(sparse, '3.0');
    expect(x).toContain('TopicType="Issue"');
    expect(x).toContain('TopicStatus="Open"');
    expect(x).toContain('<Title>Untitled</Title>');
    expect(x).toContain('<CreationAuthor>unknown</CreationAuthor>');
    expect(x.match(/<Description>/g)).toHaveLength(1); // only the document reference's
    expect(x).not.toContain('<Comments>');
  });

  it('an orthogonal camera survives a round trip', () => {
    const vp = sampleViewpoint();
    vp.camera = { kind: 'orthogonal', position: [1, 2, 3], direction: [0, 0, -1], up: [0, 1, 0], viewToWorldScale: 20, aspect: 2 };
    for (const v of ['2.1', '3.0'] as const) {
      const back = parseViewpoint(writeViewpoint(vp, v));
      expect(back.camera).toMatchObject({ kind: 'orthogonal', viewToWorldScale: 20 });
    }
  });

  it('performance: 100 topics with 2000 components write and parse quickly', async () => {
    const p = emptyProject('2.1');
    const base = sampleProject().topics[0]!;
    for (let i = 0; i < 100; i++) {
      const vp = sampleViewpoint();
      vp.selection = Array.from({ length: 2000 }, (_, k) => ({ ifcGuid: (`n${i}_${k}`).padEnd(22, 'A') }));
      p.topics.push({ ...base, guid: newGuid(), viewpoints: [{ guid: vp.guid, data: vp }], comments: [] });
    }
    const t0 = performance.now();
    const bytes = await writeBcf(p, '3.0');
    const back = await parseBcf(bytes);
    const ms = performance.now() - t0;
    expect(back.topics).toHaveLength(100);
    expect(back.topics[7]!.viewpoints[0]!.data!.selection).toHaveLength(2000);
    expect(ms).toBeLessThan(1500 * SLACK);
  });
});
