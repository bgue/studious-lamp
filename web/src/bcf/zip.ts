// Minimal zip reader and writer for BCF archives. Pure TypeScript with no DOM dependency: it uses
// DecompressionStream / CompressionStream('deflate-raw'), which exist in browsers and in node 22.
//
// Reader: central directory based (so data descriptors are fine), stored (0) and deflate (8) entries, CRC32 checked,
// backslash separators normalised to '/', no zip64, no encryption.
// Writer: UTF-8 names (flag bit 11), directory entries for every folder (the BCF guide asks for them), deflate when
// CompressionStream exists and it makes the entry smaller, stored otherwise.

const SIG_LOCAL = 0x04034b50;
const SIG_CENTRAL = 0x02014b50;
const SIG_EOCD = 0x06054b50;
/** Hard limit per entry after inflating (a guard against zip bombs; BCF parts are small). */
const MAX_ENTRY = 256 * 1024 * 1024;

let crcTable: Uint32Array | null = null;

export function crc32(data: Uint8Array, seed = 0): number {
  if (!crcTable) {
    crcTable = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crcTable[n] = c >>> 0;
    }
  }
  let c = ~seed >>> 0;
  for (let i = 0; i < data.length; i++) c = crcTable[(c ^ data[i]!) & 0xff]! ^ (c >>> 8);
  return ~c >>> 0;
}

async function pipeAll(data: Uint8Array, stream: { writable: WritableStream<Uint8Array>; readable: ReadableStream<Uint8Array> }): Promise<Uint8Array> {
  const w = stream.writable.getWriter();
  const done = (async () => {
    await w.write(data as Uint8Array<ArrayBuffer>);
    await w.close();
  })();
  const out = new Uint8Array(await new Response(stream.readable).arrayBuffer());
  await done;
  return out;
}

/** Raw deflate of `data`, or null when CompressionStream is unavailable. */
export async function deflateRaw(data: Uint8Array): Promise<Uint8Array | null> {
  if (typeof CompressionStream === 'undefined') return null;
  try {
    return await pipeAll(data, new CompressionStream('deflate-raw') as unknown as Parameters<typeof pipeAll>[1]);
  } catch {
    return null;
  }
}

export async function inflateRaw(data: Uint8Array): Promise<Uint8Array> {
  if (typeof DecompressionStream === 'undefined') throw new Error('this browser cannot inflate zip entries (no DecompressionStream)');
  return pipeAll(data, new DecompressionStream('deflate-raw') as unknown as Parameters<typeof pipeAll>[1]);
}

// ---------------------------------------------------------------- reader

export interface ZipEntry {
  /** Normalised name with '/' separators. Folder entries end with '/'. */
  name: string;
  size: number;
  compressedSize: number;
  method: number;
  isDirectory: boolean;
  /** Entry contents, inflated and CRC checked. */
  read(): Promise<Uint8Array>;
}

export function isZipData(data: Uint8Array): boolean {
  return data.length >= 4 && data[0] === 0x50 && data[1] === 0x4b && (data[2] === 0x03 || data[2] === 0x05);
}

export function readZip(input: Uint8Array | ArrayBuffer): ZipEntry[] {
  const data = input instanceof Uint8Array ? input : new Uint8Array(input);
  const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
  let eocd = -1;
  for (let i = data.length - 22; i >= Math.max(0, data.length - 65557); i--) {
    if (dv.getUint32(i, true) === SIG_EOCD) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new Error('not a valid zip archive (no end of central directory)');
  const count = dv.getUint16(eocd + 10, true);
  let p = dv.getUint32(eocd + 16, true);
  if (count === 0xffff || p === 0xffffffff) throw new Error('zip64 archives are not supported');
  const dec = new TextDecoder('utf-8');
  const out: ZipEntry[] = [];
  for (let n = 0; n < count; n++) {
    if (p + 46 > data.length || dv.getUint32(p, true) !== SIG_CENTRAL) throw new Error('zip central directory is corrupt');
    const flags = dv.getUint16(p + 8, true);
    const method = dv.getUint16(p + 10, true);
    const crc = dv.getUint32(p + 16, true);
    const csize = dv.getUint32(p + 20, true);
    const usize = dv.getUint32(p + 24, true);
    const nlen = dv.getUint16(p + 28, true);
    const xlen = dv.getUint16(p + 30, true);
    const clen = dv.getUint16(p + 32, true);
    const lho = dv.getUint32(p + 42, true);
    const rawName = dec.decode(data.subarray(p + 46, p + 46 + nlen));
    p += 46 + nlen + xlen + clen;
    if (flags & 1) throw new Error(`zip entry "${rawName}" is encrypted`);
    const name = rawName.replace(/\\/g, '/');
    const isDirectory = name.endsWith('/');
    out.push({
      name,
      size: usize,
      compressedSize: csize,
      method,
      isDirectory,
      async read(): Promise<Uint8Array> {
        if (isDirectory) return new Uint8Array(0);
        if (usize > MAX_ENTRY) throw new Error(`zip entry "${name}" is too large`);
        if (lho + 30 > data.length || dv.getUint32(lho, true) !== SIG_LOCAL) throw new Error(`zip entry "${name}" has a bad local header`);
        const start = lho + 30 + dv.getUint16(lho + 26, true) + dv.getUint16(lho + 28, true);
        if (start + csize > data.length) throw new Error(`zip entry "${name}" is truncated`);
        const comp = data.subarray(start, start + csize);
        let bytes: Uint8Array;
        if (method === 0) bytes = comp.slice();
        else if (method === 8) bytes = await inflateRaw(comp);
        else throw new Error(`zip entry "${name}" uses unsupported compression method ${method}`);
        if (bytes.length !== usize) throw new Error(`zip entry "${name}" is corrupt (size mismatch)`);
        if (crc32(bytes) !== crc) throw new Error(`zip entry "${name}" is corrupt (CRC mismatch)`);
        return bytes;
      },
    });
  }
  return out;
}

// ---------------------------------------------------------------- writer

export interface ZipInput {
  name: string;
  data: Uint8Array;
  /** Force storing (PNG snapshots do not deflate). Default: deflate when it helps. */
  store?: boolean;
}

function dosDateTime(d: Date): [number, number] {
  const year = Math.max(1980, d.getUTCFullYear());
  const time = (d.getUTCHours() << 11) | (d.getUTCMinutes() << 5) | (d.getUTCSeconds() >> 1);
  const date = ((year - 1980) << 9) | ((d.getUTCMonth() + 1) << 5) | d.getUTCDate();
  return [time, date];
}

/** Build a zip archive. Folder entries are added for every parent folder of the given names. */
export async function writeZip(files: ZipInput[], opts: { date?: Date; compress?: boolean } = {}): Promise<Uint8Array> {
  const enc = new TextEncoder();
  const [dtime, ddate] = dosDateTime(opts.date ?? new Date());
  const compress = opts.compress !== false;

  // Folders first, in order of first appearance, then the files.
  const names: Array<{ name: string; data: Uint8Array | null; store: boolean }> = [];
  const seenDirs = new Set<string>();
  for (const f of files) {
    const parts = f.name.split('/');
    for (let i = 1; i < parts.length; i++) {
      const dir = `${parts.slice(0, i).join('/')}/`;
      if (!seenDirs.has(dir)) {
        seenDirs.add(dir);
        names.push({ name: dir, data: null, store: true });
      }
    }
    names.push({ name: f.name, data: f.data, store: f.store === true });
  }

  const chunks: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const e of names) {
    const nameBytes = enc.encode(e.name);
    const raw = e.data ?? new Uint8Array(0);
    let body = raw;
    let method = 0;
    if (e.data && compress && !e.store && raw.length > 32) {
      const d = await deflateRaw(raw);
      if (d && d.length < raw.length) {
        body = d;
        method = 8;
      }
    }
    const crc = e.data ? crc32(raw) : 0;
    const local = new Uint8Array(30 + nameBytes.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, SIG_LOCAL, true);
    lv.setUint16(4, method === 8 ? 20 : 10, true);
    lv.setUint16(6, 0x0800, true);
    lv.setUint16(8, method, true);
    lv.setUint16(10, dtime, true);
    lv.setUint16(12, ddate, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, body.length, true);
    lv.setUint32(22, raw.length, true);
    lv.setUint16(26, nameBytes.length, true);
    lv.setUint16(28, 0, true);
    local.set(nameBytes, 30);

    const cd = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(cd.buffer);
    cv.setUint32(0, SIG_CENTRAL, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, method === 8 ? 20 : 10, true);
    cv.setUint16(8, 0x0800, true);
    cv.setUint16(10, method, true);
    cv.setUint16(12, dtime, true);
    cv.setUint16(14, ddate, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, body.length, true);
    cv.setUint32(24, raw.length, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint32(38, e.data ? 0 : 0x10, true); // external attributes: MS-DOS directory bit
    cv.setUint32(42, offset, true);
    cd.set(nameBytes, 46);

    chunks.push(local, body);
    central.push(cd);
    offset += local.length + body.length;
  }
  const cdSize = central.reduce((s, c) => s + c.length, 0);
  const eocd = new Uint8Array(22);
  const ev = new DataView(eocd.buffer);
  ev.setUint32(0, SIG_EOCD, true);
  ev.setUint16(8, names.length, true);
  ev.setUint16(10, names.length, true);
  ev.setUint32(12, cdSize, true);
  ev.setUint32(16, offset, true);
  if (offset > 0xfffffffe || names.length > 0xfffe) throw new Error('archive too large for a plain zip');

  const total = offset + cdSize + 22;
  const out = new Uint8Array(total);
  let o = 0;
  for (const c of [...chunks, ...central, eocd]) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}
