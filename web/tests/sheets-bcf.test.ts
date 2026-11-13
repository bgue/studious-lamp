import { describe, expect, it } from 'vitest';
import { parseBcf } from '../src/bcf/parse';
import { writeBcf } from '../src/bcf/write';
import { emptyProject, newGuid } from '../src/bcf/model';
import type { BcfProject, BcfSheetRef, BcfTopic, BcfVersion } from '../src/bcf/model';
import { readSheetRef, sidecarJson } from '../src/bcf/sidecar';
import { readZip } from '../src/bcf/zip';
import { newMarkup } from '../src/markup/model';

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4]);
const PDF = new TextEncoder().encode('%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n');
const SHA = 'ab'.repeat(32);

function sheetProject(version: BcfVersion): { project: BcfProject; docGuid: string; ref: BcfSheetRef } {
  const p = emptyProject(version);
  const docGuid = newGuid();
  p.documents.push({ guid: docGuid, filename: 'Level 1 plan.pdf', data: PDF, sha256: SHA, description: 'Drawing sheet (PDF)' });
  const ref: BcfSheetRef = {
    sha256: SHA, page: 2, name: 'Level 1 plan, page 2', docName: 'Level 1 plan.pdf', title: 'Door clash', bounds: [10, 20, 400, 300],
    markups: [
      newMarkup('cloud', { id: 'm1', number: 1, author: 'a', text: 'check', shape: { points: [[100, 100], [200, 160]], depth: 0 } }),
      newMarkup('callout', { id: 'm2', number: 2, author: 'a', text: 'door', anchor: { kind: 'point', point: [150, 120, 0] }, offset: [0.1, -0.09] }),
    ],
  };
  const t: BcfTopic = {
    guid: newGuid(), topicType: 'Issue', topicStatus: 'Open', title: 'Door clash', labels: [], referenceLinks: [], creationDate: '2026-01-01T00:00:00Z', creationAuthor: 'x',
    headerFiles: [], documentReferences: [{ guid: newGuid(), target: docGuid, external: false, description: 'Level 1 plan.pdf' }], relatedTopics: [], comments: [],
    viewpoints: [{ guid: newGuid(), data: null, snapshot: PNG, snapshotMime: 'image/png', sheet: ref }],
  };
  p.topics.push(t);
  return { project: p, docGuid, ref };
}

describe.each(['2.1', '3.0'] as BcfVersion[])('a sheet viewpoint in BCF %s', (version) => {
  it('writes the PDF into the zip and the DocumentReference to it', async () => {
    const { project } = sheetProject(version);
    const bytes = await writeBcf(project, version);
    const names = readZip(bytes).map((e) => e.name);
    if (version === '3.0') expect(names.some((n) => /^Documents\/[0-9a-f-]{36}$/.test(n))).toBe(true);
    else expect(names).toContain('Documents/Level 1 plan.pdf');
    expect(names.some((n) => /xray-markup\.json$/.test(n))).toBe(true);
    expect(names.some((n) => /\.png$/.test(n))).toBe(true);
    // no 3D viewpoint file: the viewpoint is a snapshot of a sheet
    expect(names.some((n) => /\.bcfv$/.test(n))).toBe(false);
  });

  it('round trips: the reference, the PDF bytes, the sheet record and its shapes', async () => {
    const { project, ref } = sheetProject(version);
    const back = await parseBcf(await writeBcf(project, version));
    const t = back.topics[0]!;
    expect(t.documentReferences).toHaveLength(1);
    expect(t.documentReferences[0]!.external).toBe(false);
    const doc = back.documents.find((d) => d.guid === t.documentReferences[0]!.target);
    expect(doc).toBeTruthy();
    expect(doc!.filename).toBe('Level 1 plan.pdf');
    expect(Array.from(doc!.data!)).toEqual(Array.from(PDF));
    const v = t.viewpoints[0]!;
    expect(v.snapshot).toBeTruthy();
    expect(v.sheet).toBeTruthy();
    expect(v.sheet!.sha256).toBe(SHA);
    expect(v.sheet!.page).toBe(2);
    expect(v.sheet!.name).toBe(ref.name);
    expect(v.sheet!.bounds).toEqual(ref.bounds);
    expect(v.sheet!.markups!.map((m) => [m.kind, m.shape?.points ?? m.anchor!.point])).toEqual(ref.markups!.map((m) => [m.kind, m.shape?.points ?? m.anchor!.point]));
    // and it writes again the same way
    const again = await parseBcf(await writeBcf(back, version));
    expect(again.topics[0]!.viewpoints[0]!.sheet!.sha256).toBe(SHA);
    expect(again.documents).toHaveLength(1);
  });
});

describe('the sheet record of the side file', () => {
  it('is written whenever a viewpoint has one', () => {
    const { project } = sheetProject('3.0');
    const json = JSON.parse(sidecarJson(project.topics[0]!, '3.0')!) as { viewpoints: Record<string, { sheet?: BcfSheetRef }> };
    const v = Object.values(json.viewpoints)[0]!;
    expect(v.sheet!.sha256).toBe(SHA);
    expect(v.sheet!.bounds).toEqual([10, 20, 400, 300]);
  });

  it('is refused when it does not name a PDF and a page', () => {
    expect(readSheetRef(null)).toBeNull();
    expect(readSheetRef({ sha256: 'xyz', page: 1 })).toBeNull();
    expect(readSheetRef({ sha256: SHA, page: 0 })).toBeNull();
    expect(readSheetRef({ sha256: SHA, page: 3, bounds: [1, 2, 3, 4], markups: [{ kind: 'nope' }] })!.markups).toEqual([]);
  });
});
