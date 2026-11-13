// How the PDF libraries are delivered. Default (dev server and normal build): `pdfjs-dist` (render, read annotations) and
// `pdf-lib` (write) are separate chunks fetched by a dynamic import the first time a PDF is opened or exported, and the pdf.js
// worker is a separate asset. vite.single.config.ts swaps this module for pdfRuntime.single.ts, where both libraries and the
// worker travel inside the HTML as gzip + base64 and are unpacked on first use (like the IFC worker, src/model/ifcRuntime.single.ts).
// Nothing PDF-related is imported statically anywhere else: only `import type` and this module.

import type * as PdfJs from 'pdfjs-dist';
import type * as PdfLib from 'pdf-lib';

export interface PdfLibs {
  pdfjs: typeof PdfJs;
  pdfLib: typeof PdfLib;
  /** A pdf.js port to pass as `worker` to getDocument (one worker serves every document). */
  worker: PdfJs.PDFWorker;
}

let loading: Promise<PdfLibs> | null = null;

/** The libraries, loaded once. Rejects (and tries again next time) when a chunk cannot be fetched. */
export function loadPdfLibs(): Promise<PdfLibs> {
  if (!loading) {
    loading = (async () => {
      const [pdfjs, pdfLib, workerUrl] = await Promise.all([
        import('pdfjs-dist'),
        import('pdf-lib'),
        import('pdfjs-dist/build/pdf.worker.min.mjs?url').then((m) => m.default),
      ]);
      const port = new Worker(new URL(workerUrl, location.href), { type: 'module' });
      return { pdfjs, pdfLib, worker: new pdfjs.PDFWorker({ port: port as never }) };
    })();
    loading.catch(() => { loading = null; });
  }
  return loading;
}

/** True once the libraries were requested (tests and the smoke check that nothing loads before). */
export function pdfLibsRequested(): boolean {
  return loading !== null;
}
