// Retry with backoff for the decision model: HTTP 429 and 5xx (and timeouts) are retried; anything else fails at once.

import { ProviderError } from './types';

export interface RetryOptions {
  /** Retries after the first try. Default 4. */
  retries?: number;
  baseMs?: number;
  maxMs?: number;
  /** Fraction of random extra delay. Default 0.2; tests pass 0. */
  jitter?: number;
  /** Replace the wait (tests). Must reject with an AbortError when the signal aborts. */
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

export function abortableSleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException('Aborted', 'AbortError'));
    const t = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = (): void => {
      clearTimeout(t);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

export const isAbort = (e: unknown): boolean => !!e && typeof e === 'object' && (e as { name?: string }).name === 'AbortError';

/** Call `fn`; on a retryable ProviderError wait (Retry-After, else exponential) and try again. */
export async function withBackoff<T>(fn: () => Promise<T>, signal: AbortSignal, o: RetryOptions = {}, onRetry?: (attempt: number, waitMs: number, why: string) => void): Promise<T> {
  const retries = o.retries ?? 4;
  const base = o.baseMs ?? 500;
  const max = o.maxMs ?? 20_000;
  const jitter = o.jitter ?? 0.2;
  const sleep = o.sleep ?? abortableSleep;
  for (let attempt = 0; ; attempt++) {
    try {
      return await fn();
    } catch (e) {
      if (isAbort(e) || signal.aborted) throw e;
      if (!(e instanceof ProviderError) || !e.retryable || attempt >= retries) throw e;
      const wait = (e.retryAfterMs ?? Math.min(max, base * 2 ** attempt)) * (1 + Math.random() * jitter);
      onRetry?.(attempt + 1, wait, e.message);
      await sleep(wait, signal);
    }
  }
}
