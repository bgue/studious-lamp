import { describe, expect, it } from 'vitest';
import { parseBcf, parseMarkup, parseViewpoint } from '../src/bcf/parse';
import { G1, G2, fixtureText, fixtureZip } from './bcf-helpers';

describe('BCF 2.1 fixture', () => {
  it('parses topics, comments, viewpoints and the snapshot', async () => {
    const p = await parseBcf(await fixtureZip('bcf21'));
    expect(p.versionId).toBe('2.1');
    expect(p.warnings).toEqual([]);
    expect(p.topics).toHaveLength(2);
    const t = p.topics.find((x) => x.guid === '3b6c6d0e-6a53-4f47-9f0c-7c1f8b3c9a11')!;
    expect(t).toMatchObject({
      topicType: 'Clash', topicStatus: 'Open', title: 'Duct clashes with wall & beam', priority: 'High', index: 3,
      creationDate: '2021-03-04T10:15:30+01:00', creationAuthor: 'alice@example.org', modifiedAuthor: 'bob@example.org',
      assignedTo: 'bob@example.org', stage: 'Design',
    });
    expect(t.labels).toEqual(['Architecture', 'MEP']);
    expect(t.referenceLinks).toEqual(['https://example.org/issues/42']);
    expect(t.description).toBe('The duct crosses the wall at level 1.\nSee viewpoint.');
    expect(t.headerFiles[0]).toMatchObject({ filename: 'AC20-FZK-Haus.ifc', ifcProject: '0J$yPqHBD12v72Y4tGsLzu', isExternal: true });
    expect(t.snippet).toMatchObject({ snippetType: 'ifc', isExternal: false, reference: 'snippet.ifc' });
    expect(t.documentReferences).toEqual([{ guid: 'c0b4b6f4-1e0e-4c19-8c43-7b6e0e6d7a01', target: 'https://example.org/spec.pdf', external: true, description: 'Specification' }]);
    expect(t.relatedTopics).toEqual(['8e5f1d52-0a6e-4b88-a6a3-0f9b7d2c4e22']);
    expect(t.comments.map((c) => [c.author, c.text, c.viewpointGuid])).toEqual([
      ['alice@example.org', 'Please check.', 'f4e8c1a0-2b7d-4a59-b3c6-9d8e7f6a5b41'],
      ['bob@example.org', 'On it.', undefined],
    ]);
    const v = t.viewpoints[0]!;
    expect(v.guid).toBe('f4e8c1a0-2b7d-4a59-b3c6-9d8e7f6a5b41');
    expect(v.snapshot?.length).toBeGreaterThan(20);
    expect(v.snapshotMime).toBe('image/png');
    const vp = v.data!;
    expect(vp.camera).toMatchObject({ kind: 'orthogonal', position: [10, -20, 30], direction: [0, 1, 0], up: [0, 0, 1], viewToWorldScale: 12.5 });
    expect(vp.camera?.aspect).toBeUndefined();
    expect(vp.selection.map((c) => c.ifcGuid)).toEqual([G1, G2, '0000000000000000000000']);
    expect(vp.selection[0]).toMatchObject({ originatingSystem: 'Test', authoringToolId: '263' });
    expect(vp.visibility).toEqual({ defaultVisibility: false, exceptions: [{ ifcGuid: G1 }, { ifcGuid: G2 }], hints: { spacesVisible: false, spaceBoundariesVisible: false, openingsVisible: true } });
    expect(vp.coloring).toEqual([{ color: 'FF0000', components: [{ ifcGuid: G1 }] }, { color: '0000FF80', components: [{ ifcGuid: G2 }] }]);
    expect(vp.clipping).toEqual([{ location: [0, 0, 3], direction: [0, 0, 1] }]);
    expect(vp.lines).toHaveLength(1);
  });

  it('reads a topic without comments or viewpoints', async () => {
    const p = await parseBcf(await fixtureZip('bcf21'));
    const t = p.topics.find((x) => x.title === 'Missing fire rating')!;
    expect(t.comments).toEqual([]);
    expect(t.viewpoints).toEqual([]);
    expect(t.topicStatus).toBe('');
  });

  it('works on stored and deflated archives alike', async () => {
    const a = await parseBcf(await fixtureZip('bcf21', { compress: false }));
    const b = await parseBcf(await fixtureZip('bcf21', { compress: true }));
    expect(a.topics.length).toBe(b.topics.length);
    expect(b.topics[0]!.viewpoints[0]?.data).toEqual(a.topics[0]!.viewpoints[0]?.data);
  });
});

describe('BCF 3.0 fixture', () => {
  it('parses extensions, project, documents and the wrapped topic form', async () => {
    const p = await parseBcf(await fixtureZip('bcf30'));
    expect(p.versionId).toBe('3.0');
    expect(p.warnings).toEqual([]);
    expect(p.projectId).toBe('p-1234');
    expect(p.projectName).toBe('Sample house');
    expect(p.extensions.topicTypes).toEqual(['Issue', 'Clash']);
    expect(p.extensions.users).toEqual(['dave@example.org']);
    expect(p.extensions.stages).toEqual(['Construction']);
    expect(p.documents).toHaveLength(1);
    expect(p.documents[0]).toMatchObject({ filename: 'notes.txt', description: 'Site notes' });
    expect(new TextDecoder().decode(p.documents[0]!.data)).toBe('site notes\n');
    const t = p.topics[0]!;
    expect(t).toMatchObject({ serverAssignedId: 'PRJ-7', topicType: 'Issue', topicStatus: 'Open', priority: 'Critical', creationDate: '2022-06-01T12:00:00.250Z' });
    expect(t.labels).toEqual(['Structure', 'Level 2']);
    expect(t.referenceLinks).toEqual(['https://example.org/t/7']);
    expect(t.headerFiles[0]).toMatchObject({ filename: 'AC20-FZK-Haus.ifc', isExternal: true });
    expect(t.documentReferences[0]).toMatchObject({ target: '0a1b2c3d-4e5f-4a7b-8c9d-0e1f2a3b4c5d', external: false });
    expect(t.comments[0]).toMatchObject({ text: 'Measured on site.', viewpointGuid: 'd4e5f6a7-b8c9-4d0e-9f2a-3b4c5d6e7f80' });
    const vp = t.viewpoints[0]!.data!;
    expect(vp.camera).toMatchObject({ kind: 'perspective', fov: 60, position: [5.5, -12, 4] });
    expect(vp.camera?.aspect).toBeCloseTo(16 / 9, 9);
    expect(vp.visibility).toMatchObject({ defaultVisibility: true, hints: { spacesVisible: false, openingsVisible: false } });
    expect(vp.visibility?.exceptions).toEqual([{ ifcGuid: G2 }]);
    expect(vp.coloring).toEqual([{ color: '00FF00', components: [{ ifcGuid: G1 }] }]);
    expect(vp.bitmapsIgnored).toBe(1);
  });
});

describe('parser robustness', () => {
  it('reports a malformed topic and keeps the others', async () => {
    const { writeZip } = await import('../src/bcf/zip');
    const e = new TextEncoder();
    const zip = await writeZip([
      { name: 'bcf.version', data: e.encode('<Version VersionId="2.1"/>') },
      { name: 'aaaaaaaa-0000-4000-8000-000000000001/markup.bcf', data: e.encode('<Markup><Topic Guid="aaaaaaaa-0000-4000-8000-000000000001"><Title>ok</Title></Topic></Markup>') },
      { name: 'aaaaaaaa-0000-4000-8000-000000000002/markup.bcf', data: e.encode('<Markup><Topic') },
      { name: 'aaaaaaaa-0000-4000-8000-000000000003/markup.bcf', data: e.encode('<Markup><Topic Guid="aaaaaaaa-0000-4000-8000-000000000003"><Title>vp</Title></Topic><Viewpoints Guid="bbbbbbbb-0000-4000-8000-000000000001"><Viewpoint>gone.bcfv</Viewpoint></Viewpoints></Markup>') },
    ]);
    const p = await parseBcf(zip);
    expect(p.topics.map((t) => t.title)).toEqual(['ok', 'vp']);
    expect(p.warnings.some((w) => w.includes('000000000002/markup.bcf'))).toBe(true);
    expect(p.topics[1]!.viewpoints[0]!.problem).toMatch(/missing/);
  });

  it('reads old style viewpoint.bcfv without a Viewpoints list', async () => {
    const { writeZip } = await import('../src/bcf/zip');
    const e = new TextEncoder();
    const zip = await writeZip([
      { name: 'bcf.version', data: e.encode('<Version VersionId="2.0"><DetailedVersion>2.0</DetailedVersion></Version>') },
      { name: 'aaaaaaaa-0000-4000-8000-000000000001/markup.bcf', data: e.encode('<Markup><Topic Guid="aaaaaaaa-0000-4000-8000-000000000001"><Title>t</Title></Topic></Markup>') },
      { name: 'aaaaaaaa-0000-4000-8000-000000000001/viewpoint.bcfv', data: e.encode(fixtureText('bcf21/3b6c6d0e-6a53-4f47-9f0c-7c1f8b3c9a11/viewpoint.bcfv')) },
    ]);
    const p = await parseBcf(zip);
    expect(p.versionId).toBe('2.0');
    expect(p.topics[0]!.viewpoints[0]!.data?.camera?.kind).toBe('orthogonal');
  });

  it('rejects a non-zip and wrong roots', async () => {
    await expect(parseBcf(new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]))).rejects.toThrow();
    expect(() => parseMarkup('<Foo/>')).toThrow(/Markup/);
    expect(() => parseViewpoint('<Foo/>')).toThrow(/VisualizationInfo/);
    expect(() => parseMarkup('<Markup/>')).toThrow(/Topic/);
  });
});
