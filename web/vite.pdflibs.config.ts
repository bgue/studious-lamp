// Builds the PDF libraries (pdf.js and pdf-lib) as one self-contained ES module for the single-file viewer:
// `node tools/build-single-file.mjs` runs this, gzips the result and embeds it in the HTML, where src/sheets/pdfRuntime.single.ts
// unpacks it with DecompressionStream the first time a PDF is opened or exported. The pdf.js worker is embedded the same way.
import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  publicDir: false,
  logLevel: 'warn',
  build: {
    outDir: process.env.XRAY_PDFLIBS_OUT || '.single-build-pdf',
    emptyOutDir: true,
    minify: true,
    target: 'es2022',
    chunkSizeWarningLimit: 100_000,
    lib: { entry: resolve(import.meta.dirname, 'src/sheets/pdfLibs.entry.ts'), formats: ['es'], fileName: () => 'pdf-libs.mjs' },
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
});
