import { describe, expect, it } from 'vitest';
import { fuzzyScore, rankItems } from '../src/ui/palette';
import type { PaletteItem } from '../src/ui/palette';

const item = (label: string, path = '', key = `a:${label}`): PaletteItem => ({ key, label, path, chords: [], kind: 'action', run: () => undefined });

describe('fuzzy palette ranking', () => {
  it('matches subsequences case-insensitively and rejects non-matches', () => {
    expect(fuzzyScore('xry', 'Toggle x-ray')).not.toBeNull();
    expect(fuzzyScore('XRAY', 'toggle x-ray')).not.toBeNull();
    expect(fuzzyScore('zz', 'Toggle x-ray')).toBeNull();
    expect(fuzzyScore('toggle xray extra', 'toggle')).toBeNull();
    expect(fuzzyScore('', 'anything')).toEqual({ score: 0, positions: [] });
  });
  it('reports the matched positions', () => {
    expect(fuzzyScore('tx', 'Toggle x-ray')!.positions).toEqual([0, 7]);
  });
  it('prefers prefix, word-start and consecutive matches', () => {
    const exact = fuzzyScore('explode', 'Explode')!.score;
    const sub = fuzzyScore('explode', 'Collapse or explode')!.score;
    const scattered = fuzzyScore('explode', 'e x p l o d e')!.score;
    expect(exact).toBeGreaterThan(sub);
    expect(sub).toBeGreaterThan(scattered);
    expect(fuzzyScore('ho', 'Hold')!.score).toBeGreaterThan(fuzzyScore('ho', 'Shoulder')!.score);
  });
  it('ranks items by score', () => {
    const items = [item('Hide selected'), item('Explode', 'Cinematic / Explode'), item('Peel layers'), item('Explode radial storeys'), item('Toggle x-ray')];
    const r = rankItems(items, 'explode');
    expect(r.map((x) => x.item.label)).toEqual(['Explode', 'Explode radial storeys']);
    expect(rankItems(items, 'xray')[0]!.item.label).toBe('Toggle x-ray');
    expect(rankItems(items, 'zzzz')).toEqual([]);
  });
  it('matches on the folder path with a lower weight than the label', () => {
    const items = [item('Strength', 'Bloom'), item('Bloom strength', 'Imaging')];
    expect(rankItems(items, 'bloom')[0]!.item.label).toBe('Bloom strength');
    expect(rankItems(items, 'bloom')).toHaveLength(2);
  });
  it('puts recently used items first for an empty query and boosts them otherwise', () => {
    const items = [item('Alpha'), item('Beta'), item('Gamma')];
    expect(rankItems(items, '', ['a:Gamma', 'a:Beta']).map((x) => x.item.label)).toEqual(['Gamma', 'Beta', 'Alpha']);
    const two = [item('Open file'), item('Open folder')];
    expect(rankItems(two, 'open', []).length).toBe(2);
    expect(rankItems(two, 'open', ['a:Open folder'])[0]!.item.label).toBe('Open folder');
  });
});
