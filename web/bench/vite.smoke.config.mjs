// Dev server for the smoke scripts: no file watching and no HMR, so edits made by other people while
// a script runs cannot reload the page under it.
import { defineConfig } from 'vite';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  root: resolve(dirname(fileURLToPath(import.meta.url)), '..'),
  server: { hmr: false, watch: null },
});
