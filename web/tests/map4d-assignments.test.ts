import { describe, expect, it } from 'vitest';
import type { Assignment } from '../src/schedule/types';
import { acceptedValues, assign, decide, makeAssignments, mergeAssignments, normalise, renameValue, timeOf, unassign, valueCounts } from '../src/map4d/assignments';

const G1 = '0123456789abcdefghijkA';
const G2 = '0123456789abcdefghijkB';
let n = 0;
const idGen = (): string => `t${++n}`;
const rec = (o: Partial<Assignment> & Pick<Assignment, 'id'>): Assignment => ({ element: G1, attribute: 'location', value: 'L1', status: 'accepted', ...o });

describe('assignments: supersede', () => {
  it('keeps the newest accepted record per element and attribute, the older ones become superseded', () => {
    const list = normalise([
      rec({ id: 'a', value: 'L1', reviewed_at: '2027-01-01T00:00:00Z' }),
      rec({ id: 'b', value: 'L2', reviewed_at: '2027-02-01T00:00:00Z' }),
      rec({ id: 'c', value: 'L3', reviewed_at: '2027-01-15T00:00:00Z' }),
    ]);
    expect(list.map((a) => a.status)).toEqual(['superseded', 'accepted', 'superseded']);
    expect(acceptedValues(list).get(G1)).toEqual({ location: 'L2' });
  });

  it('does not touch other attributes, other elements or non-accepted records', () => {
    const list = normalise([
      rec({ id: 'a' }), rec({ id: 'b', attribute: 'trade', value: 'CONC' }), rec({ id: 'c', element: G2 }),
      rec({ id: 'd', status: 'proposed', value: 'X' }), rec({ id: 'e', status: 'rejected', value: 'Y' }),
    ]);
    expect(list.map((a) => a.status)).toEqual(['accepted', 'accepted', 'accepted', 'proposed', 'rejected']);
  });

  it('breaks a time tie in favour of the later record, and normalise is idempotent', () => {
    const t = '2027-01-01T00:00:00Z';
    const once = normalise([rec({ id: 'a', value: 'L1', created_at: t }), rec({ id: 'b', value: 'L2', created_at: t })]);
    expect(once.map((a) => a.status)).toEqual(['superseded', 'accepted']);
    expect(normalise(once)).toEqual(once);
  });

  it('timeOf prefers reviewed_at and is 0 without a date', () => {
    expect(timeOf({})).toBe(0);
    expect(timeOf({ created_at: '2027-01-01T00:00:00Z', reviewed_at: '2027-03-01T00:00:00Z' })).toBe(Date.parse('2027-03-01T00:00:00Z'));
  });
});

describe('assignments: merge', () => {
  it('adds new ids, and a newer accepted record from outside supersedes the stored one', () => {
    const mine = [rec({ id: 'a', value: 'L1', reviewed_at: '2027-01-01T00:00:00Z' })];
    const theirs = [rec({ id: 'x', value: 'L9', reviewed_at: '2027-05-01T00:00:00Z', source: 'agent' })];
    const r = mergeAssignments(mine, theirs);
    expect(r.added).toBe(1);
    expect(r.superseded).toBe(1);
    expect(r.list.find((a) => a.id === 'a')!.status).toBe('superseded');
    expect(acceptedValues(r.list).get(G1)!.location).toBe('L9');
  });

  it('an older accepted record from outside is stored as superseded and the stored one stays current', () => {
    const mine = [rec({ id: 'a', value: 'L1', reviewed_at: '2027-06-01T00:00:00Z' })];
    const r = mergeAssignments(mine, [rec({ id: 'x', value: 'OLD', reviewed_at: '2027-01-01T00:00:00Z' })]);
    expect(r.list.map((a) => [a.id, a.status])).toEqual([['a', 'accepted'], ['x', 'superseded']]);
  });

  it('importing the same records again changes nothing', () => {
    const base = [rec({ id: 'a', reviewed_at: '2027-01-01T00:00:00Z' }), rec({ id: 'b', element: G2, status: 'proposed' })];
    const once = mergeAssignments([], base);
    const twice = mergeAssignments(once.list, base);
    expect(twice.list).toEqual(once.list);
    expect(twice.added).toBe(0);
    expect(twice.updated).toBe(0);
  });

  it('a record with a known id and a newer decision replaces the old one (proposed to accepted by a reviewer)', () => {
    const stored = [rec({ id: 'p', status: 'proposed', created_at: '2027-01-01T00:00:00Z' })];
    const r = mergeAssignments(stored, [rec({ id: 'p', status: 'accepted', created_at: '2027-01-01T00:00:00Z', reviewed_at: '2027-01-02T00:00:00Z' })]);
    expect(r.updated).toBe(1);
    expect(r.list[0]!.status).toBe('accepted');
  });
});

describe('assignments: assign, unassign, decide, rename', () => {
  it('assigns, leaves an element that already has the value alone, and supersedes on a change', () => {
    const a = assign([], [G1, G2, G1], 'trade', 'CONC', { idGen, now: '2027-01-01T00:00:00Z' });
    expect(a.assigned).toBe(2);
    expect(a.list.every((x) => x.status === 'accepted' && x.source === 'manual' && x.reviewed_at && !('reviewed_by' in x))).toBe(true);
    const same = assign(a.list, [G1], 'trade', 'CONC', { idGen });
    expect(same.assigned).toBe(0);
    expect(same.unchanged).toBe(1);
    const changed = assign(a.list, [G1], 'trade', 'STEEL', { idGen, now: '2027-02-01T00:00:00Z' });
    expect(acceptedValues(changed.list).get(G1)!.trade).toBe('STEEL');
    expect(changed.list.filter((x) => x.status === 'superseded')).toHaveLength(1);
    expect(acceptedValues(changed.list).get(G2)!.trade).toBe('CONC');
  });

  it('unassign rejects the accepted record', () => {
    const a = assign([], [G1], 'zone', 'A', { idGen });
    const u = unassign(a.list, [G1], 'zone');
    expect(u.removed).toBe(1);
    expect(acceptedValues(u.list).size).toBe(0);
  });

  it('accepting a proposal supersedes the accepted record; rejecting leaves it', () => {
    const a = assign([], [G1], 'trade', 'CONC', { idGen, now: '2027-01-01T00:00:00Z' }).list;
    const p = makeAssignments([G1], 'trade', 'STEEL', { status: 'proposed', idGen, now: '2027-03-01T00:00:00Z', confidence: 0.8 });
    const list = [...a, ...p];
    const acc = decide(list, [p[0]!.id], 'accepted', '2027-03-02T00:00:00Z');
    expect(acceptedValues(acc.list).get(G1)!.trade).toBe('STEEL');
    const rej = decide(list, [p[0]!.id], 'rejected');
    expect(acceptedValues(rej.list).get(G1)!.trade).toBe('CONC');
    expect(rej.list.find((x) => x.id === p[0]!.id)!.status).toBe('rejected');
  });

  it('renames a value on the records and counts accepted records by value', () => {
    const a = assign(assign([], [G1, G2], 'location', 'L1', { idGen }).list, [G2], 'trade', 'CONC', { idGen }).list;
    expect(valueCounts(a, 'location').get('L1')).toBe(2);
    const r = renameValue(a, 'location', 'L1', 'Level 1');
    expect(r.changed).toBe(2);
    expect(valueCounts(r.list, 'location').get('Level 1')).toBe(2);
    expect(valueCounts(r.list, 'trade').get('CONC')).toBe(1);
  });
});
