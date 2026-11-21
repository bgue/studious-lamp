// Review of the links (src/map4d/linkReview.ts) with the real linker on the FZK-Haus sample: suggestions to accept and reject, the decisions
// kept by the next run, the LinkML file in and out. No configuration: every activity is left for suggestions.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseXer } from '../src/schedule/xer';
import { fromSidecar } from '../src/schedule/model';
import { linkSchedule } from '../src/schedule/link';
import { countLinks, decideLink, decisionLinks, linksWithStatus, parseLinks, proposedLinks, serializeLinks } from '../src/map4d/linkReview';
import { emptyConfig } from '../src/map4d/scheduleConfig';
import type { FourDConfig } from '../src/schedule/types';

const file = (p: string): string => fileURLToPath(new URL(p, import.meta.url));
const schedule = parseXer(readFileSync(file('../public/samples/fzk-haus.xer')));
const model = fromSidecar(JSON.parse(readFileSync(file('../public/models/fzk-haus.json'), 'utf8')), { identityKey: 'fzk-sample' });
const sample = JSON.parse(readFileSync(file('../public/samples/fzk-haus.4d.json'), 'utf8')) as FourDConfig;
const NOW = '2027-02-02T10:00:00.000Z';

const bare = linkSchedule(schedule, model, emptyConfig(), []);

describe('review state of suggested links', () => {
  it('starts with proposals only, best confidence first, and counts them', () => {
    const p = proposedLinks(bare);
    expect(p.length).toBeGreaterThan(3);
    expect(p.every((l) => l.source === 'suggested')).toBe(true);
    for (let i = 1; i < p.length; i++) expect(p[i - 1]!.confidence ?? 0).toBeGreaterThanOrEqual(p[i]!.confidence ?? 0);
    expect(countLinks(bare)).toMatchObject({ accepted: 0, proposed: p.length, rejected: 0 });
    expect(countLinks(null)).toEqual({ accepted: 0, proposed: 0, rejected: 0, superseded: 0 });
  });

  it('accepts and rejects one link, with a time, without touching the dataset it was given', () => {
    const p = proposedLinks(bare);
    const a = decideLink(bare, p[0]!.id, 'accepted', NOW);
    const l = a.links!.find((x) => x.id === p[0]!.id)!;
    expect(l).toMatchObject({ status: 'accepted', reviewed_at: NOW });
    expect('reviewed_by' in l).toBe(false);
    expect(bare.links!.find((x) => x.id === p[0]!.id)!.status).toBe('proposed');
    const r = decideLink(a, p[1]!.id, 'rejected', NOW, 'Ana');
    expect(r.links!.find((x) => x.id === p[1]!.id)).toMatchObject({ status: 'rejected', reviewed_by: 'Ana' });
    expect(countLinks(r)).toMatchObject({ accepted: 1, rejected: 1, proposed: p.length - 2 });
    expect(decideLink(r, 'no-such-link', 'accepted')).toBe(r);
    expect(decideLink(r, p[0]!.id, 'accepted')).toBe(r);
    expect(linksWithStatus(r, 'rejected')).toHaveLength(1);
  });

  it('keeps the decisions in the next run: an accepted suggestion stays accepted, a rejected one is not suggested again', () => {
    const p = proposedLinks(bare);
    let l = decideLink(bare, p[0]!.id, 'accepted', NOW);
    l = decideLink(l, p[1]!.id, 'rejected', NOW);
    const prior = decisionLinks(l);
    expect(prior.map((x) => x.status).sort()).toEqual(['accepted', 'rejected']);
    const again = linkSchedule(schedule, model, emptyConfig(), [], { priorLinks: prior });
    const acc = again.links!.filter((x) => x.status === 'accepted' && x.role === 'build');
    expect(acc.map((x) => x.activity)).toContain(p[0]!.activity);
    expect(acc.find((x) => x.activity === p[0]!.activity)!.elements).toEqual(p[0]!.elements);
    const rej = again.links!.filter((x) => x.activity === p[1]!.activity);
    expect(rej.every((x) => x.status === 'rejected')).toBe(true);
    expect(again.links!.filter((x) => x.status === 'proposed').map((x) => x.activity)).not.toContain(p[1]!.activity);
    // the accepted link takes its elements, so other suggestions may shrink or drop
    expect(countLinks(again).proposed).toBeLessThanOrEqual(p.length - 2);
  });

  it('does not keep links that the attribute rules make again, so a changed configuration takes effect', () => {
    const ruled = linkSchedule(schedule, model, sample, []);
    expect(ruled.links!.filter((x) => x.status === 'accepted').every((x) => x.source === 'attributes')).toBe(true);
    expect(decisionLinks(ruled)).toEqual([]);
    const prop = ruled.links!.map((l) => ({ ...l, source: 'property' as const }));
    expect(decisionLinks({ ...ruled, links: prop })).toEqual([]);
    expect(decisionLinks(null)).toEqual([]);
  });
});

describe('the links as a LinkML file', () => {
  it('writes and reads the dataset, and leaves reviewer names out unless asked', () => {
    const p = proposedLinks(bare);
    const l = decideLink(bare, p[0]!.id, 'accepted', NOW, 'Ana');
    const text = serializeLinks(l);
    expect(text).not.toContain('Ana');
    expect(serializeLinks(l, true)).toContain('Ana');
    const back = parseLinks(text);
    expect(back.problems).toEqual([]);
    expect(back.dataset!.links!.find((x) => x.id === p[0]!.id)!.status).toBe('accepted');
    expect(back.dataset!.model.identity_key).toBe('fzk-sample');
    expect(back.dataset!.schedule!.source_hash).toBe(schedule.sourceHash);
    expect(back.dataset!.activities!.length).toBeGreaterThan(0);
  });

  it('lists the rows it leaves out and refuses what is no dataset', () => {
    const ds = { model: { identity_key: 'k' }, links: [{ id: 'a', activity: 'A1', role: 'build', elements: ['g'], status: 'accepted' }, { id: 'b', activity: 'A2', role: 'sideways', elements: [] }, { activity: 'A3' }, { id: 'c', activity: 'A4', role: 'build', elements: ['g'], status: 'maybe' }] };
    const r = parseLinks(ds);
    expect(r.dataset!.links!.map((x) => x.id)).toEqual(['a']);
    expect(r.problems).toHaveLength(3);
    expect(parseLinks('{').dataset).toBeNull();
    expect(parseLinks({ links: [] }).dataset).toBeNull();
    expect(parseLinks({ model: {}, links: 3 }).dataset).toBeNull();
    expect(parseLinks({ model: { identity_key: 'k' } }).dataset!.links).toEqual([]);
  });
});
