// The map key, the custom template (it may hold a key) and the place of a model never leave the key store and IndexedDB: not in the params
// document, the share link, saved views, presets, packed pages or localStorage. The map is off by default. Same method as the
// classifier's key test (tests/classify-settings.test.ts).
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { collectParams, encodeShare, paramSectionNames, shareSubset, shareUrl } from '../src/ui/params';
import { captureView } from '../src/views/capture';
import type { ViewsApp } from '../src/views/capture';
import { encodeViewShare, VIEW_EXCLUDED_SECTIONS } from '../src/views/model';
import { capturePreset } from '../src/presets/engine';
import { buildBoot, injectTemplate, injectionScript, parseArgs, INJECT_BEGIN, INJECT_END } from '../tools/pack/lib.mjs';
import { MemoryStorage } from '../src/selectionSets';
import { MapSecrets, defaultMapSettings } from '../src/map/settings';
import { LocationStore, MemoryLocationBackend } from '../src/map/store';
import type { KeyValueStorage } from '../src/classify/cache';
import { fakeApp } from './presets-helpers';

const here = dirname(fileURLToPath(import.meta.url));
const MAP_KEY = 'mapkey-LIVE-QWERTY-0123456789';
const CUSTOM_KEY_IN_URL = 'urlkey-LIVE-ZXCVBN-9876543210';
const CUSTOM_URL = `https://tiles.example.org/{z}/{x}/{y}.png?token=${CUSTOM_KEY_IN_URL}`;
const kv = (m: MemoryStorage): KeyValueStorage => m as unknown as KeyValueStorage;

describe('the map is off by default', () => {
  it('starts with enabled false, and nothing in the page asks for a tile at load', () => {
    expect(defaultMapSettings().enabled).toBe(false);
    // the plugin builds the controller and the panel only; the tile cache is asked from MapLayer.update, which the controller calls only while enabled
    const plugin = readFileSync(resolve(here, '../src/plugins/map.ts'), 'utf8');
    expect(plugin).not.toMatch(/registerParamSection/); // the map is a params section of nothing: no document, link, view, preset or packed page
    expect(plugin).not.toMatch(/\bfetch\(/);
    const ctl = readFileSync(resolve(here, '../src/map/controller.ts'), 'utf8');
    expect(ctl).toMatch(/if \(!this\.settings\.enabled\) return false;/);
    const settings = readFileSync(resolve(here, '../src/map/settings.ts'), 'utf8');
    expect(settings).not.toMatch(/setItem\([^)]*enabled/); // the switch is never stored
  });
});

describe('the map key and the custom URL never leave the key store', () => {
  it('are absent from the params, the share link, saved views, presets, packed pages and localStorage', async () => {
    const session = new MemoryStorage(), local = new MemoryStorage(), flags = new MemoryStorage();
    const secrets = new MapSecrets({ session: kv(session), local: kv(local) }, flags as never);
    secrets.key.set(MAP_KEY, true); // even with "remember on this device"
    secrets.url.set(CUSTOM_URL, true);
    secrets.acknowledge('tiles.example.org');
    const store = new LocationStore(new MemoryLocationBackend()); // IndexedDB in the browser
    await store.set('building', { lat: 48.123456, lon: 11.654321, rotation: 33.25 });

    const f = fakeApp();
    const doc = collectParams(f.app, f.env);
    const docText = JSON.stringify(doc);
    const b64 = (s: string): string => btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const needles = [MAP_KEY, CUSTOM_KEY_IN_URL, 'tiles.example.org', '48.123456', '11.654321', '33.25'];
    const has = (text: string): boolean => needles.some((k) => text.includes(k) || text.includes(b64(k)) || text.includes(encodeURIComponent(k)));
    expect(has(docText)).toBe(false);
    expect(paramSectionNames()).not.toContain('map');
    expect(Object.keys(doc)).not.toContain('map');

    const url = shareUrl(doc, { origin: 'https://x.test', pathname: '/viewer' });
    expect(has(url)).toBe(false);
    expect(has(encodeShare(shareSubset(doc)))).toBe(false);
    expect(has(JSON.stringify(doc, null, 2))).toBe(false);

    const cap = capturePreset(f.app as never, ['map'], { name: 'p' } as never, f.env as never);
    expect(has(JSON.stringify(cap.preset))).toBe(false);

    expect(VIEW_EXCLUDED_SECTIONS).toContain('map');
    const va = f.app as ViewsApp;
    (va.controller as unknown as { selection: Set<number> }).selection = new Set();
    const cam = va.renderer.camera as unknown as Record<string, unknown>;
    cam['up'] = { x: 0, y: 1, z: 0, set() {} };
    cam['fov'] = 45;
    const view = captureView(va, 'v', { paramsEnv: f.env });
    expect(has(JSON.stringify(view))).toBe(false);
    expect(has(encodeViewShare('building', view, null))).toBe(false);

    const { options } = parseArgs(['a.glb', '-o', 'x.html']);
    const boot = buildBoot('m', options, doc, [view]);
    const page = injectTemplate(`<!doctype html><html><head><title>old</title></head><body><script>\n${INJECT_BEGIN}\n${INJECT_END}\n</script></body></html>`, { models: {}, boot, title: 't' });
    expect(has(page)).toBe(false);
    expect(has(injectionScript({}, boot))).toBe(false);

    // the key and the template are in the key store (session, then local for "remember"), the notice flag has only a host name, nothing else is written
    expect(local.getItem('xray.map.apiKey')).toBe(MAP_KEY);
    expect(local.getItem('xray.map.customUrl')).toBe(CUSTOM_URL);
    expect([...flags.map.keys()]).toEqual(['xray.map.noticeAck']);
    expect([...flags.map.values()].join()).not.toMatch(/mapkey|urlkey|48\.123/);
    expect([...session.map.keys(), ...local.map.keys()].sort()).toEqual(['xray.map.apiKey', 'xray.map.customUrl']);
  });
});
