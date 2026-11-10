// A small hand-written PDF 1.7 writer for the markup report: pages with JPEG images (DCTDecode), Helvetica text
// (WinAnsi), lines, rectangles, link annotations and embedded files (EmbeddedFiles name tree, so a reader can attach the
// JSON that restores the marked-up view). No DOM, no dependencies; tested in node (tests/markup-pdf.test.ts).
//
// Coordinates are PDF points with the origin at the bottom left. Streams are written uncompressed, so an embedded file
// can be found again byte for byte without an inflate step (extractAttachments also reads FlateDecode streams).

// ---------------------------------------------------------------- text encoding (WinAnsi)

/** Characters of the 0x80..0x9F range of WinAnsi (Windows-1252). */
const WIN_HIGH: Record<number, number> = {
  0x20ac: 0x80, 0x201a: 0x82, 0x0192: 0x83, 0x201e: 0x84, 0x2026: 0x85, 0x2020: 0x86, 0x2021: 0x87, 0x02c6: 0x88, 0x2030: 0x89,
  0x0160: 0x8a, 0x2039: 0x8b, 0x0152: 0x8c, 0x017d: 0x8e, 0x2018: 0x91, 0x2019: 0x92, 0x201c: 0x93, 0x201d: 0x94, 0x2022: 0x95,
  0x2013: 0x96, 0x2014: 0x97, 0x02dc: 0x98, 0x2122: 0x99, 0x0161: 0x9a, 0x203a: 0x9b, 0x0153: 0x9c, 0x017e: 0x9e, 0x0178: 0x9f,
};

/** Characters that WinAnsi lacks, replaced by a readable ASCII form. */
const REPLACE: Record<string, string> = {
  '→': '->', '←': '<-', '↔': '<->', '⇒': '=>', '≤': '<=', '≥': '>=', '≠': '!=', '≈': '~',
  '−': '-', '‑': '-', '‐': '-', '‒': '-', '―': '-', ' ': ' ', ' ': ' ', ' ': ' ', ' ': ' ',
  ' ': ' ', '​': '', '﻿': '', '✓': 'v', '✔': 'v', '✗': 'x', '✘': 'x', '●': '*', '○': 'o',
  '☐': '[ ]', '☑': '[x]', 'μ': 'µ', 'Ω': 'Ohm', 'Ω': 'Ohm', 'Ł': 'L', 'ł': 'l', 'ı': 'i',
  'İ': 'I', '′': "'", '″': '"', '­': '-', '∕': '/', '⁄': '/', '∗': '*', '∙': '.',
};

/**
 * Bytes (as a latin1 string, one char per byte) of `text` in WinAnsi. Letters with accents that WinAnsi lacks lose the
 * accent, a few symbols get an ASCII spelling, anything else becomes `?`. Tabs become a space; line breaks stay.
 */
export function toWinAnsi(text: string): string {
  let out = '';
  for (const ch of text.normalize('NFC').replace(/\r\n?/g, '\n')) {
    const cp = ch.codePointAt(0)!;
    if (ch === '\n') out += '\n';
    else if (ch === '\t') out += ' ';
    else if (cp >= 32 && cp <= 126) out += ch;
    else if (cp >= 160 && cp <= 255) out += ch;
    else if (WIN_HIGH[cp] !== undefined) out += String.fromCharCode(WIN_HIGH[cp]!);
    else if (REPLACE[ch] !== undefined) out += REPLACE[ch]!;
    else {
      const base = ch.normalize('NFD').replace(/[̀-ͯ]/g, '');
      if (base !== ch && base.length && /^[\x20-\x7e]+$/.test(base)) out += base;
      else if (cp < 32 || (cp >= 127 && cp < 160)) out += '';
      else out += '?';
    }
  }
  return out;
}

/** A PDF literal string `( ... )` for WinAnsi bytes: backslash, parentheses and bytes outside 32..126 escaped. */
export function pdfString(winAnsi: string): string {
  let s = '(';
  for (let i = 0; i < winAnsi.length; i++) {
    const c = winAnsi.charCodeAt(i);
    if (c === 0x5c) s += '\\\\';
    else if (c === 0x28) s += '\\(';
    else if (c === 0x29) s += '\\)';
    else if (c < 32 || c > 126) s += `\\${c.toString(8).padStart(3, '0')}`;
    else s += String.fromCharCode(c);
  }
  return `${s})`;
}

/** Helvetica advance widths (1/1000 em) for 32..126. */
const HELV = [
  278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
  1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
  333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
];
/** Helvetica-Bold advance widths for 32..126. */
const HELV_B = [
  278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
  975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
  333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
];

/** Width in points of a text (Helvetica; WinAnsi bytes or plain text) at `size` points. Accented letters count as their base. */
export function textWidth(text: string, size: number, bold = false): number {
  const t = HELV_TABLE(bold);
  let w = 0;
  for (const ch of toWinAnsi(text)) {
    const c = ch.charCodeAt(0);
    if (c >= 32 && c <= 126) w += t[c - 32]!;
    else if (c === 10) continue;
    else w += c >= 192 ? t[(c >= 224 ? 'a' : 'A').charCodeAt(0) - 32]! : 556;
  }
  return (w * size) / 1000;
}
function HELV_TABLE(bold: boolean): number[] {
  return bold ? HELV_B : HELV;
}

/** Word wrap `text` to `maxWidth` points; explicit line breaks stay, over-long words are broken. */
export function wrapPdfText(text: string, maxWidth: number, size: number, bold = false): string[] {
  const out: string[] = [];
  for (const para of text.replace(/\r\n?/g, '\n').split('\n')) {
    let line = '';
    for (const word of para.split(/ +/).filter(Boolean)) {
      let w = word;
      while (textWidth(w, size, bold) > maxWidth && w.length > 1) {
        // Break the word at the longest prefix that fits.
        let k = w.length - 1;
        while (k > 1 && textWidth(w.slice(0, k), size, bold) > maxWidth) k--;
        if (line) { out.push(line); line = ''; }
        out.push(w.slice(0, k));
        w = w.slice(k);
      }
      const cand = line ? `${line} ${w}` : w;
      if (!line || textWidth(cand, size, bold) <= maxWidth) line = cand;
      else { out.push(line); line = w; }
    }
    out.push(line);
  }
  while (out.length > 1 && out[out.length - 1] === '') out.pop();
  return out;
}

// ---------------------------------------------------------------- JPEG

/** Width and height of a JPEG (from its first SOF marker), or null when the bytes are not a JPEG. */
export function jpegSize(b: Uint8Array): { width: number; height: number } | null {
  if (b.length < 4 || b[0] !== 0xff || b[1] !== 0xd8) return null;
  let i = 2;
  while (i + 9 < b.length) {
    if (b[i] !== 0xff) { i++; continue; }
    const m = b[i + 1]!;
    if (m === 0xff) { i++; continue; }
    if (m === 0xd8 || m === 0x01 || (m >= 0xd0 && m <= 0xd7)) { i += 2; continue; }
    const len = (b[i + 2]! << 8) | b[i + 3]!;
    if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
      return { height: (b[i + 5]! << 8) | b[i + 6]!, width: (b[i + 7]! << 8) | b[i + 8]! };
    }
    i += 2 + len;
  }
  return null;
}

// ---------------------------------------------------------------- document

export type Rgb = readonly [number, number, number];

const enc = new TextEncoder();
const latin1 = (s: string): Uint8Array => {
  const o = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) o[i] = s.charCodeAt(i) & 0xff;
  return o;
};
const num = (n: number): string => {
  if (!Number.isFinite(n)) return '0';
  const r = Math.round(n * 1000) / 1000;
  return Object.is(r, -0) ? '0' : String(r);
};
const color = (c: Rgb): string => `${num(c[0])} ${num(c[1])} ${num(c[2])}`;

export interface PdfImage {
  readonly id: number;
  readonly name: string;
  readonly width: number;
  readonly height: number;
}

export class PdfPage {
  readonly ops: string[] = [];
  readonly images = new Set<PdfImage>();
  readonly links: Array<{ x: number; y: number; w: number; h: number; url: string }> = [];
  constructor(readonly width: number, readonly height: number) {}

  /** One line of text with its baseline start at (x, y). Line breaks are not interpreted: use wrapPdfText. */
  text(x: number, y: number, text: string, o: { size?: number; bold?: boolean; color?: Rgb } = {}): void {
    const size = o.size ?? 10;
    const line = toWinAnsi(text).replace(/\n/g, ' ');
    this.ops.push(`BT /${o.bold ? 'F2' : 'F1'} ${num(size)} Tf ${color(o.color ?? [0, 0, 0])} rg ${num(x)} ${num(y)} Td ${pdfString(line)} Tj ET`);
  }

  line(x1: number, y1: number, x2: number, y2: number, o: { width?: number; color?: Rgb; dash?: number[] } = {}): void {
    this.ops.push(`q ${num(o.width ?? 0.5)} w ${color(o.color ?? [0, 0, 0])} RG ${o.dash ? `[${o.dash.map(num).join(' ')}] 0 d ` : ''}${num(x1)} ${num(y1)} m ${num(x2)} ${num(y2)} l S Q`);
  }

  rect(x: number, y: number, w: number, h: number, o: { fill?: Rgb; stroke?: Rgb; lineWidth?: number } = {}): void {
    if (!o.fill && !o.stroke) return;
    const paint = o.fill && o.stroke ? 'B' : o.fill ? 'f' : 'S';
    this.ops.push(`q ${o.fill ? `${color(o.fill)} rg ` : ''}${o.stroke ? `${color(o.stroke)} RG ${num(o.lineWidth ?? 0.5)} w ` : ''}${num(x)} ${num(y)} ${num(w)} ${num(h)} re ${paint} Q`);
  }

  /** A circle of radius r (four Bezier arcs). */
  circle(cx: number, cy: number, r: number, o: { fill?: Rgb; stroke?: Rgb; lineWidth?: number } = {}): void {
    if (!o.fill && !o.stroke) return;
    const k = 0.5522847498 * r;
    const paint = o.fill && o.stroke ? 'B' : o.fill ? 'f' : 'S';
    const path = `${num(cx + r)} ${num(cy)} m ${num(cx + r)} ${num(cy + k)} ${num(cx + k)} ${num(cy + r)} ${num(cx)} ${num(cy + r)} c ${num(cx - k)} ${num(cy + r)} ${num(cx - r)} ${num(cy + k)} ${num(cx - r)} ${num(cy)} c ${num(cx - r)} ${num(cy - k)} ${num(cx - k)} ${num(cy - r)} ${num(cx)} ${num(cy - r)} c ${num(cx + k)} ${num(cy - r)} ${num(cx + r)} ${num(cy - k)} ${num(cx + r)} ${num(cy)} c`;
    this.ops.push(`q ${o.fill ? `${color(o.fill)} rg ` : ''}${o.stroke ? `${color(o.stroke)} RG ${num(o.lineWidth ?? 0.5)} w ` : ''}${path} h ${paint} Q`);
  }

  /** Draw an image into the box (x, y, w, h), y being the bottom edge. */
  image(img: PdfImage, x: number, y: number, w: number, h: number): void {
    this.images.add(img);
    this.ops.push(`q ${num(w)} 0 0 ${num(h)} ${num(x)} ${num(y)} cm /${img.name} Do Q`);
  }

  /** A clickable rectangle that opens `url`. */
  link(x: number, y: number, w: number, h: number, url: string): void {
    this.links.push({ x, y, w, h, url });
  }
}

export interface PdfInfo {
  title?: string;
  author?: string;
  subject?: string;
  creator?: string;
  keywords?: string;
  created?: Date;
}

interface Attachment {
  name: string;
  data: Uint8Array;
  mime: string;
  description?: string;
}

function pdfDate(d: Date): string {
  const p = (n: number): string => String(n).padStart(2, '0');
  return `D:${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}Z`;
}

/** An ASCII file name for the attachment (the name tree stores a text string; plain ASCII reads the same everywhere). */
export function safeAttachmentName(name: string): string {
  const n = name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^\w.-]+/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '');
  return n || 'attachment';
}

export class PdfDocument {
  info: PdfInfo = {};
  readonly pages: PdfPage[] = [];
  private readonly imageData: Array<{ img: PdfImage; bytes: Uint8Array }> = [];
  private readonly files: Attachment[] = [];

  addPage(width: number, height: number): PdfPage {
    const p = new PdfPage(width, height);
    this.pages.push(p);
    return p;
  }

  /** Register a JPEG (its width and height are read from the file unless given). */
  addJpeg(bytes: Uint8Array, size?: { width: number; height: number }): PdfImage {
    const s = size ?? jpegSize(bytes);
    if (!s) throw new Error('Not a JPEG image');
    const id = this.imageData.length + 1;
    const img: PdfImage = { id, name: `Im${id}`, width: s.width, height: s.height };
    this.imageData.push({ img, bytes });
    return img;
  }

  attach(name: string, data: Uint8Array, mime = 'application/octet-stream', description?: string): void {
    const a: Attachment = { name: safeAttachmentName(name), data, mime };
    if (description) a.description = description;
    this.files.push(a);
  }

  /** The finished file. Object numbers: 1 catalog, 2 page tree, 3 info, 4 and 5 fonts, then images, pages, attachments. */
  build(): Uint8Array {
    const chunks: Uint8Array[] = [];
    const offsets: number[] = [];
    let pos = 0;
    const push = (b: Uint8Array | string): void => {
      const u = typeof b === 'string' ? latin1(b) : b;
      chunks.push(u);
      pos += u.length;
    };
    const obj = (id: number, body: string | Uint8Array[]): void => {
      offsets[id] = pos;
      push(`${id} 0 obj\n`);
      if (typeof body === 'string') push(body);
      else for (const c of body) push(c);
      push('\nendobj\n');
    };
    const stream = (dict: string, data: Uint8Array): Uint8Array[] => [latin1(`<< ${dict} /Length ${data.length} >>\nstream\n`), data, latin1('\nendstream')];

    // Number the objects up front.
    let next = 6;
    const imgIds = this.imageData.map(() => next++);
    const pageIds: Array<{ page: number; content: number; annots: number[] }> = this.pages.map((p) => ({ page: next++, content: next++, annots: p.links.map(() => next++) }));
    const fileIds = this.files.map(() => ({ stream: next++, spec: next++ }));
    const size = next;

    push('%PDF-1.7\n%\xe2\xe3\xcf\xd3\n');
    const created = this.info.created ?? new Date();
    const names = this.files.length
      ? ` /Names << /EmbeddedFiles << /Names [${this.files.map((f, i) => `${pdfString(f.name)} ${fileIds[i]!.spec} 0 R`).join(' ')}] >> >> /AF [${fileIds.map((f) => `${f.spec} 0 R`).join(' ')}]`
      : '';
    obj(1, `<< /Type /Catalog /Pages 2 0 R${names} >>`);
    obj(2, `<< /Type /Pages /Count ${this.pages.length} /Kids [${pageIds.map((p) => `${p.page} 0 R`).join(' ')}] >>`);
    const info: string[] = [`/Producer ${pdfString('X-ray mode for BIM reference viewer')}`, `/CreationDate (${pdfDate(created)})`];
    const add = (k: string, v: string | undefined): void => { if (v) info.push(`/${k} ${pdfString(toWinAnsi(v))}`); };
    add('Title', this.info.title);
    add('Author', this.info.author);
    add('Subject', this.info.subject);
    add('Creator', this.info.creator);
    add('Keywords', this.info.keywords);
    obj(3, `<< ${info.join(' ')} >>`);
    obj(4, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
    obj(5, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>');

    this.imageData.forEach(({ img, bytes }, i) => {
      obj(imgIds[i]!, stream(`/Type /XObject /Subtype /Image /Width ${img.width} /Height ${img.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode`, bytes));
    });
    this.pages.forEach((p, i) => {
      const ids = pageIds[i]!;
      const xobj = [...p.images].map((im) => `/${im.name} ${imgIds[im.id - 1]} 0 R`).join(' ');
      const annots = ids.annots.length ? ` /Annots [${ids.annots.map((a) => `${a} 0 R`).join(' ')}]` : '';
      obj(ids.page, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${num(p.width)} ${num(p.height)}] /Resources << /Font << /F1 4 0 R /F2 5 0 R >>${xobj ? ` /XObject << ${xobj} >>` : ''} >> /Contents ${ids.content} 0 R${annots} >>`);
      obj(ids.content, stream('', latin1(p.ops.join('\n'))));
      p.links.forEach((l, k) => {
        const url = l.url.replace(/[^\x21-\x7e]/g, (c) => encodeURIComponent(c));
        obj(ids.annots[k]!, `<< /Type /Annot /Subtype /Link /Rect [${num(l.x)} ${num(l.y)} ${num(l.x + l.w)} ${num(l.y + l.h)}] /Border [0 0 0] /A << /S /URI /URI ${pdfString(url)} >> >>`);
      });
    });
    this.files.forEach((f, i) => {
      const ids = fileIds[i]!;
      const mime = f.mime.replace(/[^\w.+\-/]/g, '').replace('/', '#2F');
      obj(ids.stream, stream(`/Type /EmbeddedFile /Subtype /${mime} /Params << /Size ${f.data.length} /CreationDate (${pdfDate(created)}) >>`, f.data));
      const desc = f.description ? ` /Desc ${pdfString(toWinAnsi(f.description))}` : '';
      obj(ids.spec, `<< /Type /Filespec /F ${pdfString(f.name)} /UF ${pdfString(f.name)}${desc} /AFRelationship /Data /EF << /F ${ids.stream} 0 R /UF ${ids.stream} 0 R >> >>`);
    });

    const xrefAt = pos;
    let xref = `xref\n0 ${size}\n0000000000 65535 f \n`;
    for (let id = 1; id < size; id++) xref += `${String(offsets[id]).padStart(10, '0')} 00000 n \n`;
    push(xref);
    const idHex = Array.from(enc.encode(`${created.getTime()}-${pos}-${size}`)).map((b) => b.toString(16).padStart(2, '0')).join('').padEnd(32, '0').slice(0, 32);
    push(`trailer\n<< /Size ${size} /Root 1 0 R /Info 3 0 R /ID [<${idHex}> <${idHex}>] >>\nstartxref\n${xrefAt}\n%%EOF\n`);

    const out = new Uint8Array(pos);
    let o = 0;
    for (const c of chunks) { out.set(c, o); o += c.length; }
    return out;
  }
}

// ---------------------------------------------------------------- reading attachments back

const latin1String = (b: Uint8Array): string => {
  let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return s;
};

/** The text of a PDF literal string starting at `s[i]` (which is `(`), unescaped. */
function readLiteral(s: string, i: number): string {
  let depth = 0;
  let out = '';
  for (let k = i; k < s.length; k++) {
    const c = s[k]!;
    if (c === '\\') {
      const n = s[++k]!;
      if (/[0-7]/.test(n)) {
        let oct = n;
        while (oct.length < 3 && /[0-7]/.test(s[k + 1] ?? '')) oct += s[++k]!;
        out += String.fromCharCode(parseInt(oct, 8) & 0xff);
      } else if (n === 'n') out += '\n';
      else if (n === 'r') out += '\r';
      else if (n === 't') out += '\t';
      else if (n === 'b') out += '\b';
      else if (n === 'f') out += '\f';
      else if (n === '\n') { /* line continuation */ } else out += n;
    } else if (c === '(') {
      if (depth++ > 0) out += c;
    } else if (c === ')') {
      if (--depth === 0) return out;
      out += c;
    } else out += c;
  }
  return out;
}

async function inflate(data: Uint8Array): Promise<Uint8Array> {
  const ds = new DecompressionStream('deflate');
  const w = ds.writable.getWriter();
  void w.write(data as Uint8Array<ArrayBuffer>).catch(() => undefined);
  void w.close().catch(() => undefined);
  return new Uint8Array(await new Response(ds.readable).arrayBuffer());
}

export interface PdfAttachment {
  name: string;
  data: Uint8Array;
  /** The /Subtype of the stream, such as application/json. */
  mime: string;
}

/**
 * The embedded files of a PDF written by PdfDocument (or any file whose embedded-file streams are plain objects with a
 * direct /Length). Streams with /FlateDecode are inflated. A file saved by another tool into object streams is not read.
 */
export async function extractAttachments(bytes: Uint8Array): Promise<PdfAttachment[]> {
  const s = latin1String(bytes);
  const out: PdfAttachment[] = [];
  const re = /\/Type\s*\/EmbeddedFile\b/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    const objStart = s.lastIndexOf(' obj', m.index);
    if (objStart < 0) continue;
    const idMatch = /(\d+)\s+(\d+)\s*$/.exec(s.slice(Math.max(0, objStart - 24), objStart));
    const dictEnd = s.indexOf('stream', m.index);
    if (dictEnd < 0) continue;
    const dict = s.slice(objStart, dictEnd);
    let start = dictEnd + 'stream'.length;
    if (s[start] === '\r') start++;
    if (s[start] === '\n') start++;
    const lenM = /\/Length\s+(\d+)(?!\s+\d+\s+R)/.exec(dict);
    let end = lenM ? start + Number(lenM[1]) : s.indexOf('endstream', start);
    if (!lenM) while (end > start && (s[end - 1] === '\n' || s[end - 1] === '\r')) end--;
    if (end > bytes.length || end < start) continue;
    let data: Uint8Array = bytes.slice(start, end);
    if (/\/Filter\s*(\[\s*)?\/FlateDecode/.test(dict)) {
      try {
        data = await inflate(data);
      } catch {
        continue;
      }
    }
    const sub = /\/Subtype\s*\/([\w#]+)/.exec(dict)?.[1]?.replace(/#2F/gi, '/') ?? 'application/octet-stream';
    // The file name comes from the filespec that points at this stream.
    let name = '';
    if (idMatch) {
      const ref = new RegExp(`/EF\\s*<<[^>]*?/F\\s+${idMatch[1]}\\s+0\\s+R`).exec(s);
      if (ref) {
        const specStart = s.lastIndexOf(' obj', ref.index);
        const f = /\/F\s*\(/.exec(s.slice(specStart, ref.index + 4));
        if (f) name = readLiteral(s, specStart + f.index + f[0].length - 1);
      }
    }
    out.push({ name, data, mime: sub });
  }
  return out;
}
