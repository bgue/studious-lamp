// Sheets: the data model of PDF drawing sheets, and the maths between PDF user space and the displayed page. Pure: no DOM, no
// PDF library. Tested in tests/sheets-model.test.ts.
//
// A PDF becomes a SheetDoc (one file: name, byte store key, page count, SHA-256) and one Sheet per page. Ids come from the
// SHA-256 of the bytes, so the same PDF has the same ids in every session, and a BCF file or a sketch JSON that names a sheet
// finds it again when the same PDF is opened.
//
// A sheet sketch is a MarkupSet whose `frame` is `{ kind: 'sheet', sheet: <sheet id> }`. Its shapes are PDF user-space points
// of the page (x right, y up, origin and units of the page's default user space, before /Rotate). The displayed page is turned by
// `rotation`; `userToDisplay` / `displayToUser` convert. Stage 2 (registering a sheet to the model) adds `placement` to Sheet.

import type { ModelIdentity } from '../markup/model';

export type Rotation = 0 | 90 | 180 | 270;

/** [xMin, yMin, xMax, yMax] of the page in user space (the visible box, before rotation). */
export type PageBox = [number, number, number, number];

export interface SheetDoc {
  id: string;
  name: string;
  /** Key of the PDF bytes in the byte store (IndexedDB). The bytes are never kept in the document record. */
  bytesKey: string;
  pageCount: number;
  /** SHA-256 of the bytes, lowercase hex. */
  sha256: string;
  /** The model that was loaded when the PDF was opened (scope.ts); null: none was loaded. */
  model?: ModelIdentity | null;
}

export interface Sheet {
  id: string;
  docId: string;
  /** 1-based page number. */
  page: number;
  name: string;
  /** Size of the displayed page (after rotation), PDF points (1/72 inch). */
  widthPt: number;
  heightPt: number;
  rotation: Rotation;
  /** The visible box in user space. Absent: [0, 0, w, h] of the unrotated page. */
  box?: PageBox;
  /** Stage 2: how the sheet sits in the model. Not used yet. */
  placement?: undefined;
}

export const DOC_PREFIX = 'doc-';

export function docIdOf(sha256: string): string {
  return `${DOC_PREFIX}${sha256.slice(0, 16)}`;
}
export function sheetIdOf(docId: string, page: number): string {
  return `${docId}-p${page}`;
}
export function parseSheetId(id: string): { docId: string; page: number } | null {
  const m = /^(doc-[0-9a-f]{16})-p(\d+)$/.exec(id);
  return m ? { docId: m[1]!, page: Number(m[2]) } : null;
}

/** Lowercase hex SHA-256 (Web Crypto; the page and node 20+ have it). */
export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const d = await crypto.subtle.digest('SHA-256', bytes as Uint8Array<ArrayBuffer>);
  return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, '0')).join('');
}

export function cleanRotation(r: number): Rotation {
  const n = ((Math.round(r / 90) * 90) % 360 + 360) % 360;
  return n === 90 || n === 180 || n === 270 ? n : 0;
}

/** The visible box of a sheet in user space. */
export function boxOf(s: Pick<Sheet, 'widthPt' | 'heightPt' | 'rotation' | 'box'>): PageBox {
  if (s.box) return s.box;
  const turned = s.rotation === 90 || s.rotation === 270;
  return [0, 0, turned ? s.heightPt : s.widthPt, turned ? s.widthPt : s.heightPt];
}

/** A user-space point to the displayed page: points from the top left corner, y down. */
export function userToDisplay(s: Pick<Sheet, 'widthPt' | 'heightPt' | 'rotation' | 'box'>, x: number, y: number): [number, number] {
  const b = boxOf(s);
  const w0 = b[2] - b[0];
  const h0 = b[3] - b[1];
  const lx = x - b[0];
  const ly = y - b[1];
  switch (s.rotation) {
    case 90: return [ly, lx];
    case 180: return [w0 - lx, ly];
    case 270: return [h0 - ly, w0 - lx];
    default: return [lx, h0 - ly];
  }
}

/** The inverse of userToDisplay. */
export function displayToUser(s: Pick<Sheet, 'widthPt' | 'heightPt' | 'rotation' | 'box'>, dx: number, dy: number): [number, number] {
  const b = boxOf(s);
  const w0 = b[2] - b[0];
  const h0 = b[3] - b[1];
  let lx: number;
  let ly: number;
  switch (s.rotation) {
    case 90: lx = dy; ly = dx; break;
    case 180: lx = w0 - dx; ly = dy; break;
    case 270: lx = w0 - dy; ly = h0 - dx; break;
    default: lx = dx; ly = h0 - dy;
  }
  return [lx + b[0], ly + b[1]];
}

/** Flat user-space points to flat displayed points. */
export function pointsToDisplay(s: Pick<Sheet, 'widthPt' | 'heightPt' | 'rotation' | 'box'>, flat: ArrayLike<number>): number[] {
  const out: number[] = [];
  for (let i = 0; i + 1 < flat.length; i += 2) out.push(...userToDisplay(s, flat[i]!, flat[i + 1]!));
  return out;
}

/**
 * Drawing units per point: stroke widths, text sizes and badges are authored for a screen of about 800 units across the long
 * side of the page, so a large sheet (A1, E-size) gets proportionally thicker lines and bigger text than an A4 page.
 */
export function sheetUnit(s: Pick<Sheet, 'widthPt' | 'heightPt'>): number {
  return Math.max(1, Math.max(s.widthPt, s.heightPt) / 800);
}

export const r2 = (v: number): number => Math.round(v * 100) / 100;

/** The sheets of a doc, in page order. */
export function sheetsOfDoc(sheets: readonly Sheet[], docId: string): Sheet[] {
  return sheets.filter((s) => s.docId === docId).sort((a, b) => a.page - b.page);
}

/** "Plan.pdf" -> "Plan"; "Plan.pdf", page 2 of 5 -> "Plan, page 2". */
export function sheetName(docName: string, page: number, pageCount: number): string {
  const base = docName.replace(/\.pdf$/i, '').trim() || 'Sheet';
  return pageCount > 1 ? `${base}, page ${page}` : base;
}

/** The sheet a sketch is drawn on, or undefined. */
export function sheetOf(sheets: readonly Sheet[], set: { frame?: { kind: string; sheet?: string } }): Sheet | undefined {
  return set.frame?.kind === 'sheet' ? sheets.find((s) => s.id === set.frame!.sheet) : undefined;
}
