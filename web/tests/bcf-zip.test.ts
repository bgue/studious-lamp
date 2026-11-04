import { describe, expect, it } from 'vitest';
import { crc32, deflateRaw, isZipData, readZip, writeZip } from '../src/bcf/zip';

const enc = new TextEncoder();
const text = (n: number): Uint8Array => enc.encode('<a>hello bcf zip </a>\n'.repeat(n));

describe('bcf zip', () => {
  it('crc32 matches the known check value', () => {
    expect(crc32(enc.encode('123456789'))).toBe(0xcbf43926);
  });

  it('round trips stored entries', async () => {
    const files = [{ name: 'bcf.version', data: text(1) }, { name: 'dir/sub/a.txt', data: text(3) }, { name: 'empty.bin', data: new Uint8Array(0) }];
    const zip = await writeZip(files, { compress: false });
    expect(isZipData(zip)).toBe(true);
    const entries = readZip(zip);
    expect(entries.filter((e) => !e.isDirectory).map((e) => e.name)).toEqual(['bcf.version', 'dir/sub/a.txt', 'empty.bin']);
    expect(entries.every((e) => e.method === 0)).toBe(true);
    for (const f of files) {
      const e = entries.find((x) => x.name === f.name)!;
      expect(Array.from(await e.read())).toEqual(Array.from(f.data));
    }
  });

  it('round trips deflated entries and keeps small entries smaller', async () => {
    const big = text(2000);
    const zip = await writeZip([{ name: 'a/big.xml', data: big }, { name: 'a/tiny.txt', data: enc.encode('x') }]);
    const entries = readZip(zip);
    const e = entries.find((x) => x.name === 'a/big.xml')!;
    expect(e.method).toBe(8);
    expect(e.compressedSize).toBeLessThan(big.length / 4);
    expect(Array.from(await e.read())).toEqual(Array.from(big));
    expect(entries.find((x) => x.name === 'a/tiny.txt')!.method).toBe(0);
    expect(zip.length).toBeLessThan(big.length / 2);
  });

  it('adds directory entries for every folder, as the BCF encoding guide asks', async () => {
    const zip = await writeZip([{ name: 'guid/markup.bcf', data: text(1) }, { name: 'guid/viewpoint.bcfv', data: text(1) }]);
    const dirs = readZip(zip).filter((e) => e.isDirectory).map((e) => e.name);
    expect(dirs).toEqual(['guid/']);
  });

  it('inflates what CompressionStream produced and reads UTF-8 names', async () => {
    const d = await deflateRaw(text(100));
    expect(d).not.toBeNull();
    const zip = await writeZip([{ name: 'größe/ü.txt', data: text(100) }]);
    expect(readZip(zip).some((e) => e.name === 'größe/ü.txt')).toBe(true);
  });

  it('detects corruption and bad input', async () => {
    const zip = await writeZip([{ name: 'a.txt', data: text(5) }], { compress: false });
    const e = readZip(zip).find((x) => x.name === 'a.txt')!;
    const bad = zip.slice();
    bad[30 + 'a.txt'.length + 3] = bad[30 + 'a.txt'.length + 3]! ^ 0xff; // a payload byte
    await expect(readZip(bad).find((x) => x.name === 'a.txt')!.read()).rejects.toThrow(/CRC/);
    expect(Array.from(await e.read()).length).toBe(text(5).length);
    expect(() => readZip(new Uint8Array([1, 2, 3, 4, 5]))).toThrow(/zip/);
    expect(isZipData(new Uint8Array([1, 2, 3, 4]))).toBe(false);
  });

  it('normalises backslash separators when reading', async () => {
    const zip = await writeZip([{ name: 'x\\y.txt', data: text(1) }], { compress: false });
    expect(readZip(zip).some((e) => e.name === 'x/y.txt')).toBe(true);
  });
});
