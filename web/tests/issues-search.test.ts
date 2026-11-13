// Search index of issues and sketches: title, note or description, and comment text.

import { describe, expect, it } from 'vitest';
import { searchIssues } from '../src/issues/search';
import type { BcfTopic } from '../src/bcf/model';
import type { MarkupSet } from '../src/markup/model';

function topic(title: string, o: Partial<BcfTopic> = {}): BcfTopic {
  return {
    guid: `g-${title}`, topicType: 'Issue', topicStatus: 'Open', title, labels: [], referenceLinks: [], creationDate: '2026-01-01T00:00:00Z', creationAuthor: 'x',
    headerFiles: [], documentReferences: [], relatedTopics: [], comments: [], viewpoints: [], ...o,
  };
}

function sketch(title: string, o: Partial<MarkupSet> = {}): MarkupSet {
  return {
    id: `s-${title}`, title, author: 'x', created: '2026-01-01T00:00:00Z', updated: '2026-01-01T00:00:00Z',
    view: { id: 'v', name: title, created: '', updated: '', camera: { position: [0, 0, 0], target: [0, 0, 1], up: [0, 1, 0], fov: 45, ortho: false }, selection: [], params: {} },
    camera: { position: [0, 0, 0], direction: [0, 1, 0], up: [0, 0, 1], fov: 45, aspect: 1.5 }, markups: [], nextNumber: 1, ...o,
  };
}

const topics = [
  topic('Duct clash level 1', { priority: 'High', comments: [{ guid: 'c1', date: '', author: 'a', text: 'Reroute below the girder' }] }),
  topic('Door width', { description: 'Fire escape door is too narrow', topicStatus: 'Resolved' }),
];

const sets = [
  sketch('Stair detail', { note: 'Handrail height to check' }),
  sketch('Roof plan'),
];

describe('searchIssues', () => {
  const input = { topics, sets };

  it('finds an issue by title', () => {
    const r = searchIssues(input, 'duct');
    expect(r).toHaveLength(1);
    expect(r[0]).toMatchObject({ kind: 'issue', id: 'g-Duct clash level 1', field: 'title' });
    expect(r[0]!.positions).toEqual([0, 1, 2, 3]);
    expect(r[0]!.sub).toContain('Open, High');
  });

  it('finds an issue by comment text and says where it matched', () => {
    const r = searchIssues(input, 'girder');
    expect(r).toHaveLength(1);
    expect(r[0]).toMatchObject({ kind: 'issue', field: 'comment' });
    expect(r[0]!.sub).toContain('comment');
    expect(r[0]!.sub).toContain('girder');
  });

  it('finds an issue by description, a sketch by note and a sketch by title', () => {
    expect(searchIssues(input, 'fire escape')[0]).toMatchObject({ kind: 'issue', field: 'description' });
    expect(searchIssues(input, 'handrail')[0]).toMatchObject({ kind: 'sketch', field: 'note', id: 's-Stair detail' });
    expect(searchIssues(input, 'roof')[0]).toMatchObject({ kind: 'sketch', field: 'title' });
  });

  it('finds a sketch by the comment text it still carries from before issues', () => {
    const old = sketch('Old review');
    old.markups.push({ id: 'm', number: 1, kind: 'rect', colour: 'red', weight: 2, fill: false, text: '', status: 'resolved', author: 'x', created: '', comments: [{ id: 'c', author: 'b', date: '', text: 'Checked on site' }] });
    const r = searchIssues({ topics: [], sets: [old] }, 'checked on site');
    expect(r[0]).toMatchObject({ kind: 'sketch', field: 'comment' });
  });

  it('needs every word, ignores case and ranks a title hit before a comment hit', () => {
    expect(searchIssues(input, 'DUCT girder')).toHaveLength(1);
    expect(searchIssues(input, 'duct nothing')).toHaveLength(0);
    const both = searchIssues({ topics: [topic('Beam', { comments: [{ guid: 'c', date: '', author: '', text: 'about the duct' }] }), topic('Duct')], sets: [] }, 'duct');
    expect(both.map((h) => h.field)).toEqual(['title', 'comment']);
  });

  it('an empty query finds nothing', () => {
    expect(searchIssues(input, '   ')).toEqual([]);
  });
});
