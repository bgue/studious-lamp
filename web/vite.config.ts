// Vite config for `npm run dev`, `npm run build`, `npm run preview` and vitest. (The single-file viewer has its own,
// vite.single.config.ts; the smoke scripts use bench/vite.smoke.config.mjs.)
//
// server.fs.allow keeps Vite's defaults (the workspace root) and adds
//   - the repository root: the "What's new" note imports ../CHANGELOG.md (src/whatsnew/);
//   - the real path of node_modules: in a git worktree whose web/node_modules is a symlink to another checkout, files such as
//     pdfjs-dist/build/pdf.worker.min.mjs are served as /@fs/<other checkout>/node_modules/..., which Vite refuses with
//     403 "outside of Vite serving allow list" unless that folder is allowed.
import { defineConfig, searchForWorkspaceRoot } from 'vite';
import { existsSync, realpathSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { releasePlugin, repoRoot } from './tools/release-number.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const modules = resolve(here, 'node_modules');

export function fsAllow(): string[] {
  const allow = [searchForWorkspaceRoot(here), repoRoot];
  if (existsSync(modules)) allow.push(realpathSync(modules));
  return allow;
}

export default defineConfig({
  plugins: [releasePlugin()],
  server: { fs: { allow: fsAllow() } },
});
