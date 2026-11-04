// Vite config for the single-file viewer. Produces one JS chunk and one CSS file in a scratch directory
// (.single-build); tools/build-single-file.mjs then inlines them into web/dist-single/xray-viewer.html.
//
// The IFC reader (web-ifc) reaches the bundle through src/model/ifcRuntime.ts. This config swaps that one module:
//   default        -> ifcRuntime.single.ts  the module worker is inlined as a Blob worker (`?worker&inline`) and the
//                                           wasm is NOT in the JS: build-single-file.mjs appends it to the HTML as base64
//   XRAY_NO_IFC=1  -> ifcRuntime.none.ts    no web-ifc, no worker, no wasm (`node tools/build-single-file.mjs --no-ifc`)
import { defineConfig } from 'vite';
import type { Plugin } from 'vite';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const noIfc = process.env.XRAY_NO_IFC === '1';
// tools/build-single-file.mjs --template builds into its own scratch directory (so it cannot clash with a plain bundle run)
const outDir = process.env.XRAY_SINGLE_OUT || '.single-build';

/** Redirect every import of src/model/ifcRuntime to the variant for this bundle. */
function ifcRuntimeVariant(): Plugin {
  const target = resolve(here, 'src/model', noIfc ? 'ifcRuntime.none.ts' : 'ifcRuntime.single.ts');
  return {
    name: 'xray-ifc-runtime-variant',
    enforce: 'pre',
    resolveId(source, importer) {
      if (!importer) return null;
      if (/(^|\/)workerRuntime$/.test(source) && importer.includes('/pointcloud/')) return resolve(here, 'src/pointcloud/workerRuntime.single.ts');
      if (!/(^|\/)ifcRuntime$/.test(source)) return null;
      return target;
    },
  };
}

export default defineConfig({
  base: './',
  publicDir: false, // models and config are embedded by the post-processing script, not copied
  plugins: [ifcRuntimeVariant()],
  build: {
    outDir,
    emptyOutDir: true,
    assetsInlineLimit: 100_000_000,
    cssCodeSplit: false,
    modulePreload: false,
    chunkSizeWarningLimit: 100_000,
    rollupOptions: {
      output: { inlineDynamicImports: true },
    },
  },
  // the inlined worker is one self-contained script (no chunks to load from file://)
  worker: {
    format: 'iife',
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
});
