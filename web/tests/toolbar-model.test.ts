import { describe, expect, it } from 'vitest';
import { getTools, registerTool } from '../src/tools/registry';
import type { XrayTool } from '../src/tools/registry';
import { clampDrawerWidth, visibleTools } from '../src/tools/toolbarModel';

const tool = (id: string, order?: number, extra: Partial<XrayTool> = {}): XrayTool => ({ id, label: id, title: id, icon: '<svg/>', order, ...extra });

describe('toolbar ordering (registry)', () => {
  it('sorts by order, then id; default order 100', () => {
    const offs = [registerTool(tool('zz-b', 5)), registerTool(tool('zz-a', 5)), registerTool(tool('zz-first', 1)), registerTool(tool('zz-none'))];
    const ids = getTools().map((t) => t.id).filter((i) => i.startsWith('zz-'));
    expect(ids).toEqual(['zz-first', 'zz-a', 'zz-b', 'zz-none']);
    offs.forEach((o) => o());
    expect(getTools().some((t) => t.id.startsWith('zz-'))).toBe(false);
  });
});

describe('toolbar boot filtering', () => {
  const all = [tool('open', 10), tool('xray', 30), tool('measure', 70), tool('cleanup', 110, { available: () => false })];
  it('without boot.tools shows every available tool in registry order', () => {
    expect(visibleTools(all, {}, {} as never).map((t) => t.id)).toEqual(['open', 'xray', 'measure']);
  });
  it('boot.tools picks and orders', () => {
    expect(visibleTools(all, { tools: ['measure', 'xray'] }).map((t) => t.id)).toEqual(['measure', 'xray']);
  });
  it('boot.tools skips unknown, repeated and unavailable ids', () => {
    expect(visibleTools(all, { tools: ['xray', 'nope', 'xray', 'cleanup', 'open'] }, {} as never).map((t) => t.id)).toEqual(['xray', 'open']);
  });
  it('an empty boot.tools list shows nothing', () => {
    expect(visibleTools(all, { tools: [] })).toEqual([]);
  });
  it('a throwing available() hides the tool', () => {
    const bad = tool('bad', 1, { available: () => { throw new Error('x'); } });
    expect(visibleTools([bad, ...all], {}, {} as never).map((t) => t.id)).not.toContain('bad');
  });
});

describe('drawer width', () => {
  it('clamps to 280 and to the viewport', () => {
    expect(clampDrawerWidth(100, 1600)).toBe(280);
    expect(clampDrawerWidth(5000, 1600)).toBe(900);
    expect(clampDrawerWidth(5000, 600)).toBe(520);
    expect(clampDrawerWidth(401.6, 1600)).toBe(402);
  });
});
