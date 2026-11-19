// Dev server for the smoke scripts: no file watching and no HMR, so edits made by other people while
// a script runs cannot reload the page under it.
import { defineConfig } from 'vite';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  root: resolve(dirname(fileURLToPath(import.meta.url)), '..'),
  // XRAY_VITE_CACHE_DIR gives one smoke its own dependency cache: node_modules is shared between worktrees, and another dev
  // server that re-optimises it makes lazy imports fail with 504 "Outdated Optimize Dep" in a running page.
  ...(process.env.XRAY_VITE_CACHE_DIR ? { cacheDir: process.env.XRAY_VITE_CACHE_DIR } : {}),
  server: { hmr: false, watch: null },
});
