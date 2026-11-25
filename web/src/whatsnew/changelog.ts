// "What's new": the pure part. CHANGELOG.md (repository root) is imported as text at build time (plugins/whatsNew.ts) and read here.
//
// Format of CHANGELOG.md: "## Unreleased" or "## v29 - 2026-11-25" headings, newest first, each followed by "- " lines. A line may
// continue on following lines that are indented. Anything else (the title, the introduction) is ignored.

export interface ChangelogSection {
  /** The heading text without "## ". */
  title: string;
  /** The release number, or null for "Unreleased" and for headings that carry none. */
  release: number | null;
  /** ISO date of the release, or null. */
  date: string | null;
  /** One entry per "- " line, continuation lines joined with a space. */
  lines: string[];
}

/** Read every section of a CHANGELOG.md text. */
export function parseChangelog(text: string): ChangelogSection[] {
  const sections: ChangelogSection[] = [];
  let cur: ChangelogSection | null = null;
  let open = false; // the last line was a bullet, so an indented line continues it
  for (const raw of text.replace(/\r\n?/g, '\n').split('\n')) {
    const h = /^##\s+(.+?)\s*$/.exec(raw);
    if (h) {
      const title = h[1]!;
      const v = /^v(\d+)\b/i.exec(title);
      const d = /(\d{4}-\d{2}-\d{2})/.exec(title);
      cur = { title, release: v ? parseInt(v[1]!, 10) : null, date: d ? d[1]! : null, lines: [] };
      sections.push(cur);
      open = false;
      continue;
    }
    if (!cur) continue;
    const b = /^[-*]\s+(.*\S)\s*$/.exec(raw);
    if (b) {
      cur.lines.push(b[1]!);
      open = true;
    } else if (open && /^\s+\S/.test(raw)) {
      cur.lines[cur.lines.length - 1] += ` ${raw.trim()}`;
    } else {
      open = false;
    }
  }
  return sections;
}

/** The newest released section (the first one with a release number; "Unreleased" is skipped), or null. */
export function newestRelease(sections: readonly ChangelogSection[]): ChangelogSection | null {
  return sections.find((s) => s.release !== null) ?? null;
}

/** Why the note stays away in a packed page, a kiosk page or an embedded one. */
export interface QuietContext {
  /** window.__xrayBoot: written into a page by xray-pack. The normal viewer and its single-file build have none. */
  boot: { kiosk?: boolean } | null | undefined;
  /** location.search */
  search: string;
  /** The page runs inside a frame. */
  framed: boolean;
}

/** True for a packed page (any boot configuration), a kiosk page, a page with ?embed or ?kiosk, and a framed page. */
export function isQuietMode(c: QuietContext): boolean {
  if (c.boot) return true;
  if (c.framed) return true;
  const q = new URLSearchParams(c.search);
  return q.has('embed') || q.has('kiosk');
}

export interface Decision {
  /** Show the card now. */
  show: boolean;
  /** Write `current` as the last seen release. */
  store: boolean;
}

/**
 * Show the card or not.
 *  - release unknown (no counter at build time) or a quiet page: no card, nothing stored;
 *  - nothing stored yet (the first start ever): no card, store the number;
 *  - stored is older than the build: card (when there is something to say), store the number;
 *  - stored is the same or newer (an older build opened later): nothing.
 * `stored` is the raw string from localStorage; null means no key. `storageOk` is false when localStorage cannot be used: the
 * card would come back at every start, so it stays away.
 */
export function decideWhatsNew(o: { current: number | null; stored: string | null; storageOk: boolean; quiet: boolean; hasLines: boolean }): Decision {
  const none: Decision = { show: false, store: false };
  if (o.current === null || o.quiet || !o.storageOk) return none;
  const seen = o.stored === null ? NaN : parseInt(o.stored, 10);
  if (!Number.isFinite(seen)) return { show: false, store: true };
  if (seen >= o.current) return none;
  return { show: o.hasLines, store: true };
}
