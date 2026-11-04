// Every relative link in README.md and SPEC.md must point at a file or directory that exists.
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

/** Relative link targets of a markdown text: `[text](target)` and `[text]: target`, without anchors, queries and absolute URLs. */
export function relativeLinks(md: string): string[] {
  const noFences = md.replace(/```[\s\S]*?```/g, '');
  const out: string[] = [];
  for (const m of noFences.matchAll(/\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g)) out.push(m[1]!);
  for (const m of noFences.matchAll(/^\[[^\]]+\]:\s*(\S+)/gm)) out.push(m[1]!);
  return out
    .filter((t) => !/^([a-z][a-z0-9+.-]*:|#|\/\/)/i.test(t))
    .map((t) => decodeURIComponent(t.split('#')[0]!.split('?')[0]!))
    .filter((t) => t.length > 0);
}

describe('relative links in the top-level docs', () => {
  it('finds links', () => {
    expect(relativeLinks('see [a](web/x.md#h), [b](https://x.y), [c](#top) and [d](docs/S.md "t")')).toEqual(['web/x.md', 'docs/S.md']);
  });
  for (const doc of ['README.md', 'SPEC.md']) {
    it(`${doc}: every relative link resolves`, () => {
      const text = readFileSync(resolve(repo, doc), 'utf8');
      const broken = relativeLinks(text).filter((t) => !existsSync(resolve(repo, t)));
      expect(broken).toEqual([]);
    });
  }
});
