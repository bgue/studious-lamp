// What the decision model reads: the state of every signature's representative, and what a byte cap cuts from it.
//   cd web && node bench/state-report.mjs --model process-plant --reps <out>/reps.json [--caps 2000,1000,500]
// buildState (src/classify/state.ts) builds the state at detail level 0 (everything) and drops detail in steps until it fits the cap; class and name always stay.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const a = process.argv.slice(2);
const args = {};
for (let i = 0; i < a.length; i++) if (a[i].startsWith('--')) args[a[i].slice(2)] = a[++i];
if (!args.model || !args.reps) throw new Error('Usage: --model <sidecar> --reps <reps.json> [--caps 2000,1000,500]');
const CAPS = (args.caps ?? '2000,1000,500').split(',').map(Number);
const server = await createServer({ root, logLevel: 'error', server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
try {
  const C = await server.ssrLoadModule('/src/classify/index.ts');
  const H = await server.ssrLoadModule('/tests/classify-helpers.ts');
  const model = H.sidecarModel(args.model);
  const inputs = new Map(C.buildInputs(model).map((i) => [i.id, i]));
  const reps = JSON.parse(readFileSync(resolve(args.reps), 'utf8')).map((r) => inputs.get(r.gid));
  const bytes = (v) => Buffer.byteLength(JSON.stringify(v));
  const keysOf = (s) => { const out = []; for (const [k, v] of Object.entries(s)) { if (k === 'psets' || k === 'quantities') for (const [set, p] of Object.entries(v)) for (const pk of Object.keys(p)) out.push(`${k}.${set}.${pk}`); else if (k === 'type' && v.psets) { out.push('type'); for (const [set, p] of Object.entries(v.psets)) for (const pk of Object.keys(p)) out.push(`type.psets.${set}.${pk}`); } else out.push(k); } return out; };
  const full = reps.map((r) => C.buildState(r, 10_000_000));
  const sizes = full.map(bytes).sort((x, y) => x - y);
  console.log(`${reps.length} representatives. Full state (level 0): min ${sizes[0]} B, median ${sizes[sizes.length >> 1]} B, max ${sizes[sizes.length - 1]} B, mean ${(sizes.reduce((p, x) => p + x, 0) / sizes.length).toFixed(0)} B`);
  console.log(`Top-level keys of the full states: ${[...new Set(full.flatMap((s) => Object.keys(s)))].join(', ')}`);
  for (const cap of CAPS) {
    let truncated = 0;
    const lost = new Map();
    let example = null;
    reps.forEach((r, i) => {
      const s = C.buildState(r, cap);
      if (bytes(s) === sizes.length && false) return;
      if (JSON.stringify(s) === JSON.stringify(full[i])) return;
      truncated++;
      const have = new Set(keysOf(s));
      for (const k of keysOf(full[i])) if (!have.has(k)) lost.set(k.replace(/\.[^.]*$/, '.*'), (lost.get(k.replace(/\.[^.]*$/, '.*')) ?? 0) + 1);
      if (!example || bytes(full[i]) > bytes(example.full)) example = { full: full[i], cut: s, name: r.name };
    });
    console.log(`\ncap ${cap} B: ${truncated} of ${reps.length} truncated${truncated ? `; lost (key group: signatures): ${[...lost].map(([k, n]) => `${k}: ${n}`).join('; ')}` : ''}`);
    if (example) console.log(`  example ${example.name}\n  full ${bytes(example.full)} B: ${JSON.stringify(example.full)}\n  cut  ${bytes(example.cut)} B: ${JSON.stringify(example.cut)}`);
  }
  const big = reps.map((r, i) => ({ r, n: bytes(full[i]) })).sort((x, y) => y.n - x.n)[0];
  console.log(`\nLargest full state (${big.n} B, ${big.r.name}): ${JSON.stringify(C.buildState(big.r, 10_000_000))}`);
} finally {
  await server.close();
}
