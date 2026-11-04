// IFC -> glb + sidecar at pack time, in node, with the browser's own reader (src/model/ifcRaw.ts + ifcImport.ts).
// Those files use vite-only imports and non-erasable TypeScript, so node cannot run them directly. Instead a small
// entry (reader-entry.ts) is bundled with vite's build API (ssr, ESM, web-ifc left external) into tools/pack/reader.mjs.
// The bundle is rebuilt when it is missing or older than src/model, src/types.ts or the entry (about 1 s).
import { existsSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
export const webRoot = resolve(here, '..', '..');
export const readerFile = join(here, 'reader.mjs');
const wasmPath = join(webRoot, 'node_modules', 'web-ifc', 'web-ifc-node.wasm');

/** Newest mtime (ms) of a file or of every file below a directory; 0 when missing. */
export function newestMtime(path) {
  if (!existsSync(path)) return 0;
  const st = statSync(path);
  if (!st.isDirectory()) return st.mtimeMs;
  let m = 0;
  for (const f of readdirSync(path, { withFileTypes: true })) m = Math.max(m, newestMtime(join(path, f.name)));
  return m;
}

export function readerIsStale() {
  if (!existsSync(readerFile)) return true;
  const built = statSync(readerFile).mtimeMs;
  const inputs = [
    join(webRoot, 'src', 'model'), join(webRoot, 'src', 'types.ts'),
    join(here, 'reader-entry.ts'), join(here, 'ifcRuntime.node.ts'), join(here, 'convert.mjs'),
  ];
  return inputs.some((p) => newestMtime(p) > built);
}

export async function buildReader() {
  const { build } = await import(pathToFileURL(join(webRoot, 'node_modules', 'vite', 'dist', 'node', 'index.js')).href);
  const stub = join(here, 'ifcRuntime.node.ts');
  await build({
    root: webRoot,
    configFile: false,
    logLevel: 'silent',
    publicDir: false,
    plugins: [{
      name: 'xray-pack-ifc-runtime',
      enforce: 'pre',
      resolveId(source, importer) {
        return importer && /(^|\/)ifcRuntime$/.test(source) ? stub : null;
      },
    }],
    build: {
      ssr: join(here, 'reader-entry.ts'),
      outDir: here,
      emptyOutDir: false,
      minify: false,
      target: 'node22',
      rollupOptions: {
        external: ['web-ifc'],
        output: { format: 'es', entryFileNames: 'reader.mjs', codeSplitting: false },
      },
    },
  });
  if (!existsSync(readerFile)) throw new Error('the reader bundle was not written');
}

/** Load the reader bundle (building it first when needed). */
export async function loadReader() {
  if (readerIsStale()) await buildReader();
  return import(pathToFileURL(readerFile).href + `?v=${Math.floor(statSync(readerFile).mtimeMs)}`);
}

/** inputs: [{ name, bytes }]. Returns { glb, sidecar, report, files, extractMs, buildMs }. */
export async function convertIfcFiles(inputs) {
  if (!existsSync(wasmPath)) throw new Error(`${wasmPath} missing (run npm install in web/)`);
  const reader = await loadReader();
  return reader.convertIfc(inputs, wasmPath);
}
