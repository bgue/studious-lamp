// Tile sources for the map under the model: presets with their attribution, and a custom XYZ template. Pure. Docs: docs-features/map.md.

export type ProviderId = 'esri' | 'osm' | 'custom';

export interface MapProvider {
  id: ProviderId;
  label: string;
  /** XYZ template with {z} {x} {y}; the custom one may also have {key}. */
  template: string;
  /** Shown on screen while the map is drawn. */
  attribution: string;
  /** What the notice names as the party that receives the project's location. */
  host: string;
  minZoom: number;
  maxZoom: number;
  satellite: boolean;
  /** A line for the docs and the panel. */
  note?: string;
}

export const PROVIDERS: Record<Exclude<ProviderId, 'custom'>, MapProvider> = {
  esri: {
    id: 'esri', label: 'Esri World Imagery', template: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Esri, Maxar, Earthstar Geographics, and the GIS User Community', host: 'Esri (server.arcgisonline.com)', minZoom: 1, maxZoom: 19, satellite: true,
  },
  osm: {
    id: 'osm', label: 'OpenStreetMap (street map)', template: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap contributors', host: 'OpenStreetMap (tile.openstreetmap.org)', minZoom: 1, maxZoom: 19, satellite: false,
    note: 'Street map, not satellite. Subject to the OpenStreetMap tile usage policy (https://operations.osmfoundation.org/policies/tiles/): light use only.',
  },
};

export const PROVIDER_LABELS: Array<[string, ProviderId]> = [[PROVIDERS.esri.label, 'esri'], [PROVIDERS.osm.label, 'osm'], ['Custom XYZ template', 'custom']];

export const CUSTOM_HINT = 'https://host/{z}/{x}/{y}.png (optional {key})';

/** A custom template is usable when it is an http(s) URL with {z}, {x} and {y}. Returns the reason when it is not. */
export function validateTemplate(t: string): string | null {
  const s = t.trim();
  if (!s) return 'enter a URL template';
  if (!/^https?:\/\//i.test(s)) return 'the template must start with http:// or https://';
  for (const k of ['{z}', '{x}', '{y}']) if (!s.includes(k)) return `the template needs ${k}`;
  return null;
}

export function templateNeedsKey(t: string): boolean {
  return t.includes('{key}');
}

/** The host of a template, for the notice. */
export function hostOf(t: string): string {
  try {
    return new URL(t.replace(/\{[a-z]+\}/gi, '0')).host || 'the tile server';
  } catch {
    return 'the tile server';
  }
}

export function tileUrl(template: string, z: number, x: number, y: number, key?: string): string {
  return template.replace(/\{z\}/g, String(z)).replace(/\{x\}/g, String(x)).replace(/\{y\}/g, String(y)).replace(/\{key\}/g, key === undefined ? '' : encodeURIComponent(key));
}

export interface CustomConfig {
  template: string;
  key: string | null;
  attribution: string;
}

/** The provider to draw from, or null when a custom one is not usable (no template, or {key} without a key). */
export function activeProvider(id: ProviderId, custom: CustomConfig): { provider: MapProvider; key: string | null; problem: string | null } {
  if (id !== 'custom') return { provider: PROVIDERS[id], key: null, problem: null };
  const bad = validateTemplate(custom.template);
  const needs = templateNeedsKey(custom.template);
  const host = hostOf(custom.template);
  const provider: MapProvider = {
    id: 'custom', label: 'Custom XYZ template', template: custom.template.trim(), attribution: custom.attribution.trim() || `Map tiles: ${host}`,
    host, minZoom: 0, maxZoom: 22, satellite: true,
  };
  return { provider, key: custom.key, problem: bad ?? (needs && !custom.key ? 'this template needs an API key' : null) };
}

/** The notice that comes before the first request to a provider. */
export function privacyNotice(host: string): string {
  return `Map tiles are fetched from ${host}; this reveals the project's location to them.`;
}
