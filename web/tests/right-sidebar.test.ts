// The pure part of the right sidebar (src/ui/rightSidebar.ts): the stored state and the queue for tabs added before the column exists.
// The DOM, the tabs and the phone sheet are covered by bench/smoke-right-sidebar.mjs.
import { describe, expect, it } from 'vitest';
import { DEFAULT_TAB, addRightSidebarTab, getRightSidebar, parseDockState, setRightSidebar } from '../src/ui/rightSidebar';

describe('right sidebar state', () => {
  it('reads the stored fold and tab', () => {
    expect(parseDockState('{"collapsed":true,"tab":"classification"}', false)).toEqual({ collapsed: true, tab: 'classification' });
    expect(parseDockState('{"collapsed":false}', true)).toEqual({ collapsed: false, tab: DEFAULT_TAB });
  });
  it('keeps the old format of the parameter dock ({ collapsed } only) working', () => {
    expect(parseDockState('{"collapsed":true}', false)).toEqual({ collapsed: true, tab: 'properties' });
  });
  it('falls back to the screen width for the fold and to Properties for the tab on nothing or garbage', () => {
    expect(parseDockState(null, true)).toEqual({ collapsed: true, tab: 'properties' });
    expect(parseDockState(null, false)).toEqual({ collapsed: false, tab: 'properties' });
    expect(parseDockState('not json', true)).toEqual({ collapsed: true, tab: 'properties' });
    expect(parseDockState('{"collapsed":"yes","tab":7}', false)).toEqual({ collapsed: false, tab: 'properties' });
  });
});

describe('tabs added before the column exists', () => {
  it('are queued and the handle is inert until the column is built', () => {
    expect(getRightSidebar()).toBeNull();
    const h = addRightSidebarTab({ id: 'early', label: 'Early', mount: () => undefined });
    expect(h.id).toBe('early');
    expect(h.visible()).toBe(false);
    expect(() => { h.show(); h.setBadge('1'); h.remove(); }).not.toThrow();
    setRightSidebar(null);
  });
});
