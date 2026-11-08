// Where the API key lives. Nowhere else: not in the settings, not in params documents, share links, saved views, presets
// or packed pages. By default the key is kept in sessionStorage (gone when the tab closes); the person may tick "remember
// on this device" to keep it in localStorage. It is sent only to the configured endpoint, and it is never logged.
//
// A key that a page holds can be read by anyone who uses that browser profile. For a shared deployment, use a same-origin
// proxy that adds the key on the server, and leave the key box empty.

import type { KeyValueStorage } from './cache';

export const KEY_STORAGE_NAME = 'xray.classify.apiKey';

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
  constructor(private readonly s: KeyStorages) {}

  /** The key, or null when none is set. */
  get(): string | null {
    try {
      const v = this.s.session?.getItem(KEY_STORAGE_NAME) ?? this.s.local?.getItem(KEY_STORAGE_NAME);
      if (v) return v;
    } catch {
      /* storage blocked */
    }
    return this.mem;
  }

  /** True when the key is kept on this device (localStorage). */
  remembered(): boolean {
    try {
      return !!this.s.local?.getItem(KEY_STORAGE_NAME);
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
        this.s.local?.setItem(KEY_STORAGE_NAME, k);
        this.s.session?.removeItem(KEY_STORAGE_NAME);
      } else {
        this.s.session?.setItem(KEY_STORAGE_NAME, k);
        this.s.local?.removeItem(KEY_STORAGE_NAME);
      }
    } catch {
      /* the key stays in memory for this page */
    }
  }

  clear(): void {
    this.mem = null;
    try {
      this.s.session?.removeItem(KEY_STORAGE_NAME);
      this.s.local?.removeItem(KEY_STORAGE_NAME);
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
