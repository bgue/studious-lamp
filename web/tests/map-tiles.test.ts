// Tile cache (LRU, queue order, concurrency, retry, abort), providers and templates, the location store, the settings and the controller:
// nothing is requested while the map is off. No real network: the fetcher is a fake.
import { describe, expect, it } from 'vitest';
import { TileCache } from '../src/map/tiles';
import { PROVIDERS, activeProvider, hostOf, privacyNotice, templateNeedsKey, tileUrl, validateTemplate } from '../src/map/providers';
import { LocationStore, MemoryLocationBackend } from '../src/map/store';
import type { LocationBackend } from '../src/map/store';
import { MapSecrets, clampSettings, defaultMapSettings, MAP_KEY_STORAGE_NAME, MAP_URL_STORAGE_NAME } from '../src/map/settings';
import { MapController, groundLevel } from '../src/map/controller';
import { MemoryStorage } from '../src/selectionSets';
import type { KeyValueStorage } from '../src/classify/cache';

const kv = (m: MemoryStorage): KeyValueStorage => m as unknown as KeyValueStorage;

interface Deferred { url: string; resolve(v: { width: number; height: number }): void; reject(e: unknown): void; signal: AbortSignal }
function fakeFetcher(): { fetcher: (url: string, signal: AbortSignal) => Promise<{ width: number; height: number }>; calls: Deferred[]; urls: string[] } {
  const calls: Deferred[] = [];
  const urls: string[] = [];
  return {
    calls, urls,
    fetcher: (url, signal) => new Promise((resolve, reject) => { urls.push(url); calls.push({ url, resolve, reject, signal }); }),
  };
}
const tick = (): Promise<void> => new Promise((r) => setTimeout(r, 0));

describe('the tile cache', () => {
  it('asks for a tile once, serves it from memory, and loads nearest first with a limit on requests in flight', async () => {
    const f = fakeFetcher();
    const c = new TileCache({ fetcher: f.fetcher as never, concurrency: 2 });
    for (let i = 0; i < 5; i++) c.request(`k${i}`, `u${i}`, 10 - i); // k4 is the nearest
    expect(f.urls).toEqual(['u0', 'u1']); // the first two went out at once, as the queue was empty when they came
    f.calls[0]!.resolve({ width: 256, height: 256 });
    await tick();
    expect(f.urls[2]).toBe('u4'); // the next to go is the nearest of those waiting
    c.request('k0', 'u0', 0); // again: no second request
    expect(f.urls.filter((u) => u === 'u0')).toHaveLength(1);
    expect(c.get('k0')!.state).toBe('ready');
    expect(c.stats.requested).toBe(3);
  });

  it('evicts the least recently used finished tile beyond its capacity', async () => {
    const f = fakeFetcher();
    const gone: string[] = [];
    const c = new TileCache({ fetcher: f.fetcher as never, capacity: 3, concurrency: 10, onEvict: (e) => gone.push(e.key) });
    for (const k of ['a', 'b', 'c']) c.request(k, k, 0);
    for (const call of f.calls) call.resolve({ width: 1, height: 1 });
    await tick();
    c.request('a', 'a', 0); // a is used again: b is now the oldest
    c.request('d', 'd', 0);
    f.calls[3]!.resolve({ width: 1, height: 1 });
    await tick();
    expect(gone).toEqual(['b']);
    expect(c.entries.size).toBe(3);
    expect(c.stats.evicted).toBe(1);
  });

  it('never evicts a tile that is still loading', async () => {
    const f = fakeFetcher();
    const c = new TileCache({ fetcher: f.fetcher as never, capacity: 1, concurrency: 10 });
    for (const k of ['a', 'b', 'c']) c.request(k, k, 0);
    f.calls[0]!.resolve({ width: 1, height: 1 });
    await tick();
    expect(c.get('b')!.state).toBe('loading');
    expect(c.get('c')!.state).toBe('loading');
  });

  it('marks a failed tile and asks again only after a pause', async () => {
    const f = fakeFetcher();
    let t = 0;
    const c = new TileCache({ fetcher: f.fetcher as never, retryAfterMs: 1000, now: () => t });
    c.request('a', 'a', 0);
    f.calls[0]!.reject(new Error('404'));
    await tick();
    expect(c.get('a')!.state).toBe('error');
    c.request('a', 'a', 0);
    expect(f.urls).toHaveLength(1);
    t = 1500;
    c.request('a', 'a', 0);
    expect(f.urls).toHaveLength(2);
    expect(c.get('a')!.state).toBe('loading');
  });

  it('aborts what is in flight on cancelAll and ignores a late answer', async () => {
    const f = fakeFetcher();
    const c = new TileCache({ fetcher: f.fetcher as never, concurrency: 1 });
    c.request('a', 'a', 0);
    c.request('b', 'b', 1);
    c.cancelAll();
    expect(f.calls[0]!.signal.aborted).toBe(true);
    f.calls[0]!.resolve({ width: 1, height: 1 });
    await tick();
    expect(c.get('a')).toBeUndefined();
    expect(c.pending).toBe(0);
    c.request('c', 'c', 0); // works again
    expect(f.urls).toEqual(['a', 'c']);
  });
});

describe('providers', () => {
  it('has the presets with their attribution and the Esri and OpenStreetMap templates', () => {
    expect(PROVIDERS.esri.template).toBe('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}');
    expect(PROVIDERS.esri.attribution).toBe('Esri, Maxar, Earthstar Geographics, and the GIS User Community');
    expect(PROVIDERS.osm.attribution).toBe('© OpenStreetMap contributors');
    expect(PROVIDERS.osm.satellite).toBe(false);
    expect(PROVIDERS.osm.note).toMatch(/tile usage policy/i);
  });
  it('fills a template (Esri puts y before x)', () => {
    expect(tileUrl(PROVIDERS.esri.template, 18, 139000, 91000)).toBe('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/18/91000/139000');
    expect(tileUrl(PROVIDERS.osm.template, 3, 4, 5)).toBe('https://tile.openstreetmap.org/3/4/5.png');
    expect(tileUrl('https://t.example/{z}/{x}/{y}.jpg?key={key}', 1, 2, 3, 'a b&c')).toBe('https://t.example/1/2/3.jpg?key=a%20b%26c');
  });
  it('validates a custom template', () => {
    expect(validateTemplate('')).toMatch(/enter/);
    expect(validateTemplate('ftp://x/{z}/{x}/{y}')).toMatch(/http/);
    expect(validateTemplate('https://x/{z}/{x}')).toMatch(/\{y\}/);
    expect(validateTemplate('https://x/{z}/{x}/{y}.png')).toBeNull();
    expect(templateNeedsKey('https://x/{z}/{x}/{y}?k={key}')).toBe(true);
    expect(hostOf('https://tiles.example.org:8443/{z}/{x}/{y}.png')).toBe('tiles.example.org:8443');
  });
  it('needs a key when the template has {key}', () => {
    const none = activeProvider('custom', { template: 'https://t.example/{z}/{x}/{y}?k={key}', key: null, attribution: '' });
    expect(none.problem).toMatch(/key/);
    const ok = activeProvider('custom', { template: 'https://t.example/{z}/{x}/{y}?k={key}', key: 'K', attribution: 'Tiles by Example' });
    expect(ok.problem).toBeNull();
    expect(ok.provider.attribution).toBe('Tiles by Example');
    expect(activeProvider('custom', { template: 'https://t.example/{z}/{x}/{y}', key: null, attribution: '' }).provider.attribution).toMatch(/t\.example/);
  });
  it('words the notice as asked', () => {
    expect(privacyNotice('Esri (server.arcgisonline.com)')).toBe("Map tiles are fetched from Esri (server.arcgisonline.com); this reveals the project's location to them.");
  });
});

describe('the location store', () => {
  it('keeps a location per model and forgets it', async () => {
    const s = new LocationStore(new MemoryLocationBackend());
    expect(await s.get('a')).toBeNull();
    await s.set('a', { lat: 1, lon: 2, rotation: 3 });
    await s.set('b', { lat: 4, lon: 5, rotation: 6 });
    expect(await s.get('a')).toEqual({ lat: 1, lon: 2, rotation: 3 });
    await s.clear('a');
    expect(await s.get('a')).toBeNull();
    expect(await s.get('b')).toEqual({ lat: 4, lon: 5, rotation: 6 });
  });
  it('survives a broken backend: the page keeps the location in memory', async () => {
    const broken: LocationBackend = { get: async () => { throw new Error('x'); }, put: async () => { throw new Error('x'); }, delete: async () => { throw new Error('x'); } };
    const s = new LocationStore(broken);
    await s.set('a', { lat: 1, lon: 2, rotation: 0 });
    expect(await s.get('a')).toEqual({ lat: 1, lon: 2, rotation: 0 });
    expect(await s.get('zzz')).toBeNull();
  });
});

describe('the settings', () => {
  it('are off by default, with the Esri provider, full opacity and a 150 m radius', () => {
    expect(defaultMapSettings()).toEqual({ enabled: false, provider: 'esri', opacity: 1, radius: 150, customAttribution: '' });
  });
  it('clamp what is out of range', () => {
    expect(clampSettings({ ...defaultMapSettings(), opacity: 7, radius: 1e9 })).toMatchObject({ opacity: 1, radius: 1000 });
    expect(clampSettings({ ...defaultMapSettings(), opacity: -1, radius: 1 })).toMatchObject({ opacity: 0, radius: 25 });
    expect(clampSettings({ ...defaultMapSettings(), provider: 'x' as never }).provider).toBe('esri');
  });
  it('keep the key and the custom template in the key store only (session by default) and remember the notice per host', () => {
    const session = new MemoryStorage(), local = new MemoryStorage(), flags = new MemoryStorage();
    const s = new MapSecrets({ session: kv(session), local: kv(local) }, flags as never);
    s.key.set('SECRET-1');
    s.url.set('https://t.example/{z}/{x}/{y}?key=SECRET-2');
    expect(session.getItem(MAP_KEY_STORAGE_NAME)).toBe('SECRET-1');
    expect(session.getItem(MAP_URL_STORAGE_NAME)).toContain('SECRET-2');
    expect(local.map.size).toBe(0);
    expect(s.acknowledged('h')).toBe(false);
    s.acknowledge('h');
    expect(new MapSecrets({ session: kv(session), local: kv(local) }, flags as never).acknowledged('h')).toBe(true);
    expect([...flags.map.values()].join()).not.toMatch(/SECRET/);
  });
});

function ctlWith(opts: { confirm?: (t: string, h: string) => Promise<boolean>; model?: Partial<Parameters<typeof groundLevel>[0]> & { mapConversion?: never; siteGeo?: { lat: number; lon: number } } } = {}) {
  const f = fakeFetcher();
  let dirty = 0;
  const session = new MemoryStorage(), local = new MemoryStorage(), flags = new MemoryStorage();
  const model = { originShift: [0, 0, 0] as [number, number, number], storeys: [{ id: 0, name: 'G', elevation: 0 }, { id: 1, name: 'U', elevation: -3 }], elements: [], ...(opts.model ?? {}) };
  const camera = { position: { x: 30, y: 20, z: 30 }, fov: 45 };
  const c = new MapController({
    host: { scene: { add() {}, remove() {} } as never, camera: camera as never, viewportPx: () => 800, markDirty: () => void dirty++, model: () => model as never, modelName: () => 'm' },
    fetcher: f.fetcher as never,
    store: new LocationStore(new MemoryLocationBackend()),
    secrets: new MapSecrets({ session: kv(session), local: kv(local) }, flags as never),
    ...(opts.confirm ? { confirm: opts.confirm } : {}),
  });
  return { c, f, session, local, flags, dirty: () => dirty };
}

describe('the controller', () => {
  it('requests nothing while the map is off, whatever the camera does', async () => {
    const { c, f } = ctlWith({ model: { siteGeo: { lat: 49.1, lon: 8.43 } } });
    await c.onModel();
    for (let i = 0; i < 5; i++) c.tick(i * 16);
    expect(c.state().enabled).toBe(false);
    expect(c.state().visible).toBe(false);
    expect(f.urls).toEqual([]);
    expect(c.state().status).toBe('From IfcSite');
  });

  it('needs the notice before the first request: no answer, no request; yes, tiles', async () => {
    const asked: string[] = [];
    const { c, f } = ctlWith({ confirm: async (t) => { asked.push(t); return false; }, model: { siteGeo: { lat: 49.1, lon: 8.43 } } });
    await c.onModel();
    expect(await c.setEnabled(true)).toBe(false);
    expect(asked).toEqual(["Map tiles are fetched from Esri (server.arcgisonline.com); this reveals the project's location to them."]);
    c.tick(0);
    expect(f.urls).toEqual([]);
    const yes = ctlWith({ confirm: async () => true, model: { siteGeo: { lat: 49.1, lon: 8.43 } } });
    await yes.c.onModel();
    expect(await yes.c.setEnabled(true)).toBe(true);
    yes.c.tick(0);
    expect(yes.f.urls.length).toBeGreaterThan(0);
    expect(yes.f.urls.every((u) => u.startsWith('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/'))).toBe(true);
  });

  it('asks the notice once per host, and turns off again without a request', async () => {
    let n = 0;
    const { c } = ctlWith({ confirm: async () => (n++, true), model: { siteGeo: { lat: 49.1, lon: 8.43 } } });
    await c.onModel();
    await c.setEnabled(true);
    await c.setEnabled(false);
    await c.setEnabled(true);
    expect(n).toBe(1);
  });

  it('does not draw an unknown place, and says so', async () => {
    const { c, f } = ctlWith({ confirm: async () => true });
    await c.onModel();
    await c.setEnabled(true);
    c.tick(0);
    expect(f.urls).toEqual([]);
    expect(c.state().status).toBe('Unknown');
  });

  it('uses a manual place, keeps it per model, and the ground is the lowest storey', async () => {
    const { c, f } = ctlWith({ confirm: async () => true, model: { originShift: [0, 0, 2] } });
    await c.onModel();
    await c.setManual({ lat: 52.52, lon: 13.405, rotation: 20 });
    expect(c.state().status).toBe('Manual');
    expect(c.groundY).toBeCloseTo(-3 - 2, 9); // lowest storey -3 minus the shift
    expect(c.groundBasis).toBe('lowest storey');
    await c.setEnabled(true);
    c.tick(0);
    expect(f.urls.length).toBeGreaterThan(0);
    // a second page over the same store finds it again
    const c2 = new MapController({ host: { scene: { add() {}, remove() {} } as never, camera: { position: { x: 1, y: 1, z: 1 }, fov: 45 } as never, viewportPx: () => 800, markDirty() {}, model: () => ({ originShift: [0, 0, 0], storeys: [], elements: [] }) as never, modelName: () => 'm' }, fetcher: f.fetcher as never, store: (c as unknown as { o: { store: LocationStore } }).o.store });
    await c2.onModel();
    expect(c2.manual).toEqual({ lat: 52.52, lon: 13.405, rotation: 20 });
    await c.setManual(null);
    expect(c.state().status).toBe('Unknown');
  });

  it('refuses a custom template that needs a key it does not have', async () => {
    const { c, f } = ctlWith({ confirm: async () => true, model: { siteGeo: { lat: 49.1, lon: 8.43 } } });
    await c.onModel();
    c.patch({ provider: 'custom' });
    c.secrets.url.set('https://t.example/{z}/{x}/{y}?k={key}');
    c.recompute();
    expect(await c.setEnabled(true)).toBe(false);
    expect(c.problem).toMatch(/key/);
    c.tick(0);
    expect(f.urls).toEqual([]);
    c.secrets.key.set('K');
    expect(await c.setEnabled(true)).toBe(true);
    c.tick(0);
    expect(f.urls.every((u) => u.startsWith('https://t.example/') && u.endsWith('?k=K'))).toBe(true);
  });

  it('finds the ground level: the lowest storey, else the bottom of the model', () => {
    expect(groundLevel({ originShift: [0, 0, 1], storeys: [{ id: 0, name: 'a', elevation: 3 }, { id: 1, name: 'b', elevation: 0.5 }], elements: [] }).y).toBeCloseTo(-0.5, 9);
    const el = (y: number) => ({ bounds: [0, y, 0, 1, y + 1, 1] }) as never;
    expect(groundLevel({ originShift: [0, 0, 1], storeys: [], elements: [el(2), el(-1.5)] })).toEqual({ y: -1.5, basis: 'bottom of the model' });
    expect(groundLevel({ originShift: [0, 0, 0], storeys: [], elements: [] }).y).toBe(0);
  });
});
