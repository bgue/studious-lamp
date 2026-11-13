import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { sanitizeView } from '../src/views/model';
import { MemoryBackend, SheetStore } from '../src/sheets/store';
import type { Sheet, SheetDoc } from '../src/sheets/model';
import type { SheetPlacement } from '../src/sheets/placement';

const doc: SheetDoc = { id: 'doc-0123456789abcdef', name: 'a.pdf', bytesKey: 'k1', pageCount: 1, sha256: '0123456789abcdef'.repeat(4), model: null };
const placement: SheetPlacement = {
  kind: 'manual', level: { storeyGuid: '3Scp8nJDr5Hwp7hmL8Dm5y', name: 'Level 1', elevation: 0 }, plane: 'plan', transform: { scale: 0.0352778, rotation: 0.349, tx: -4.37, ty: -9.94 },
  residual: 0.0042, source: '3 points', pairs: [{ sheet: [10, 20], model: [1, 2] }, { sheet: [300, 20], model: [11, 3] }, { sheet: [10, 300], model: [-1, 11] }],
};
const sheet: Sheet = { id: 'doc-0123456789abcdef-p1', docId: doc.id, page: 1, name: 'a', widthPt: 842, heightPt: 595, rotation: 0, placement };

describe('a placement is saved with its sheet', () => {
  it('goes into the record in IndexedDB (the store) and comes back in the next session', async () => {
    const be = new MemoryBackend();
    const a = new SheetStore(async () => be);
    await a.init();
    a.docs.push(doc);
    a.sheets.push(sheet);
    await a.saveMeta([]);
    const saved = await be.getMeta();
    expect(saved!.sheets[0]!.placement).toEqual(placement);
    const b = new SheetStore(async () => be);
    await b.init();
    expect(b.sheet(sheet.id)!.placement).toEqual(placement);
  });

  it('a stored placement that is not usable is dropped when read, the sheet stays', async () => {
    const be = new MemoryBackend();
    await be.putMeta({ schema: 'xray-sheets/1', docs: [doc], sheets: [{ ...sheet, placement: { kind: 'manual', level: { elevation: 'x' }, transform: placement.transform } as never }], thumbs: {}, sets: [] });
    const s = new SheetStore(async () => be);
    await s.init();
    expect(s.sheet(sheet.id)).toBeTruthy();
    expect(s.sheet(sheet.id)!.placement).toBeUndefined();
  });

  it('a sheet without a placement saves without the key (stage 1 records read as before)', async () => {
    const be = new MemoryBackend();
    const a = new SheetStore(async () => be);
    await a.init();
    a.docs.push(doc);
    const { placement: _p, ...plain } = sheet;
    a.sheets.push(plain);
    await a.saveMeta([]);
    expect(JSON.stringify(await be.getMeta())).not.toContain('placement');
  });
});

describe('a placement never travels', () => {
  const read = (p: string): string => readFileSync(fileURLToPath(new URL(`../src/${p}`, import.meta.url)), 'utf8');

  it('the modules of URLs, share links, saved views and presets do not know the sheets code', () => {
    for (const f of ['ui/params.ts', 'views/model.ts', 'presets/model.ts', 'plugins/exportParams.ts', 'plugins/views.ts', 'plugins/presets.ts']) {
      expect(read(f), f).not.toMatch(/from '\.\.\/sheets|sheets\/(placement|store|controller)|xraySheets/);
    }
  });

  it('a saved view takes no sheets or placement section', () => {
    const v = sanitizeView({ name: 'x', camera: { position: [0, 0, 1], target: [0, 0, 0] }, sheets: { placement }, placement }) as unknown as Record<string, unknown>;
    expect(JSON.stringify(v)).not.toMatch(/placement|elevation|transform/);
  });

  it('the markup document of a sheet sketch carries the attachment (GlobalIds) but not the placement', () => {
    const src = read('markup/model.ts');
    expect(src).not.toMatch(/placement/);
  });
});
