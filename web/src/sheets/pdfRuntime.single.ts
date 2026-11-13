// The PDF libraries in the single-file build. pdf.js, pdf-lib (one ES module) and the pdf.js worker travel inside the HTML as gzip +
// base64 (written by tools/build-single-file.mjs) and are unpacked with DecompressionStream the first time a PDF is opened or exported;
// nothing is fetched. Same exports as pdfRuntime.ts, which vite.single.config.ts replaces with this module.

import type { PdfLibs } from './pdfRuntime';

declare global {
  interface Window {
    /** gzip + base64 of the ES module with pdf.js (pdfjs) and pdf-lib (pdfLib). */
    __xrayPdfLibsGz?: string;
    /** gzip + base64 of the pdf.js worker (made a classic script by tools/build-single-file.mjs). */
    __xrayPdfWorkerGz?: string;
  }
}

async function inflate(b64: string): Promise<Uint8Array> {
  const bin = atob(b64);
  const packed = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) packed[i] = bin.charCodeAt(i);
  if (typeof DecompressionStream === 'undefined') throw new Error('This browser cannot unpack the embedded PDF reader (no DecompressionStream)');
  const stream = new Blob([packed as BlobPart]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

let loading: Promise<PdfLibs> | null = null;

export function loadPdfLibs(): Promise<PdfLibs> {
  if (!loading) {
    loading = (async () => {
      const libsGz = window.__xrayPdfLibsGz;
      const workerGz = window.__xrayPdfWorkerGz;
      if (!libsGz || !workerGz) throw new Error('The embedded PDF reader is missing from this page');
      const [libs, worker] = await Promise.all([inflate(libsGz), inflate(workerGz)]);
      const libUrl = URL.createObjectURL(new Blob([libs as BlobPart], { type: 'text/javascript' }));
      const workerUrl = URL.createObjectURL(new Blob([worker as BlobPart], { type: 'text/javascript' }));
      try {
        const mod = (await import(/* @vite-ignore */ libUrl)) as { pdfjs: PdfLibs['pdfjs']; pdfLib: PdfLibs['pdfLib'] };
        const port = new Worker(workerUrl); // a classic script: a module worker cannot start from a Blob URL on a file:// page
        return { pdfjs: mod.pdfjs, pdfLib: mod.pdfLib, worker: new mod.pdfjs.PDFWorker({ port: port as never }) };
      } finally {
        // the module and the worker keep running after their script URLs are revoked
        setTimeout(() => { URL.revokeObjectURL(libUrl); URL.revokeObjectURL(workerUrl); }, 10000);
      }
    })();
    loading.catch(() => { loading = null; });
  }
  return loading;
}

export function pdfLibsRequested(): boolean {
  return loading !== null;
}
