import { describe, expect, it } from 'vitest';
import { PdfDocument, extractAttachments, jpegSize, pdfString, safeAttachmentName, textWidth, toWinAnsi, wrapPdfText } from '../src/markup/pdf';

/** A structurally valid JPEG header (SOI, SOF0 with the size, EOI): enough for the writer; not decodable. */
function fakeJpeg(w: number, h: number): Uint8Array {
  return new Uint8Array([0xff, 0xd8, 0xff, 0xc0, 0, 17, 8, h >> 8, h & 255, w >> 8, w & 255, 3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1, 0xff, 0xd9]);
}
const same = (a: Uint8Array, b: Uint8Array): boolean => a.length === b.length && a.every((v, i) => v === b[i]);
const text = (b: Uint8Array): string => Array.from(b, (c) => String.fromCharCode(c)).join('');

describe('pdf text encoding', () => {
  it('escapes backslash and parentheses and octal-escapes high bytes', () => {
    expect(pdfString('a(b)c\\d')).toBe('(a\\(b\\)c\\\\d)');
    expect(pdfString('\xe9\n')).toBe('(\\351\\012)');
  });
  it('maps typographic characters to WinAnsi and replaces what it lacks', () => {
    expect(toWinAnsi('“q” – €').split('').map((c) => c.charCodeAt(0))).toEqual([0x93, 113, 0x94, 32, 0x96, 32, 0x80]);
    expect(toWinAnsi('a→b ≤ é ć')).toBe('a->b <= é c');
    expect(toWinAnsi('😀')).toBe('?');
    expect(toWinAnsi('a\tb\r\nc')).toBe('a b\nc');
  });
  it('measures Helvetica text and wraps to a width', () => {
    expect(textWidth('Hello', 10)).toBeCloseTo((722 + 556 + 222 + 222 + 556) / 100, 5);
    expect(textWidth('Hello', 10, true)).toBeGreaterThan(textWidth('Hello', 10));
    const lines = wrapPdfText('one two three four five six seven', 60, 10);
    expect(lines.length).toBeGreaterThan(2);
    for (const l of lines) expect(textWidth(l, 10)).toBeLessThanOrEqual(60.01);
    expect(wrapPdfText('a\n\nb', 100, 10)).toEqual(['a', '', 'b']);
    // a word wider than the line is broken
    for (const l of wrapPdfText('W'.repeat(40), 50, 10)) expect(textWidth(l, 10)).toBeLessThanOrEqual(50.01);
  });
  it('makes ASCII attachment names', () => {
    expect(safeAttachmentName('Küche / Plan #3.json')).toBe('Kuche_Plan_3.json');
    expect(safeAttachmentName('')).toBe('attachment');
  });
});

describe('jpegSize', () => {
  it('reads the size from SOF and refuses other bytes', () => {
    expect(jpegSize(fakeJpeg(640, 480))).toEqual({ width: 640, height: 480 });
    expect(jpegSize(new Uint8Array([1, 2, 3, 4]))).toBeNull();
  });
});

describe('PdfDocument', () => {
  function sample(): { bytes: Uint8Array; payload: Uint8Array } {
    const doc = new PdfDocument();
    doc.info = { title: 'Set "A" (1)', author: 'Zoë', created: new Date(Date.UTC(2026, 0, 2, 3, 4, 5)) };
    const img = doc.addJpeg(fakeJpeg(200, 100));
    const p = doc.addPage(842, 595);
    p.text(40, 500, 'Hello (world) \\ ok', { size: 12, bold: true, color: [1, 0, 0] });
    p.line(10, 10, 100, 10, { dash: [2, 2] });
    p.rect(20, 20, 50, 30, { fill: [0.9, 0.9, 0.2], stroke: [0, 0, 0] });
    p.image(img, 40, 300, 400, 200);
    p.link(40, 40, 100, 12, 'https://example.org/?a=1&b=2#view=abc');
    const p2 = doc.addPage(595, 842);
    p2.text(10, 10, 'second');
    // a payload with every byte value and the word endstream inside
    const payload = new Uint8Array(600);
    for (let i = 0; i < payload.length; i++) payload[i] = i % 256;
    payload.set(new TextEncoder().encode('\nendstream\nendobj\n'), 100);
    doc.attach('xray-markup-set.json', payload, 'application/json', 'Markup set');
    return { bytes: doc.build(), payload };
  }

  it('writes a header, xref offsets that point at their objects, and a trailer', () => {
    const { bytes } = sample();
    const s = text(bytes);
    expect(s.startsWith('%PDF-1.7\n')).toBe(true);
    expect(s.endsWith('%%EOF\n')).toBe(true);
    const startxref = Number(/startxref\n(\d+)\n%%EOF/.exec(s)![1]);
    expect(s.slice(startxref, startxref + 5)).toBe('xref\n');
    const head = /xref\n0 (\d+)\n/.exec(s.slice(startxref))!;
    const n = Number(head[1]);
    const table = s.slice(startxref + head[0].length).split('\n').slice(0, n);
    expect(table[0]).toBe('0000000000 65535 f ');
    for (let id = 1; id < n; id++) {
      const entry = table[id]!;
      expect(entry).toMatch(/^\d{10} 00000 n $/);
      const off = Number(entry.slice(0, 10));
      expect(s.slice(off, off + `${id} 0 obj`.length), `object ${id}`).toBe(`${id} 0 obj`);
    }
    expect(s).toContain(`/Size ${n}`);
    expect(s).toContain('/Root 1 0 R');
  });

  it('lists the pages, fonts, image and link as objects of the expected kinds', () => {
    const { bytes } = sample();
    const s = text(bytes);
    expect(s).toContain('/Type /Pages /Count 2');
    expect(s).toContain('/BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding');
    expect(s).toContain('/Subtype /Image /Width 200 /Height 100 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode');
    expect(s).toContain('/MediaBox [0 0 842 595]');
    expect(s).toContain('/URI (https://example.org/?a=1&b=2#view=abc)');
    expect(s).toContain('/Title (Set "A" \\(1\\))');
    expect(s).toContain('/Author (Zo\\353)');
    expect(s).toContain('(Hello \\(world\\) \\\\ ok) Tj');
    expect(s).toContain('/CreationDate (D:20260102030405Z)');
  });

  it('stream lengths match the bytes between stream and endstream', () => {
    const { bytes } = sample();
    const s = text(bytes);
    const re = /\/Length (\d+) >>\nstream\n/g;
    let m: RegExpExecArray | null;
    let count = 0;
    while ((m = re.exec(s))) {
      const start = m.index + m[0].length;
      const len = Number(m[1]);
      expect(s.slice(start + len, start + len + 10), `stream at ${start}`).toBe('\nendstream');
      count++;
    }
    expect(count).toBe(1 /* image */ + 2 /* contents */ + 1 /* embedded */);
  });

  it('round-trips an embedded file byte for byte, name and type included', async () => {
    const { bytes, payload } = sample();
    const s = text(bytes);
    expect(s).toContain('/Names << /EmbeddedFiles << /Names [(xray-markup-set.json) ');
    expect(s).toContain('/AFRelationship /Data');
    const files = await extractAttachments(bytes);
    expect(files.length).toBe(1);
    expect(files[0]!.name).toBe('xray-markup-set.json');
    expect(files[0]!.mime).toBe('application/json');
    expect(files[0]!.data.length).toBe(payload.length);
    expect(same(files[0]!.data, payload)).toBe(true);
  });

  it('reads a FlateDecode embedded stream', async () => {
    const data = new TextEncoder().encode('{"schema":"x"}'.repeat(20));
    const cs = new CompressionStream('deflate');
    const w = cs.writable.getWriter();
    void w.write(data);
    void w.close();
    const z = new Uint8Array(await new Response(cs.readable).arrayBuffer());
    const head = new TextEncoder().encode('%PDF-1.7\n7 0 obj\n<< /Type /EmbeddedFile /Subtype /application#2Fjson /Filter /FlateDecode /Length ' + z.length + ' >>\nstream\n');
    const tail = new TextEncoder().encode('\nendstream\nendobj\n');
    const file = new Uint8Array(head.length + z.length + tail.length);
    file.set(head, 0); file.set(z, head.length); file.set(tail, head.length + z.length);
    const got = await extractAttachments(file);
    expect(got.length).toBe(1);
    expect(same(got[0]!.data, data)).toBe(true);
  });

  it('finds no attachments in a file without one', async () => {
    const doc = new PdfDocument();
    doc.addPage(100, 100).text(1, 1, 'x');
    expect(await extractAttachments(doc.build())).toEqual([]);
  });

  it('refuses a non-JPEG image', () => {
    expect(() => new PdfDocument().addJpeg(new Uint8Array([1, 2, 3]))).toThrow();
  });
});
