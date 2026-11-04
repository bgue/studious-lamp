// Validates generated BCF XML against the official buildingSMART XSDs (tests/fixtures/bcf/xsd, fetched from
// github.com/buildingSMART/BCF-XML tags v2.1 and v3.0) with lxml. Skipped when python3 or lxml is unavailable.

import { describe, expect, it } from 'vitest';
import { parseBcf } from '../src/bcf/parse';
import { writeBcf } from '../src/bcf/write';
import { readZip } from '../src/bcf/zip';
import { emptyProject, newGuid } from '../src/bcf/model';
import type { BcfProject, BcfVersion } from '../src/bcf/model';
import { FIXTURES, G1, G2, fixtureZip, nodeMod } from './bcf-helpers';

const { spawnSync } = nodeMod('node:child_process');
const { mkdirSync, mkdtempSync, rmSync, writeFileSync } = nodeMod('node:fs');
const { tmpdir } = nodeMod('node:os');
const { dirname, join } = nodeMod('node:path');


const SCRIPT: string = join(FIXTURES, 'validate_xsd.py');
const hasLxml = ((): boolean => {
  try {
    return spawnSync('python3', ['-I', '-c', 'import lxml.etree'], { encoding: 'utf8' }).status === 0;
  } catch {
    return false;
  }
})();

async function unpack(bytes: Uint8Array, dir: string): Promise<void> {
  for (const e of readZip(bytes)) {
    if (e.isDirectory) continue;
    const p = join(dir, e.name);
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, await e.read());
  }
}

function validate(dirs: string[]): { status: number | null; out: string } {
  const r = spawnSync('python3', ['-I', SCRIPT, ...dirs], { encoding: 'utf8' });
  return { status: r.status, out: `${r.stdout}${r.stderr}` };
}

function project(): BcfProject {
  const p = emptyProject('2.1');
  p.projectId = 'p1';
  p.projectName = 'Name';
  const mk = (title: string, rich: boolean) => {
    const vpGuid = newGuid();
    return {
      guid: newGuid(), topicType: 'Issue', topicStatus: 'Open', title, priority: rich ? 'High' : undefined, labels: rich ? ['a', 'b'] : [], referenceLinks: rich ? ['https://x.y/z'] : [],
      creationDate: new Date().toISOString(), creationAuthor: 'me', modifiedDate: rich ? new Date().toISOString() : undefined, modifiedAuthor: rich ? 'you' : undefined,
      assignedTo: rich ? 'you' : undefined, stage: rich ? 'S' : undefined, description: rich ? 'Described' : undefined,
      headerFiles: rich ? [{ filename: 'm.ifc', date: new Date().toISOString(), isExternal: true, ifcProject: '0J$yPqHBD12v72Y4tGsLzu' }] : [],
      documentReferences: rich ? [{ guid: newGuid(), target: 'https://x.y/d.pdf', external: true, description: 'd' }] : [],
      relatedTopics: [],
      comments: rich ? [{ guid: newGuid(), date: new Date().toISOString(), author: 'me', text: 'hello', viewpointGuid: vpGuid }, { guid: newGuid(), date: new Date().toISOString(), author: 'me', text: 'plain' }] : [],
      viewpoints: rich ? [{
        guid: vpGuid,
        data: {
          guid: vpGuid,
          camera: { kind: 'perspective' as const, position: [1, 2, 3] as [number, number, number], direction: [0, 1, 0] as [number, number, number], up: [0, 0, 1] as [number, number, number], fov: 45, aspect: 16 / 9 },
          selection: [{ ifcGuid: G1 }], visibility: { defaultVisibility: false, exceptions: [{ ifcGuid: G1 }, { ifcGuid: G2 }], hints: { spacesVisible: false, openingsVisible: true } },
          coloring: [{ color: 'FF0000', components: [{ ifcGuid: G1 }] }, { color: '00FF0080', components: [{ ifcGuid: G2 }] }],
          clipping: [{ location: [0, 0, 1] as [number, number, number], direction: [0, 0, 1] as [number, number, number] }], lines: [{ start: [0, 0, 0] as [number, number, number], end: [1, 1, 1] as [number, number, number] }],
        },
        snapshot: new Uint8Array([0x89, 0x50, 0x4e, 0x47, 1, 2, 3, 4]), snapshotMime: 'image/png' as const,
      }, {
        guid: newGuid(),
        data: { guid: newGuid(), camera: { kind: 'orthogonal' as const, position: [0, 0, 9] as [number, number, number], direction: [0, 0, -1] as [number, number, number], up: [0, 1, 0] as [number, number, number], viewToWorldScale: 10, aspect: 1.5 }, selection: [], visibility: { defaultVisibility: true, exceptions: [] }, coloring: [], clipping: [], lines: [] },
      }] : [],
    };
  };
  p.topics.push(mk('rich', true), mk('sparse', false));
  return p;
}

describe.skipIf(!hasLxml)('generated BCF validates against the official XSDs', () => {
  it.each(['2.1', '3.0'] as BcfVersion[])('BCF %s written by this viewer', async (v) => {
    const dir = mkdtempSync(join(tmpdir(), `bcf-xsd-${v}-`));
    try {
      await unpack(await writeBcf(project(), v), dir);
      const r = validate([dir]);
      expect(r.out).toMatch(/0 failed/);
      expect(r.status).toBe(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it.each([['bcf21', '2.1'], ['bcf30', '3.0']] as Array<[string, BcfVersion]>)('fixture %s re-written as %s keeps validating', async (fx, v) => {
    const dir = mkdtempSync(join(tmpdir(), `bcf-xsd-fx-${v}-`));
    try {
      const p = await parseBcf(await fixtureZip(fx));
      await unpack(await writeBcf(p, v), dir);
      const r = validate([dir]);
      expect(r.out).toMatch(/0 failed/);
      expect(r.status).toBe(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('the hand written fixtures themselves validate', () => {
    const r = validate([join(FIXTURES, 'bcf21'), join(FIXTURES, 'bcf30')]);
    expect(r.out).toMatch(/0 failed/);
    expect(r.status).toBe(0);
  });

  it('the validator really rejects bad documents', () => {
    const dir = mkdtempSync(join(tmpdir(), 'bcf-xsd-bad-'));
    try {
      writeFileSync(join(dir, 'bcf.version'), '<Version VersionId="3.0"/>');
      mkdirSync(join(dir, 'g'));
      writeFileSync(join(dir, 'g', 'markup.bcf'), '<Markup><Topic Guid="not-a-guid" TopicType="a" TopicStatus="b"><Title>t</Title></Topic></Markup>');
      expect(validate([dir]).status).toBe(1);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
