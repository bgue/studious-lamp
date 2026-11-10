// The sample projects: the models that ship with the viewer, with the readable label that the "Sample Projects" folder shows.
// The names are the `?model=` values and the keys of the saved views, presets and selection sets, so they never change; only
// the labels are for people. Pure (no DOM): the panel, the loader and the single-file bundle use it.

export interface SampleProject {
  /** The `?model=` value and the model name in saved views, presets and sets. */
  name: string;
  /** The readable label in the folder, the command list and the status bar. */
  label: string;
}

export const SAMPLE_PROJECTS: readonly SampleProject[] = [
  { name: 'building', label: 'Building (Simple-Scene)' },
  { name: 'fzk-haus', label: 'FZK-Haus' },
  { name: 'plumbing', label: 'Plumbing' },
  { name: 'process-plant', label: 'Process plant' },
  { name: 'synth5k', label: 'Synthetic 5k' },
  { name: 'debris-demo', label: 'Debris demo' },
  { name: 'procedural', label: 'Procedural' },
];

/** What a single-file bundle says about the models inside it. Not a single file: null (the served app loads every sample). */
export interface BundleContents {
  /** Models embedded as glb with their sidecar (window.__xrayEmbeddedModels). */
  models: readonly string[];
  /** Models embedded as gzip-compressed IFC (window.__xrayEmbeddedIfc), read by the built-in IFC reader. */
  ifc: readonly string[];
}

/** The plain hint for a sample that a single file does not carry. */
export const UNAVAILABLE_HINT = 'needs the served app or the zip';

/** Gzip-compressed IFC of a sample, as the single-file bundle embeds it: the file name and the base64 bytes. */
export interface EmbeddedIfc {
  file: string;
  gz: string;
}

declare global {
  interface Window {
    /** Single-file bundles: name -> gzip-compressed IFC (base64). The viewer inflates it and reads it with the IFC reader. */
    __xrayEmbeddedIfc?: Record<string, EmbeddedIfc>;
  }
}

/** The contents of the bundle the page runs in, or null outside a single file. */
export function bundleContents(): BundleContents | null {
  const models = window.__xrayEmbeddedModels;
  if (!models) return null;
  return { models: Object.keys(models), ifc: Object.keys(window.__xrayEmbeddedIfc ?? {}) };
}

/** Can the sample be loaded here? Everything is, except what a single file does not carry. */
export function sampleAvailable(name: string, bundle: BundleContents | null): boolean {
  if (!bundle) return true;
  return name === 'procedural' || bundle.models.includes(name) || bundle.ifc.includes(name);
}

export interface MenuEntry {
  /** The model name that selecting the entry loads. */
  value: string;
  /** The text of the entry. An unavailable sample says why. */
  label: string;
  available: boolean;
}

/**
 * The entries of the Sample Projects menu, in order: every sample, then the models the bundle embeds that are not samples
 * (a packed file names its own), then the models the user opened from files in this session.
 */
export function sampleMenu(bundle: BundleContents | null, opened: readonly string[] = []): MenuEntry[] {
  const out: MenuEntry[] = [];
  const seen = new Set<string>();
  const add = (value: string, label: string, available: boolean): void => {
    if (seen.has(value)) return;
    seen.add(value);
    out.push({ value, label: available ? label : `${label} (${UNAVAILABLE_HINT})`, available });
  };
  for (const s of SAMPLE_PROJECTS) add(s.name, s.label, sampleAvailable(s.name, bundle));
  for (const name of [...(bundle?.models ?? []), ...(bundle?.ifc ?? [])]) add(name, name, true);
  for (const name of opened) add(name, `${name} (opened file)`, true);
  return out;
}

/** The menu as lil-gui takes it: label -> value. Labels are unique, so no entry is lost. */
export function menuOptions(entries: readonly MenuEntry[]): Record<string, string> {
  return Object.fromEntries(entries.map((e) => [e.label, e.value]));
}

/** The gzip-compressed sample inflated (DecompressionStream, Chromium, Firefox and Node 18+). */
export async function inflateEmbedded(base64: string): Promise<ArrayBuffer> {
  const bin = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const stream = new Blob([bin]).stream().pipeThrough(new DecompressionStream('gzip'));
  return await new Response(stream).arrayBuffer();
}
