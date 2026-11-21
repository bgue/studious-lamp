// The saved animation scripts of one model, and the .xrayanim file format. Pure apart from the storage it is given.
//
// Scripts are the user's own text. They live only in this browser's localStorage, under one key per model
// (`xray.anim.<model identity key>`, identityKey of src/markup/scope.ts), and in the .xrayanim files the user exports. They are never
// part of the parameters document, a share link, a saved view, a preset or a packed page (tests/animscript-leak.test.ts checks).

export const ANIM_STORAGE_PREFIX = 'xray.anim.';
export const ANIM_FILE_EXT = '.xrayanim';
export const MAX_SCRIPTS = 100;
export const MAX_NAME = 60;
export const MAX_FILE_CHARS = 200_000;

export interface SavedScript {
  name: string;
  text: string;
  /** ms since the epoch. */
  savedAt: number;
}

export interface ScriptDoc {
  version: 1;
  scripts: SavedScript[];
  /** The text in the editor when the page was left: a convenience, not a saved script. */
  draft?: { name: string; text: string };
}

export interface ScriptStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export const storageKeyFor = (modelKey: string): string => `${ANIM_STORAGE_PREFIX}${modelKey}`;

export const emptyDoc = (): ScriptDoc => ({ version: 1, scripts: [] });

/** A clean script name: trimmed, one line, not too long. */
export function cleanName(name: string): string {
  return name.replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, MAX_NAME);
}

/** Read a model's scripts. Never throws; bad data reads as an empty store. */
export function loadDoc(storage: ScriptStorage | null, modelKey: string): ScriptDoc {
  try {
    const raw = storage?.getItem(storageKeyFor(modelKey));
    if (!raw) return emptyDoc();
    const v = JSON.parse(raw) as Partial<ScriptDoc> | null;
    if (!v || v.version !== 1 || !Array.isArray(v.scripts)) return emptyDoc();
    const scripts: SavedScript[] = [];
    for (const s of v.scripts.slice(0, MAX_SCRIPTS)) {
      if (s && typeof s.name === 'string' && typeof s.text === 'string' && cleanName(s.name)) {
        scripts.push({ name: cleanName(s.name), text: s.text.slice(0, MAX_FILE_CHARS), savedAt: typeof s.savedAt === 'number' ? s.savedAt : 0 });
      }
    }
    const d = v.draft;
    const draft = d && typeof d.text === 'string' ? { name: typeof d.name === 'string' ? cleanName(d.name) : '', text: d.text.slice(0, MAX_FILE_CHARS) } : undefined;
    return { version: 1, scripts, ...(draft ? { draft } : {}) };
  } catch {
    return emptyDoc();
  }
}

/** Write a model's scripts. False when the storage refused (full, private mode). */
export function saveDoc(storage: ScriptStorage | null, modelKey: string, doc: ScriptDoc): boolean {
  try {
    if (!storage) return false;
    storage.setItem(storageKeyFor(modelKey), JSON.stringify(doc));
    return true;
  } catch {
    return false;
  }
}

/** Add a script or replace the one with the same name (case-insensitive). Returns the new document. */
export function upsertScript(doc: ScriptDoc, name: string, text: string, now: number = Date.now()): ScriptDoc {
  const n = cleanName(name);
  if (!n) return doc;
  const rest = doc.scripts.filter((s) => s.name.toLowerCase() !== n.toLowerCase());
  const scripts = [...rest, { name: n, text: text.slice(0, MAX_FILE_CHARS), savedAt: now }].slice(-MAX_SCRIPTS);
  scripts.sort((a, b) => a.name.localeCompare(b.name));
  return { ...doc, scripts };
}

export function removeScript(doc: ScriptDoc, name: string): ScriptDoc {
  const l = name.toLowerCase();
  return { ...doc, scripts: doc.scripts.filter((s) => s.name.toLowerCase() !== l) };
}

export function findScript(doc: ScriptDoc, name: string): SavedScript | undefined {
  const l = name.trim().toLowerCase();
  return doc.scripts.find((s) => s.name.toLowerCase() === l);
}

/** A name that no saved script has: "Walk", "Walk 2", "Walk 3". */
export function uniqueScriptName(doc: ScriptDoc, wanted: string): string {
  const base = cleanName(wanted) || 'Script';
  if (!findScript(doc, base)) return base;
  for (let i = 2; i < 1000; i++) if (!findScript(doc, `${base} ${i}`)) return `${base} ${i}`;
  return `${base} ${Date.now()}`;
}

// ---------------------------------------------------------------- .xrayanim files

/** The file text of a script: the script itself, line ends as \n, one trailing newline. */
export function exportText(text: string): string {
  const t = text.replace(/\r\n?/g, '\n');
  return t.endsWith('\n') ? t : `${t}\n`;
}

/** A safe file name for an export: `Walk around.xrayanim`. */
export function exportFileName(name: string): string {
  const base = cleanName(name).replace(/[\\/:*?"<>|]+/g, '-').replace(/^\.+/, '') || 'script';
  return `${base}${ANIM_FILE_EXT}`;
}

export interface ImportedScript {
  name: string;
  text: string;
}

/** Read an imported file: strips a byte order mark and normalises line ends; the name is the file name without its extension. */
export function importText(fileName: string, content: string): ImportedScript | { error: string } {
  if (content.length > MAX_FILE_CHARS) return { error: `The file is too large (more than ${MAX_FILE_CHARS} characters).` };
  if (content.includes('\u0000')) return { error: 'The file is not a text file.' };
  const text = content.replace(/^﻿/, '').replace(/\r\n?/g, '\n');
  const name = cleanName(fileName.replace(/^.*[\\/]/, '').replace(/\.(xrayanim|txt)$/i, '')) || 'Imported script';
  return { name, text };
}
