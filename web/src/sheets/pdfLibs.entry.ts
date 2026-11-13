// Entry of the PDF libraries bundle of the single-file build (vite.pdflibs.config.ts): one ES module with pdf.js and pdf-lib in
// it. tools/build-single-file.mjs compresses it (gzip + base64) into the HTML; pdfRuntime.single.ts unpacks it on first use.
export * as pdfjs from 'pdfjs-dist';
export * as pdfLib from 'pdf-lib';
