import { describe, expect, it } from 'vitest';
import changelogText from '../../CHANGELOG.md?raw';
import { decideWhatsNew, isQuietMode, newestRelease, parseChangelog } from '../src/whatsnew/changelog';

const SAMPLE = `# Changelog

Intro text that is not a bullet.

## Unreleased

- Placeholder.

## v30 - 2026-12-01

- First line.
- A line that goes on
  over two lines.
* Star bullet.

Loose text is ignored.

## v29 - 2026-11-25

- Older line.
`;

describe('parseChangelog', () => {
  const s = parseChangelog(SAMPLE);

  it('reads sections newest first, with release and date', () => {
    expect(s.map((x) => x.release)).toEqual([null, 30, 29]);
    expect(s[1]!.date).toBe('2026-12-01');
    expect(s[0]!.date).toBeNull();
    expect(s[0]!.title).toBe('Unreleased');
  });

  it('joins continuation lines and accepts star bullets', () => {
    expect(s[1]!.lines).toEqual(['First line.', 'A line that goes on over two lines.', 'Star bullet.']);
  });

  it('ignores the title and loose text, and handles CRLF and empty input', () => {
    expect(s[2]!.lines).toEqual(['Older line.']);
    expect(parseChangelog('')).toEqual([]);
    expect(parseChangelog(SAMPLE.replace(/\n/g, '\r\n'))[1]!.lines.length).toBe(3);
  });

  it('newestRelease skips Unreleased', () => {
    expect(newestRelease(s)!.release).toBe(30);
    expect(newestRelease(parseChangelog('## Unreleased\n- x'))).toBeNull();
  });
});

describe('the real CHANGELOG.md', () => {
  const sections = parseChangelog(changelogText);

  it('starts with Unreleased and lists every release from the newest down to v22, newest first, each with lines and a date', () => {
    expect(sections[0]!.title).toBe('Unreleased');
    const rel = sections.filter((x) => x.release !== null);
    const newest = rel[0]!.release!;
    expect(newest).toBeGreaterThanOrEqual(29);
    // No gaps and no duplicates: newest, newest - 1, ..., 22 (a new release adds its section on top).
    expect(rel.map((x) => x.release)).toEqual(Array.from({ length: newest - 21 }, (_, i) => newest - i));
    for (const r of rel) {
      expect(r.lines.length, `v${r.release}`).toBeGreaterThan(0);
      expect(r.date, `v${r.release}`).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });
});

describe('isQuietMode', () => {
  const base = { boot: undefined, search: '', framed: false };
  it('is false for the normal viewer', () => expect(isQuietMode(base)).toBe(false));
  it('is true for a packed page, a kiosk page, ?embed, ?kiosk and a framed page', () => {
    expect(isQuietMode({ ...base, boot: {} })).toBe(true);
    expect(isQuietMode({ ...base, boot: { kiosk: true } })).toBe(true);
    expect(isQuietMode({ ...base, search: '?model=building&embed=1' })).toBe(true);
    expect(isQuietMode({ ...base, search: '?kiosk' })).toBe(true);
    expect(isQuietMode({ ...base, framed: true })).toBe(true);
  });
  it('ignores unrelated parameters', () => expect(isQuietMode({ ...base, search: '?model=fzk-haus' })).toBe(false));
});

describe('decideWhatsNew', () => {
  const ok = { current: 30, stored: '29', storageOk: true, quiet: false, hasLines: true };
  it('shows the card once for a newer build and stores the number', () => {
    expect(decideWhatsNew(ok)).toEqual({ show: true, store: true });
  });
  it('does not show it on the first start ever, but stores the number', () => {
    expect(decideWhatsNew({ ...ok, stored: null })).toEqual({ show: false, store: true });
  });
  it('treats an unreadable stored value like the first start', () => {
    expect(decideWhatsNew({ ...ok, stored: 'abc' })).toEqual({ show: false, store: true });
  });
  it('does nothing when the stored number is the same or newer', () => {
    expect(decideWhatsNew({ ...ok, stored: '30' })).toEqual({ show: false, store: false });
    expect(decideWhatsNew({ ...ok, stored: '31' })).toEqual({ show: false, store: false });
  });
  it('never shows or stores on a quiet page', () => {
    expect(decideWhatsNew({ ...ok, quiet: true })).toEqual({ show: false, store: false });
    expect(decideWhatsNew({ ...ok, quiet: true, stored: null })).toEqual({ show: false, store: false });
  });
  it('stays away when localStorage is not usable or the release is unknown', () => {
    expect(decideWhatsNew({ ...ok, storageOk: false })).toEqual({ show: false, store: false });
    expect(decideWhatsNew({ ...ok, current: null })).toEqual({ show: false, store: false });
  });
  it('stores but does not show when there is nothing to say', () => {
    expect(decideWhatsNew({ ...ok, hasLines: false })).toEqual({ show: false, store: true });
  });
});
