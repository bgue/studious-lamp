// Dev server for the smoke scripts: no file watching and no HMR, so edits made by other people while
// a script runs cannot reload the page under it.
import { defineConfig, searchForWorkspaceRoot } from 'vite';
import { existsSync, realpathSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { releasePlugin, repoRoot } from '../tools/release-number.mjs';

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
// Keep Vite's default allow list and add the repository root (the What's new note imports ../CHANGELOG.md) and the REAL path of
// node_modules: in a git worktree whose web/node_modules is a symlink to another checkout, pdfjs-dist's worker is served as
// /@fs/<other checkout>/node_modules/..., and Vite answers 403 "outside of Vite serving allow list" without this.
const modules = resolve(webRoot, 'node_modules');
const allow = [searchForWorkspaceRoot(webRoot), repoRoot, ...(existsSync(modules) ? [realpathSync(modules)] : [])];

export default defineConfig({
  root: webRoot,
  plugins: [releasePlugin()],
  // XRAY_VITE_CACHE_DIR gives one smoke its own dependency cache: node_modules is shared between worktrees, and another dev
  // server that re-optimises it makes lazy imports fail with 504 "Outdated Optimize Dep" in a running page.
  ...(process.env.XRAY_VITE_CACHE_DIR ? { cacheDir: process.env.XRAY_VITE_CACHE_DIR } : {}),
  server: { hmr: false, watch: null, fs: { allow } },
});
