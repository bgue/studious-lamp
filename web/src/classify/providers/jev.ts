// The HTTP provider for the decision model Jev. The wire format is in ../jevAdapter.ts; this file only sends the request and
// maps failures to ProviderError. The API key is read at call time through `apiKey()`, is sent in the Authorization header
// to the configured endpoint only, and never appears in an error message or a log line.

import { buildRequest, parseResponse, requestHeaders } from '../jevAdapter';
import type { Answers, JsonObject, Questions } from '../jevAdapter';
import { ProviderError } from '../types';
import type { DecideExtra, DecisionModel } from '../types';

export interface JevOptions {
  /** Provider id that the object reports: `jev` (default) or `d3` (the System One endpoint of d3-edge: same wire format). */
  provider?: string;
  /** Send `images` when the request has them. Off by default: only a server that reads images may get them. */
  sendImages?: boolean;
  endpoint: string;
  model: string;
  /** Returns the key, or null/'' for none (a same-origin proxy adds it). */
  apiKey: () => string | null;
  timeoutMs: number;
  fetchImpl?: typeof fetch;
}

function retryAfter(h: Headers): number | undefined {
  const v = h.get('retry-after');
  if (!v) return undefined;
  const n = Number(v);
  if (Number.isFinite(n)) return Math.max(0, Math.min(120_000, n * 1000));
  const t = Date.parse(v);
  return Number.isFinite(t) ? Math.max(0, Math.min(120_000, t - Date.now())) : undefined;
}

/** Strip anything that looks like a bearer token or the key itself from text that may be shown. */
export function redact(text: string, key: string | null): string {
  let t = text;
  if (key) t = t.split(key).join('[key]');
  return t.replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/g, 'Bearer [key]');
}

export function createJevProvider(o: JevOptions): DecisionModel {
  return {
    provider: o.provider ?? 'jev',
    async decide(state: JsonObject, questions: Questions, signal: AbortSignal, extra?: DecideExtra): Promise<Answers> {
      const f = o.fetchImpl ?? globalThis.fetch.bind(globalThis);
      const key = o.apiKey();
      const ctl = new AbortController();
      let timedOut = false;
      const onAbort = (): void => ctl.abort();
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      signal.addEventListener('abort', onAbort, { once: true });
      const timer = setTimeout(() => {
        timedOut = true;
        ctl.abort();
      }, o.timeoutMs);
      try {
        let res: Response;
        try {
          res = await f(o.endpoint, { method: 'POST', headers: requestHeaders(key), body: JSON.stringify(buildRequest(o.model, state, questions, o.sendImages ? extra?.images : undefined)), signal: ctl.signal, credentials: 'omit' });
        } catch (e) {
          if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
          if (timedOut) throw new ProviderError(`The request timed out after ${Math.round(o.timeoutMs / 1000)} s.`, undefined, undefined, true);
          const m = e instanceof Error ? redact(e.message, key) : 'unknown error';
          throw new ProviderError(`Could not reach the endpoint (${m}). A browser blocks the call when the endpoint does not allow cross-origin requests (CORS). Use a same-origin proxy URL instead.`);
        }
        if (!res.ok) {
          const body = redact((await res.text().catch(() => '')).slice(0, 200).replace(/\s+/g, ' '), key);
          if (res.status === 401 || res.status === 403) throw new ProviderError(`The endpoint rejected the credentials (HTTP ${res.status}). Check the API key.`, res.status);
          const retryable = res.status === 429 || res.status === 408 || res.status >= 500;
          throw new ProviderError(`The endpoint answered HTTP ${res.status}${body ? `: ${body}` : ''}.`, res.status, retryAfter(res.headers), retryable);
        }
        let json: unknown;
        try {
          json = await res.json();
        } catch {
          throw new ProviderError('The endpoint answered with text that is not JSON.');
        }
        return parseResponse(json, questions);
      } finally {
        clearTimeout(timer);
        signal.removeEventListener('abort', onAbort);
      }
    },
  };
}
