// Where a secret lives (the API key of Jev, and the Hugging Face token). Nowhere else: not in the settings, not in params documents, share links, saved views, presets
// or packed pages. By default the key is kept in sessionStorage (gone when the tab closes); the person may tick "remember
// on this device" to keep it in localStorage. It is sent only to the configured endpoint, and it is never logged.
//
// A key that a page holds can be read by anyone who uses that browser profile. For a shared deployment, use a same-origin
// proxy that adds the key on the server, and leave the key box empty.

import type { KeyValueStorage } from './cache';

export const KEY_STORAGE_NAME = 'xray.classify.apiKey';
/** The Hugging Face token (gated or private models) lives in its own entry, with exactly the same rules as the API key. */
export const HF_TOKEN_STORAGE_NAME = 'xray.classify.hfToken';
/** The API key of a d3 endpoint has its own entry: a Jev key is never sent to a d3 server, and the other way round. Same rules. */
export const D3_KEY_STORAGE_NAME = 'xray.classify.d3Key';

export interface KeyStorages {
  session: KeyValueStorage | null;
  local: KeyValueStorage | null;
}

export function browserKeyStorages(): KeyStorages {
  const pick = (f: () => Storage): KeyValueStorage | null => {
    try {
      return f();
    } catch {
      return null;
    }
  };
  return { session: pick(() => window.sessionStorage), local: pick(() => window.localStorage) };
}

export class ApiKeyStore {
  private mem: string | null = null;
  /** `name` is the storage entry. The same class holds the Jev API key and the Hugging Face token. */
  constructor(private readonly s: KeyStorages, private readonly name: string = KEY_STORAGE_NAME) {}

  /** The key, or null when none is set. */
  get(): string | null {
    try {
      const v = this.s.session?.getItem(this.name) ?? this.s.local?.getItem(this.name);
      if (v) return v;
    } catch {
      /* storage blocked */
    }
    return this.mem;
  }

  /** True when the key is kept on this device (localStorage). */
  remembered(): boolean {
    try {
      return !!this.s.local?.getItem(this.name);
    } catch {
      return false;
    }
  }

  /** Keep a key. `remember` true: in localStorage (opt-in). Otherwise: in sessionStorage only. An empty key clears it. */
  set(key: string, remember = false): void {
    const k = key.trim();
    if (!k) return this.clear();
    this.mem = k;
    try {
      if (remember) {
        this.s.local?.setItem(this.name, k);
        this.s.session?.removeItem(this.name);
      } else {
        this.s.session?.setItem(this.name, k);
        this.s.local?.removeItem(this.name);
      }
    } catch {
      /* the key stays in memory for this page */
    }
  }

  clear(): void {
    this.mem = null;
    try {
      this.s.session?.removeItem(this.name);
      this.s.local?.removeItem(this.name);
    } catch {
      /* ignore */
    }
  }

  /** What the UI may show: no part of the key. */
  mask(): string {
    const k = this.get();
    return k ? `set (${k.length} characters, hidden)` : 'not set';
  }
}
