// User-facing text for IFC reader failures. web-ifc throws its own internal errors on damaged input (for example
// "Cannot read properties of undefined (reading 'arguments')"); those mean nothing to a user. The loader shows one
// friendly line instead and logs the raw text to the console. Our own reader errors (IfcReadError: empty file, no
// ISO-10303-21 header, no geometry, out of memory) are already written for people and pass through unchanged.

/** Codes of IfcReadError (ifcRaw.ts) and of the worker's error message whose text is already user-facing. */
const FRIENDLY_CODES = new Set(['invalid', 'empty', 'no-geometry', 'cancelled', 'wasm', 'memory']);

export const IFC_UNREADABLE = 'This IFC file could not be read: it may be damaged or not an IFC file';

/** A reader failure with a friendly message; `detail` is the raw text from web-ifc (console only). */
export class IfcUnreadable extends Error {
  constructor(message: string, readonly detail: string) {
    super(message);
    this.name = 'IfcUnreadable';
  }
}

/** The raw text without our own "IFC reader failed: " prefix (worker and importer add it). */
function rawDetail(message: string): string {
  return message.replace(/^IFC reader failed:\s*/i, '').replace(/\s+/g, ' ').trim();
}

/**
 * Map an error thrown while reading IFC files to what the user sees. Errors with a user-facing code (IfcReadError, the
 * worker's `code`) pass through; anything else (web-ifc internals, a crashed worker) becomes IfcUnreadable with the
 * one-line message, naming the file when there is one. Pure.
 */
export function friendlyIfcError(e: unknown, fileName?: string): Error {
  const err = e instanceof Error ? e : new Error(String(e));
  const code = (err as { code?: unknown }).code;
  const prefixed = /^IFC reader failed:/i.test(err.message);
  if (typeof code === 'string' && FRIENDLY_CODES.has(code) && !prefixed) return err;
  const detail = rawDetail(err.message) || err.name || 'unknown error';
  return new IfcUnreadable(fileName ? `${IFC_UNREADABLE} (${fileName})` : IFC_UNREADABLE, detail);
}
