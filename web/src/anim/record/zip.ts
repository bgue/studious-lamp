// A small store-only zip builder for PNG image sequences. Entries are kept as Blob parts, so a long sequence does not have to sit
// in memory as one big buffer (the browser keeps blobs outside the JS heap). No compression: PNG frames do not deflate. At most
// 65535 entries and 4 GB (no zip64). The CRC32 and the zip layout are those of src/bcf/zip.ts, whose readZip reads the result.

import { crc32 } from '../../bcf/zip';

const SIG_LOCAL = 0x04034b50;
const SIG_CENTRAL = 0x02014b50;
const SIG_EOCD = 0x06054b50;
const MAX_ENTRIES = 65535;
const MAX_BYTES = 0xffffffff - 1024 * 1024;

export class StoreZip {
  private readonly parts: BlobPart[] = [];
  private readonly central: Uint8Array[] = [];
  private offset = 0;
  private readonly dtime: number;
  private readonly ddate: number;
  private readonly enc = new TextEncoder();

  constructor(date: Date = new Date()) {
    const year = Math.max(1980, date.getUTCFullYear());
    this.dtime = (date.getUTCHours() << 11) | (date.getUTCMinutes() << 5) | (date.getUTCSeconds() >> 1);
    this.ddate = ((year - 1980) << 9) | ((date.getUTCMonth() + 1) << 5) | date.getUTCDate();
  }

  get count(): number {
    return this.central.length;
  }

  get bytes(): number {
    return this.offset;
  }

  /** Add a file. Throws when the archive would pass the limits of a plain zip. */
  add(name: string, data: Uint8Array): void {
    if (this.central.length >= MAX_ENTRIES) throw new Error('A zip file holds at most 65535 frames. Use a lower frame rate or a shorter fly-through.');
    if (this.offset + data.length > MAX_BYTES) throw new Error('The frames are over 4 GB. Use a smaller size or a shorter fly-through.');
    const nameBytes = this.enc.encode(name);
    const crc = crc32(data);
    const local = new Uint8Array(30 + nameBytes.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, SIG_LOCAL, true);
    lv.setUint16(4, 10, true);
    lv.setUint16(6, 0x0800, true);
    lv.setUint16(8, 0, true);
    lv.setUint16(10, this.dtime, true);
    lv.setUint16(12, this.ddate, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, data.length, true);
    lv.setUint32(22, data.length, true);
    lv.setUint16(26, nameBytes.length, true);
    lv.setUint16(28, 0, true);
    local.set(nameBytes, 30);

    const cd = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(cd.buffer);
    cv.setUint32(0, SIG_CENTRAL, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 10, true);
    cv.setUint16(8, 0x0800, true);
    cv.setUint16(10, 0, true);
    cv.setUint16(12, this.dtime, true);
    cv.setUint16(14, this.ddate, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, data.length, true);
    cv.setUint32(24, data.length, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint32(42, this.offset, true);
    cd.set(nameBytes, 46);

    this.parts.push(local as Uint8Array<ArrayBuffer>, data as Uint8Array<ArrayBuffer>);
    this.central.push(cd);
    this.offset += local.length + data.length;
  }

  /** The archive as a Blob. */
  finish(): Blob {
    let cdSize = 0;
    for (const c of this.central) cdSize += c.length;
    const eocd = new Uint8Array(22);
    const ev = new DataView(eocd.buffer);
    ev.setUint32(0, SIG_EOCD, true);
    ev.setUint16(8, this.central.length, true);
    ev.setUint16(10, this.central.length, true);
    ev.setUint32(12, cdSize, true);
    ev.setUint32(16, this.offset, true);
    return new Blob([...this.parts, ...(this.central as Uint8Array<ArrayBuffer>[]), eocd as Uint8Array<ArrayBuffer>], { type: 'application/zip' });
  }
}

/** `frame-000001.png` style names, 1-based. */
export function frameFileName(index: number, prefix = 'frame'): string {
  return `${prefix}-${String(index + 1).padStart(6, '0')}.png`;
}
