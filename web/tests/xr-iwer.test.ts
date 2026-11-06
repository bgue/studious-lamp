// The headless WebXR test with the emulated device iwer runs in a real browser (Chromium through Playwright, with a dev
// server), which takes minutes with software rendering, so it is a script: bench/smoke-xr.mjs. This test runs it when
// XRAY_XR=1 is set (for example `XRAY_XR=1 SMOKE_PORT=5411 npx vitest run tests/xr-iwer.test.ts`) and checks its exit code;
// otherwise it only checks that the pieces the script needs are in place (iwer installed as a dev dependency only, not in the
// app's dependencies, and not imported by any file under src/).
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function walk(dir: string, out: string[] = []): string[] {
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

describe('iwer, the WebXR emulation runtime (dev dependency)', () => {
  const pkg = JSON.parse(readFileSync(join(web, 'package.json'), 'utf8')) as { dependencies?: Record<string, string>; devDependencies?: Record<string, string> };

  it('is a dev dependency at 2.7.0 and not a runtime dependency', () => {
    expect(pkg.devDependencies?.iwer).toBe('2.7.0');
    expect(pkg.dependencies?.iwer).toBeUndefined();
  });

  it('is imported by nothing under src/ (the app and its bundles never contain it)', () => {
    const hits = walk(join(web, 'src')).filter((f) => /\.(ts|js|mjs)$/.test(f) && /\biwer\b/i.test(readFileSync(f, 'utf8')));
    expect(hits).toEqual([]);
  });

  it('has the browser build the smoke script injects', () => {
    expect(existsSync(join(web, 'node_modules/iwer/build/iwer.js'))).toBe(true);
  });
});

describe.skipIf(!process.env.XRAY_XR)('headless WebXR session against the emulated device', () => {
  it('passes bench/smoke-xr.mjs (enter VR, select with the controller, exit, restore; enter AR, place, scale)', () => {
    const r = spawnSync('node', ['bench/smoke-xr.mjs', 'fzk'], { cwd: web, env: { ...process.env, SMOKE_PORT: process.env.SMOKE_PORT ?? '5411' }, encoding: 'utf8', timeout: 15 * 60 * 1000 });
    if (r.status !== 0) console.log(r.stdout, r.stderr);
    expect(r.status).toBe(0);
  }, 16 * 60 * 1000);
});

describe.skipIf(!process.env.XRAY_XR)('headless field AR session against the emulated device', () => {
  it('passes bench/smoke-xr-field.mjs (registration, anchors, looks, cut, restore, snapshot, USDZ)', () => {
    const r = spawnSync('node', ['bench/smoke-xr-field.mjs'], { cwd: web, env: { ...process.env, SMOKE_PORT: process.env.SMOKE_PORT ?? '5652' }, encoding: 'utf8', timeout: 45 * 60 * 1000 });
    if (r.status !== 0) console.log(r.stdout, r.stderr);
    expect(r.status).toBe(0);
  }, 46 * 60 * 1000);
});
