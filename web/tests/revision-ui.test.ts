// The pure parts of the revision walk UI (ticket T4): the RevisionStatus hand-off to the save plan, the card text, the ghost storage,
// the attachment adapter, the PanelHost adapter, the key table, and the rule that none of it is a setting. The panel, banner and
// controller are checked by bench/smoke-ifc-save-revision.mjs.
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';
import { diffModels } from '../src/revision/diff';
import { attachmentHost, retargetSet, retargetTopic, setGuids, topicGuids } from '../src/revision/attachHost';
import { changeRows, geometryText, moveText, MAX_PROP_ROWS } from '../src/revision/card';
import { baseToViewer, boxEdges, decodeGhosts, encodeGhosts, meshOfElement, nextGhostMode } from '../src/revision/ghost';
import type { GhostMesh } from '../src/revision/ghost';
import { REVISION_ACTIONS, REVISION_WALK_KEYS } from '../src/revision/keys';
import { revisionStatusMap } from '../src/revision/status';
import { newSession, parseSession } from '../src/revision/session';
import type { DiffEntry, ModelSnapshot, RevisionDiff, RevisionSession } from '../src/revision/types';
import { rightSidebarPanelHost } from '../src/ui/panelHost';
import type { BcfTopic } from '../src/bcf/model';
import type { MarkupSet } from '../src/markup/model';
import { fzk1, fzk2, loadIfc, readTruth, WEB } from './revision-helpers';

let v1: ModelSnapshot, v2: ModelSnapshot, diff: RevisionDiff;
beforeAll(async () => {
  [v1, v2] = (await Promise.all([loadIfc(fzk1()), loadIfc(fzk2())])).map((l) => l.snap) as [ModelSnapshot, ModelSnapshot];
  diff = diffModels(v1, v2);
}, 120000);

describe('RevisionStatus hand-off (extra.revision of the save plan)', () => {
  it('gives every head element its category, unchanged for the rest, and the baseline name', () => {
    const session = newSession({ base: v1.identity, head: v2.identity, baseName: 'AC20-FZK-Haus.ifc', diff });
    const m = revisionStatusMap(session, v2.globalId);
    expect(m.size).toBe(v2.globalId.length);
    const count = (s: string): number => [...m.values()].filter((x) => x.status === s).length;
    expect(count('new')).toBe(3);
    expect(count('changed')).toBe(14);
    expect(count('rematched')).toBe(6);
    expect(count('unchanged')).toBe(v2.globalId.length - 23);
    expect([...m.values()].every((x) => x.baseline === 'AC20-FZK-Haus.ifc')).toBe(true);
  });
  it('has no entry for a deleted element (it is not in the head file)', () => {
    const session = newSession({ base: v1.identity, head: v2.identity, diff });
    const m = revisionStatusMap(session, v2.globalId);
    for (const e of diff.entries.filter((x) => x.category === 'deleted')) { expect(m.has(e.base!)).toBe(false); expect(m.has(e.key)).toBe(false); }
  });
  it('uses the head GlobalId of a rematch, not the base one', () => {
    const session = newSession({ base: v1.identity, head: v2.identity, diff });
    const m = revisionStatusMap(session, v2.globalId);
    const e = diff.entries.find((x) => x.category === 'rematched')!;
    expect(m.get(e.head!)?.status).toBe('rematched');
    expect(m.has(e.base!)).toBe(false);
  });
  it('works from a session read back from storage', () => {
    const session = newSession({ base: v1.identity, head: v2.identity, diff });
    const back = parseSession(JSON.parse(JSON.stringify(session))).session!;
    expect(revisionStatusMap(back, v2.globalId)).toEqual(revisionStatusMap(session, v2.globalId));
  });
});

describe('decisions keep an edit so a resumed walk proposes it again', () => {
  it('round-trips the edited codes through parseSession', () => {
    const s = newSession({ base: v1.identity, head: v2.identity, diff }) as RevisionSession;
    s.decisions['a'] = { key: 'a', verdict: 'accepted', classification: 'edited', edited: { discipline: 'ARC', subDiscipline: null, division: '08' }, at: '2026-01-01T00:00:00Z', by: 'x' };
    const back = parseSession(JSON.parse(JSON.stringify(s))).session!;
    expect(back.decisions['a']!.edited).toEqual({ discipline: 'ARC', subDiscipline: null, division: '08' });
  });
});

describe('card text', () => {
  it('says how far and in which direction an element moved', () => {
    expect(moveText([0.005, 0, 0], 0.005)).toBe('moved 5 mm east');
    expect(moveText([0.0057, 0.0057, 0], 0.008)).toBe('moved 8 mm north-east');
    expect(moveText([0, -0.25, 0], 0.25)).toBe('moved 250 mm south');
    expect(moveText([0, 0, 0.02], 0.02)).toBe('moved 20 mm up');
    expect(moveText([0.0, 0.0, 1.5], 1.5)).toBe('moved 1.50 m up');
    expect(moveText([0.003, 0, -0.003], 0.0042)).toBe('moved 4.2 mm east and down');
    expect(moveText(undefined, undefined, true)).toBe('turned');
    expect(moveText([0.01, 0, 0], 0.01, true)).toBe('turned and moved 10 mm east');
  });
  it('lists the rows of the fzk-v2 changes: placement, geometry, class, type and properties', () => {
    const truth = readTruth();
    const bi = new Map(v1.globalId.map((g, i) => [g, i])), hi = new Map(v2.globalId.map((g, i) => [g, i]));
    const rowsOf = (e: DiffEntry): ReturnType<typeof changeRows> => changeRows(e, v1, v2, bi.get(e.base!), hi.get(e.head!));
    const byFlag = (f: string): DiffEntry => diff.entries.find((e) => e.flags.includes(f as never))!;
    const place = rowsOf(diff.entries.find((e) => e.flags.includes('placement') && e.move !== undefined && e.move < 0.01)!);
    expect(place[0]).toMatchObject({ flag: 'placement' });
    expect(place[0]!.text).toMatch(/^moved 5 mm /);
    expect(rowsOf(byFlag('geometry'))[0]!.text).toMatch(/area [+−]?\d+ %/);
    expect(rowsOf(byFlag('class'))[0]).toMatchObject({ flag: 'class' });
    expect(rowsOf(byFlag('class'))[0]!.before).not.toBe(rowsOf(byFlag('class'))[0]!.after);
    expect(rowsOf(byFlag('type'))[0]).toMatchObject({ flag: 'type' });
    expect(rowsOf(byFlag('properties'))[0]).toMatchObject({ flag: 'properties', label: 'Pset_WallCommon.ThermalTransmittance', before: '1.5', after: '0.9' });
    expect(truth.changes.length).toBe(diff.entries.length);
  });
  it('shows at most 8 property rows and then "n more"', () => {
    const e: DiffEntry = { key: 'k', category: 'changed', flags: ['properties'], classifyAffected: false, props: Array.from({ length: 11 }, (_, i) => ({ key: `P.${i}`, before: i, after: i + 1 })) };
    const rows = changeRows(e, null, null, undefined, undefined);
    expect(rows).toHaveLength(MAX_PROP_ROWS + 1);
    expect(rows.at(-1)!.text).toBe('3 more');
  });
  it('describes a geometry change in percent', () => {
    const e = diff.entries.find((x) => x.flags.includes('geometry'))!;
    const t = geometryText(v1, v1.globalId.indexOf(e.base!), v2, v2.globalId.indexOf(e.head!));
    expect(t).toMatch(/area/);
  });
});

describe('ghost storage', () => {
  const mesh = (gid: string, n: number): GhostMesh => ({
    gid,
    positions: Float32Array.from({ length: n * 3 }, (_, i) => 12.3456 + Math.sin(i) * 3.2 + (i % 3) * 0.7),
    index: Uint32Array.from({ length: n - (n % 3) }, (_, i) => i % n),
  });
  it('keeps positions within 0.1 mm and the index exactly', () => {
    const a = mesh('A', 30), b = mesh('B', 9);
    const { data, dropped } = encodeGhosts([a, b]);
    expect(dropped).toEqual([]);
    const back = decodeGhosts(data);
    expect(back.map((m) => m.gid).sort()).toEqual(['A', 'B']);
    const got = back.find((m) => m.gid === 'A')!;
    expect(Array.from(got.index)).toEqual(Array.from(a.index));
    let worst = 0;
    a.positions.forEach((v, i) => { worst = Math.max(worst, Math.abs(v - got.positions[i]!)); });
    expect(worst).toBeLessThan(0.0001 + 1e-5);
  });
  it('drops the largest meshes first when over the cap, and says which', () => {
    const small = mesh('small', 6), big = mesh('big', 600);
    const { data, dropped } = encodeGhosts([big, small], 600);
    expect(dropped).toEqual(['big']);
    expect(decodeGhosts(data).map((m) => m.gid)).toEqual(['small']);
  });
  it('reads a damaged blob as empty, so the walk draws boxes', () => {
    expect(decodeGhosts(new Uint8Array([1, 2, 3]))).toEqual([]);
    const { data } = encodeGhosts([mesh('A', 12)]);
    expect(decodeGhosts(data.slice(0, 20))).toEqual([]);
  });
  it('takes one element out of a merged geometry in IFC axes with a local index', () => {
    const position = [0, 0, 0, 9, 9, 9, 1, 2, 3, 4, 5, 6, 7, 8, 9]; // viewer axes; the element owns vertices 1..4
    const index = [0, 1, 2, 3, 2, 3, 4, 2, 3];
    const m = meshOfElement(position, index, 1, 4, 3, 6, 'g');
    expect(Array.from(m.index)).toEqual([2, 1, 2, 3, 1, 2]); // indices 3,2,3,4,2,3 minus the vertex start 1
    // viewer (x, y, z) -> IFC (x, -z, y)
    expect(Array.from(m.positions.subarray(0, 3))).toEqual([9, -9, 9]);
    expect(Array.from(m.positions.subarray(3, 6))).toEqual([1, -3, 2]);
  });
  it('puts a base point in the head viewer frame with both shifts and the diff offset', () => {
    expect(baseToViewer([1, 2, 3], [0, 0, 0], [0, 0, 0], [0, 0, 0])).toEqual([1, 3, -2]);
    expect(baseToViewer([1, 2, 3], [100, 0, 0], [100, 0, 0], [0, 0, 0])).toEqual([1, 3, -2]);
    expect(baseToViewer([1, 2, 3], [100, 0, 0], [90, 0, 0], [0, 0, 0])).toEqual([11, 3, -2]);
    expect(baseToViewer([1, 2, 3], [0, 0, 0], [0, 0, 0], [1000, 0, 0])).toEqual([1001, 3, -2]);
  });
  it('draws a box as 12 edges and cycles the ghost modes', () => {
    expect(boxEdges([0, 0, 0, 1, 2, 3]).length).toBe(12 * 6);
    expect(['both', 'head', 'base', 'both'].map((_, i, a) => (i === 0 ? 'both' : nextGhostMode(a[i - 1] as never)))).toEqual(['both', 'head', 'base', 'both']);
  });
});

describe('attachment adapter', () => {
  const topic = (g: string, status = 'Open'): BcfTopic => ({
    guid: `t-${g}`, topicType: 'Issue', topicStatus: status, title: 'T', labels: [], referenceLinks: [], creationDate: '', creationAuthor: 'a', headerFiles: [], documentReferences: [], relatedTopics: [], comments: [],
    viewpoints: [{ guid: 'v', data: { guid: 'v', camera: null, selection: [{ ifcGuid: g }], visibility: null, coloring: [], clipping: [], lines: [] }, annotations: [{ guid: 'an', type: 'note', text: '', anchor: { kind: 'element', point: [0, 0, 0], elementGuid: g }, offset: [0, 0] }] }],
    pin: { position: [0, 0, 0], elementGuid: g },
  }) as unknown as BcfTopic;
  const set = (g: string): MarkupSet => ({ id: 's-' + g, title: 'S', author: 'a', created: '', updated: '', view: { selection: [g], pins: [] }, camera: {}, markups: [{ id: 'm', anchor: { kind: 'element', point: [0, 0, 0], elementGuid: g }, attach: { kind: 'elements', guids: [g, 'other'] } }], nextNumber: 2 }) as unknown as MarkupSet;
  const make = (topics: BcfTopic[], sets: MarkupSet[]) => {
    const log: string[] = [];
    const host = attachmentHost({
      topics: () => topics, sets: () => sets, touched: (o) => log.push(`touched ${o.topics.length}/${o.sets.length}`),
      addComment: (g, t) => { topics.find((x) => x.guid === g)!.comments.push({ guid: 'c', date: '', author: '', text: t }); log.push(`comment ${g}`); },
      setStatus: (g, s) => { topics.find((x) => x.guid === g)!.topicStatus = s; },
    });
    return { host, log };
  };
  it('reads what an issue and a sketch refer to', () => {
    expect([...topicGuids(topic('G1'))]).toEqual(['G1']);
    expect(new Set(setGuids(set('G1')))).toEqual(new Set(['G1', 'other']));
  });
  it('counts issues and sketches by GlobalId, with or without a federation suffix', () => {
    const { host } = make([topic('G1'), topic('G2')], [set('G1')]);
    expect(host.countFor('G1')).toEqual({ issues: 1, sketches: 1 });
    expect(host.countFor('G1~2')).toEqual({ issues: 1, sketches: 1 });
    expect(host.countFor('G2')).toEqual({ issues: 1, sketches: 0 });
    expect(host.countFor('G3')).toEqual({ issues: 0, sketches: 0 });
  });
  it('retargets an accepted rematch everywhere an element is named, and deletes nothing', () => {
    const t = topic('OLD'), s = set('OLD');
    const { host, log } = make([t], [s]);
    const n = host.retarget(new Map([['OLD', 'NEW']]));
    expect(n).toBe(6);
    expect(topicGuids(t)).toEqual(new Set(['NEW']));
    expect(new Set(setGuids(s))).toEqual(new Set(['NEW', 'other']));
    expect(host.countFor('OLD')).toEqual({ issues: 0, sketches: 0 });
    expect(host.countFor('NEW')).toEqual({ issues: 1, sketches: 1 });
    expect(log).toEqual(['touched 1/1']);
    expect(host.retarget(new Map([['OLD', 'NEW']]))).toBe(0);
  });
  it('flags the issues of a deleted element once, and resolves on request', () => {
    const t = topic('DEL');
    const { host } = make([t], []);
    expect(host.flagDeleted(['DEL'], 'element deleted in v2')).toBe(1);
    expect(host.flagDeleted(['DEL'], 'element deleted in v2')).toBe(1);
    expect(t.comments).toHaveLength(1);
    expect(t.topicStatus).toBe('Open');
    expect(host.resolveIssues(['DEL'], 'element removed in revision')).toBe(1);
    expect(t.topicStatus).toBe('Resolved');
    expect(host.resolveIssues(['DEL'], 'again')).toBe(0);
  });
  it('rewrites plain shapes in place', () => {
    const t = topic('A');
    expect(retargetTopic(t, new Map([['A', 'B']]))).toBeGreaterThan(0);
    const s = set('A');
    expect(retargetSet(s, new Map([['A', 'B']]))).toBeGreaterThan(0);
  });
});

describe('panel host adapter for the right-hand sidebar (stub, not wired)', () => {
  it('is null without a sidebar so the floating host is used', () => {
    expect(rightSidebarPanelHost(null)).toBeNull();
    expect(rightSidebarPanelHost(undefined)).toBeNull();
  });
  it('turns addTab({ id, label, mount }) into mount, show and hide', () => {
    const log: string[] = [];
    let mounted: ((b: HTMLElement) => void) | null = null;
    const host = rightSidebarPanelHost({ addTab: (spec) => { log.push(`tab ${spec.id} ${spec.label}`); mounted = spec.mount; return { show: () => log.push('show'), hide: () => log.push('hide') }; } })!;
    const body = { appended: [] as unknown[], appendChild(x: unknown) { this.appended.push(x); return x; } };
    const el = { hidden: true } as unknown as HTMLElement;
    host.mount('revision-walk', 'Revision walk', el);
    mounted!(body as unknown as HTMLElement);
    host.show('revision-walk');
    host.hide('revision-walk');
    expect(log).toEqual(['tab revision-walk Revision walk', 'show', 'hide']);
    expect(body.appended).toEqual([el]);
    expect(el.hidden).toBe(false);
  });
});

describe('keys', () => {
  const src = (f: string): string => readFileSync(resolve(WEB, f), 'utf8');
  it('handles every key of the table in the panel', () => {
    const panel = src('src/plugins/revisionWalk.ts');
    for (const k of REVISION_WALK_KEYS.flatMap((x) => x.keys)) {
      const lit = k === 'Escape' ? "e.key === 'Escape'" : `case '${k}'`;
      expect(panel.includes(lit) || panel.includes(`k === '${k}'`), k).toBe(true);
    }
  });
  it('reuses the review walk keys where the meaning is the same', () => {
    const review = src('src/plugins/classifyReview.ts');
    for (const k of REVISION_WALK_KEYS.filter((x) => x.sameAsReview).flatMap((x) => x.keys)) expect(review.includes(`'${k}'`), k).toBe(true);
  });
  it('has no key twice and none with a modifier', () => {
    const all = REVISION_WALK_KEYS.flatMap((x) => x.keys);
    expect(new Set(all).size).toBe(all.length);
    expect(all.some((k) => /^(Ctrl|Alt|Meta)\+/i.test(k))).toBe(false);
  });
  it('registers exactly the palette actions of the table, and their default keys are free', () => {
    const plugin = src('src/plugins/revision.ts');
    for (const a of REVISION_ACTIONS) {
      expect(plugin.includes(`id: '${a.id}'`), a.id).toBe(true);
      expect(plugin.includes(`keys: [${a.keys.map((k) => `'${k}'`).join(', ')}]`), a.id).toBe(true);
    }
    const used = new Map<string, string>();
    for (const f of readdirSync(resolve(WEB, 'src/plugins')).filter((n) => n.endsWith('.ts') && n !== 'revision.ts')) {
      for (const m of src(`src/plugins/${f}`).matchAll(/keys: \[([^\]]*)\]/g)) for (const k of (m[1] ?? '').matchAll(/'([^']+)'/g)) used.set(k[1]!.toLowerCase(), f);
    }
    for (const a of REVISION_ACTIONS) for (const k of a.keys) expect(used.get(k.toLowerCase()), `${k} is taken`).toBeUndefined();
  });
});

describe('nothing of it is a setting', () => {
  it('registers no params section, preset or link, and keeps no state in localStorage', () => {
    for (const f of ['src/plugins/revision.ts', 'src/plugins/revisionWalk.ts', 'src/revision/controller.ts', 'src/revision/attachHost.ts', 'src/revision/ghost.ts', 'src/ui/panelHost.ts']) {
      const t = readFileSync(resolve(WEB, f), 'utf8');
      expect(t, f).not.toMatch(/registerParamSection|localStorage|sessionStorage|history\.(push|replace)State|location\.(hash|search)\s*=/);
    }
  });
  it('mounts the panel only through the PanelHost', () => {
    const t = readFileSync(resolve(WEB, 'src/plugins/revisionWalk.ts'), 'utf8');
    expect(t).toMatch(/this\.host\.mount\(/);
    expect(t).not.toMatch(/appendChild\(root\)|stage\.appendChild/);
  });
});
