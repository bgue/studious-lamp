// The viewer release number a build carries (the "What's new" note compares it with the number the browser last saw).
//
//   default      the last released number: ../tools/viewer-release.txt (what a development or smoke-test server shows)
//   RELEASE=1    that number + 1: the release being built. ../tools/release_viewer.sh bumps the counter AFTER the build, so
//                a release build must say RELEASE=1; the script then checks the built file carries the number it names.
//
// releasePlugin() is used by vite.config.ts, bench/vite.smoke.config.mjs and vite.single.config.ts. It defines the
// constant __XRAY_RELEASE__ for src/whatsnew/ and writes <meta name="xray-release" content="N"> into index.html.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

/** The repository root: the folder above web/. */
export const repoRoot = resolve(here, '..', '..');

/** The release number to build in, or null when the counter file is missing or unreadable. */
export function releaseNumber(env = process.env) {
  let last = NaN;
  try {
    last = parseInt(readFileSync(resolve(repoRoot, 'tools', 'viewer-release.txt'), 'utf8').replace(/[^0-9]/g, ''), 10);
  } catch {
    /* no counter file: the number stays unknown */
  }
  if (!Number.isFinite(last)) return null;
  const releasing = env.RELEASE !== undefined && env.RELEASE !== '' && env.RELEASE !== '0';
  return releasing ? last + 1 : last;
}

/** Vite plugin: the constant and the meta tag. */
export function releasePlugin() {
  const n = releaseNumber();
  return {
    name: 'xray-release',
    config: () => ({ define: { __XRAY_RELEASE__: n === null ? 'null' : String(n) } }),
    transformIndexHtml: () => (n === null ? [] : [{ tag: 'meta', attrs: { name: 'xray-release', content: String(n) }, injectTo: 'head-prepend' }]),
  };
}
