import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { VIEW_EXCLUDED_SECTIONS } from '../src/views/model';
import { buildMarkupDoc, newMarkup, parseMarkupDoc, sanitizeSet, SHEET_CAMERA, SHEET_VIEW } from '../src/markup/model';
import type { MarkupSet } from '../src/markup/model';
import { sanitizeView } from '../src/views/model';
import { MemoryBackend, SheetStore } from '../src/sheets/store';
import type { Sheet, SheetDoc } from '../src/sheets/model';

const PDF = new TextEncoder().encode('%PDF-1.7\nSECRET-PDF-BYTES-1234567890\n%%EOF');
const doc: SheetDoc = { id: 'doc-0123456789abcdef', name: 'a.pdf', bytesKey: 'k1', pageCount: 1, sha256: '0123456789abcdef'.repeat(4), model: null };
const sheet: Sheet = { id: 'doc-0123456789abcdef-p1', docId: doc.id, page: 1, name: 'a', widthPt: 842, heightPt: 595, rotation: 0 };

function sheetSet(): MarkupSet {
  const now = '2026-02-01T10:00:00.000Z';
  return {
    id: 's1', title: 'Review', author: 'x', created: now, updated: now, view: sanitizeView(SHEET_VIEW('Review')) as never, camera: SHEET_CAMERA(), nextNumber: 2,
    markups: [newMarkup('rect', { id: 'm1', number: 1, author: 'x', shape: { points: [[1, 2], [30, 40]], depth: 0 }, attach: { kind: 'none' } })],
    model: null, frame: { kind: 'sheet', sheet: sheet.id },
  };
}

describe('the sheet store', () => {
  it('keeps the bytes apart from the record', async () => {
    const be = new MemoryBackend();
    const s = new SheetStore(async () => be);
    await s.init();
    expect(await s.putBytes('k1', PDF)).toBe(false); // memory backend: not persistent
    s.docs.push(doc);
    s.sheets.push(sheet);
    s.thumbs.set(sheet.id, 'data:image/jpeg;base64,AAAA');
    await s.saveMeta([sheetSet()]);
    const meta = await be.getMeta();
    const text = JSON.stringify(meta);
    expect(text).not.toContain('SECRET-PDF-BYTES');
    expect(text).not.toContain('JVBER'); // base64 of "%PDF-"
    expect(meta!.docs[0]!.bytesKey).toBe('k1');
    expect(meta!.sets[0]!.frame).toEqual({ kind: 'sheet', sheet: sheet.id });
    expect(Array.from((await s.bytesOf(doc))!)).toEqual(Array.from(PDF));
  });

  it('reads the record back in a new session and drops the bytes with the doc', async () => {
    const be = new MemoryBackend();
    const a = new SheetStore(async () => be);
    await a.init();
    await a.putBytes('k1', PDF);
    a.docs.push(doc);
    a.sheets.push(sheet);
    await a.saveMeta([]);
    const b = new SheetStore(async () => be);
    const meta = await b.init();
    expect(meta!.docs).toHaveLength(1);
    expect(b.sheet(sheet.id)!.page).toBe(1);
    expect((await b.bytesOf(doc))!.length).toBe(PDF.length);
    await b.removeDoc(doc.id);
    expect(b.docs).toHaveLength(0);
    expect(await be.getBytes('k1')).toBeNull();
  });

  it('works in memory when IndexedDB is missing', async () => {
    const s = new SheetStore(async () => null);
    await s.init();
    expect(s.persistent).toBe(false);
    await s.putBytes('k', PDF);
    s.docs.push({ ...doc, bytesKey: 'k' });
    expect((await s.bytesOf(s.docs[0]!))!.length).toBe(PDF.length);
  });
});

describe('a sheet sketch in the markup document', () => {
  it('keeps its frame, its points and a read-only flag, with neutral placeholders for the camera', () => {
    const set = sheetSet();
    set.readonly = true;
    const doc1 = buildMarkupDoc({ name: 'm', elementCount: 1, guidCount: 1, guidHash: 'x' }, [set]);
    const back = parseMarkupDoc(JSON.stringify(doc1));
    expect(back.error).toBeUndefined();
    const s = back.sets[0]!;
    expect(s.frame).toEqual({ kind: 'sheet', sheet: sheet.id });
    expect(s.readonly).toBe(true);
    expect(s.markups[0]!.shape!.points).toEqual([[1, 2], [30, 40]]);
    expect(s.camera).toEqual(SHEET_CAMERA());
  });

  it('is read without a camera', () => {
    const raw = JSON.parse(JSON.stringify(sheetSet())) as Record<string, unknown>;
    delete raw['camera'];
    delete raw['view'];
    const r = sanitizeSet(raw);
    expect(typeof r).toBe('object');
  });
});

describe('PDF bytes stay out of the places that travel', () => {
  it('saved views, presets, share links and the params document never take a sheets section', () => {
    expect(VIEW_EXCLUDED_SECTIONS).toContain('sheets');
  });

  it('the sheets code never touches localStorage, sessionStorage, the URL or history', () => {
    const dir = fileURLToPath(new URL('../src/sheets/', import.meta.url));
    const files = (readdirSync(dir) as string[]).filter((f) => f.endsWith('.ts'));
    expect(files.length).toBeGreaterThan(5);
    for (const f of files) {
      const code = readFileSync(dir + f, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
      expect(code, f).not.toMatch(/localStorage|sessionStorage|location\.(hash|search|href\s*=)|history\.(push|replace)State|URLSearchParams/);
    }
    const plugin = readFileSync(fileURLToPath(new URL('../src/plugins/sheets.ts', import.meta.url)), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
    expect(plugin).not.toMatch(/localStorage|sessionStorage|registerParamSection|shareUrl/);
  });

  it('only the store opens IndexedDB, and only for sheets', () => {
    const dir = fileURLToPath(new URL('../src/sheets/', import.meta.url));
    for (const f of readdirSync(dir) as string[]) {
      if (!f.endsWith('.ts') || f === 'store.ts') continue;
      expect(readFileSync(dir + f, 'utf8'), f).not.toMatch(/indexedDB/);
    }
  });
});
