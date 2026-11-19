// The settings of the map and where the secrets live. Nothing here is a params section: the map is in no params document, share link,
// saved view, preset or packed page. The enable switch is never stored: every page starts with the map off. The API key and the
// custom template (which may hold a key) are in the key store (sessionStorage by default, like the classifier's keys), the
// acknowledgement of the privacy notice is a plain flag on this device. Docs: docs-features/map.md.

import { ApiKeyStore, browserKeyStorages } from '../classify/keyStore';
import type { KeyStorages } from '../classify/keyStore';
import type { CustomConfig, ProviderId } from './providers';
import { PROVIDERS } from './providers';

export const MAP_KEY_STORAGE_NAME = 'xray.map.apiKey';
export const MAP_URL_STORAGE_NAME = 'xray.map.customUrl';
export const MAP_NOTICE_STORAGE_NAME = 'xray.map.noticeAck';

export interface MapSettings {
  /** Always false at start. */
  enabled: boolean;
  provider: ProviderId;
  /** 0..1 */
  opacity: number;
  /** Metres, the disc around the model. */
  radius: number;
  /** Attribution text of a custom provider (not a secret). */
  customAttribution: string;
}

export const DEFAULT_RADIUS = 150;
export const MIN_RADIUS = 25;
export const MAX_RADIUS = 1000;

export function defaultMapSettings(): MapSettings {
  return { enabled: false, provider: 'esri', opacity: 1, radius: DEFAULT_RADIUS, customAttribution: '' };
}

export function clampSettings(s: MapSettings): MapSettings {
  const num = (v: unknown, d: number): number => (typeof v === 'number' && Number.isFinite(v) ? v : d);
  return {
    enabled: !!s.enabled,
    provider: s.provider in PROVIDERS || s.provider === 'custom' ? s.provider : 'esri',
    opacity: Math.max(0, Math.min(1, num(s.opacity, 1))),
    radius: Math.max(MIN_RADIUS, Math.min(MAX_RADIUS, num(s.radius, DEFAULT_RADIUS))),
    customAttribution: typeof s.customAttribution === 'string' ? s.customAttribution.slice(0, 200) : '',
  };
}

interface FlagStorage { getItem(k: string): string | null; setItem(k: string, v: string): void }

/** The secrets and the notice flag of the map. */
export class MapSecrets {
  readonly key: ApiKeyStore;
  readonly url: ApiKeyStore;
  private readonly acked = new Set<string>();
  constructor(storages: KeyStorages = browserKeyStorages(), private readonly flags: FlagStorage | null = safeLocal()) {
    this.key = new ApiKeyStore(storages, MAP_KEY_STORAGE_NAME);
    this.url = new ApiKeyStore(storages, MAP_URL_STORAGE_NAME);
    try {
      const raw = this.flags?.getItem(MAP_NOTICE_STORAGE_NAME);
      const list = raw ? JSON.parse(raw) : [];
      if (Array.isArray(list)) for (const h of list) if (typeof h === 'string') this.acked.add(h);
    } catch { /* none */ }
  }

  custom(attribution: string): CustomConfig {
    return { template: this.url.get() ?? '', key: this.key.get(), attribution };
  }

  /** The notice for this host was accepted before (on this device). */
  acknowledged(host: string): boolean {
    return this.acked.has(host);
  }

  acknowledge(host: string): void {
    this.acked.add(host);
    try { this.flags?.setItem(MAP_NOTICE_STORAGE_NAME, JSON.stringify([...this.acked])); } catch { /* remembered for this page */ }
  }
}

function safeLocal(): FlagStorage | null {
  try { return typeof localStorage !== 'undefined' ? localStorage : null; } catch { return null; }
}
