// Runs the browser smoke scripts one after the other: one port, one vite cache directory, a time limit for each, one summary line each.
//
//   node bench/run-smokes.mjs [--tier fast|full|tours] [--port 5790] [--cache DIR] [--summary FILE] [--logs DIR]
//                             [--only a,b] [--keep-png] [--list]
//   npm run smoke:fast       about 12 minutes: 8 smokes that cover start-up, keys, the tree, undo, issues, 4D, scripts and help
//   npm run smoke:full       every bench/smoke-*.mjs plus help-smoke.mjs plus the tours (about 2 to 3 hours on a software renderer)
//   npm run tours            the tours only: bench/tours/tour-*.mjs, one per manual chapter (see bench/tours/README.md)
//
//   --tier     fast (default), full, or tours (the tour-*.mjs in bench/tours/)
//   --port     the port every smoke gets as SMOKE_PORT and BENCH_PORT (default 5790); the runner needs it to itself
//   --cache    vite dependency cache, XRAY_VITE_CACHE_DIR for every smoke (default <tmp>/xray-smoke-vite-cache). One directory for all
//              of them: the first smoke optimises the dependencies, the others reuse them. A git worktree should not share it with
//              another checkout that runs a dev server.
//   --summary  summary file (default <tmp>/xray-smoke-summary.txt), rewritten at the start; the same lines go to stdout
//   --logs     directory for the full output of each smoke (default <tmp>/xray-smoke-logs)
//   --only     run just these smokes (names with or without "smoke-" and ".mjs"), in the order given; with --tier it narrows the tier
//   --keep-png keep the rewritten tracked pictures in bench/ (by default `git checkout -- bench/*.png` runs at the end)
//   --list     print what would run, with the time limit and the expected seconds, and stop
//
// Summary line:  <name> rc=<exit code> pass=<n> fail=<n> <seconds>s   (rc=124: the time limit hit; the smoke is killed by process group)
// pass and fail count the lines that start with PASS and FAIL (a tour also prints KNOWN lines for suspected product bugs; they are shown as known=n and are not failures), or the "N/M checks passed" line of the smokes that print one.
// After each smoke the runner kills whatever still listens on the port, by process id (lsof), so a crashed smoke does not leave
// its vite server behind. Exit code 0 only when every smoke exited 0 with no failed check.
import { spawn, spawnSync } from 'node:child_process';
import { appendFileSync, existsSync, mkdirSync, readdirSync, writeFileSync, createWriteStream } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');

/** Expected seconds of each smoke on the software renderer (from the serial runs of 2026-11-21; "est" were not measured). */
const EXPECT = {
  'smoke-right-sidebar': 40,
  'smoke-keys': 150,
  'smoke-tree-keys': 60, // est
  'smoke-pointer-undo': 82,
  'smoke-issue-clash': 110,
  'smoke-4d-play': 142,
  'smoke-animation-script': 100,
  'help-smoke': 148,
  'smoke-views': 460,
  'smoke-viewmodes': 1300,
  'smoke-oit': 950,
  'smoke-topbar': 600,
  'smoke-presets': 460,
  'smoke-search': 450,
  'smoke-qa-wave7': 355,
  'smoke-markup': 460,
  'smoke-issues': 270,
  'smoke-imaging': 430,
  'smoke-classify-local': 330,
  'smoke-gizmo': 190,
};

/** The fast tier, in this order. */
const FAST = ['smoke-right-sidebar', 'smoke-keys', 'smoke-tree-keys', 'smoke-pointer-undo', 'smoke-issue-clash', 'smoke-4d-play', 'smoke-animation-script', 'help-smoke'];

/** Time limit in seconds: four times the expected duration, at least 5 minutes, 15 minutes for a smoke with no measurement. */
function limitOf(name) {
  const e = EXPECT[name];
  return e ? Math.max(300, e * 4) : name.startsWith('tour-') ? 3600 : 900;
}

const args = process.argv.slice(2);
function opt(name, dflt) {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] !== undefined ? args[i + 1] : dflt;
}
const flag = (name) => args.includes(`--${name}`);

const tier = opt('tier', 'fast');
const port = Number(opt('port', '5790'));
const cache = resolve(opt('cache', join(tmpdir(), 'xray-smoke-vite-cache')));
const summaryFile = resolve(opt('summary', join(tmpdir(), 'xray-smoke-summary.txt')));
const logDir = resolve(opt('logs', join(tmpdir(), 'xray-smoke-logs')));

const tourDir = join(here, 'tours');
function allTours() {
  return existsSync(tourDir) ? readdirSync(tourDir).filter((f) => /^tour-.*\.mjs$/.test(f)).map((f) => f.replace(/\.mjs$/, '')).sort() : [];
}
function allSmokes() {
  const names = readdirSync(here).filter((f) => /^smoke-.*\.mjs$/.test(f)).map((f) => f.replace(/\.mjs$/, '')).sort();
  return [...names, 'help-smoke', ...allTours()];
}
/** The script of a smoke or tour. */
const scriptOf = (name) => (name.startsWith('tour-') ? join(tourDir, `${name}.mjs`) : join(here, `${name}.mjs`));

const norm = (n) => {
  const b = n.replace(/\.mjs$/, '');
  return b === 'help' || b === 'help-smoke' ? 'help-smoke' : b.startsWith('smoke-') || b.startsWith('tour-') ? b : `smoke-${b}`;
};

function plan() {
  if (tier !== 'fast' && tier !== 'full' && tier !== 'tours') throw new Error(`--tier must be fast, full or tours, not "${tier}"`);
  const base = tier === 'fast' ? FAST : tier === 'tours' ? allTours() : allSmokes();
  const only = opt('only', '');
  if (!only) return base;
  const wanted = only.split(',').map((s) => s.trim()).filter(Boolean).map(norm);
  const known = new Set(allSmokes());
  for (const w of wanted) if (!known.has(w)) throw new Error(`no such smoke: ${w}`);
  return wanted;
}

let names;
try {
  names = plan();
} catch (e) {
  console.error(e.message);
  process.exit(2);
}

if (flag('list')) {
  let total = 0;
  for (const n of names) {
    const e = EXPECT[n];
    total += e ?? 0;
    console.log(`${n.padEnd(26)} limit ${String(limitOf(n)).padStart(5)}s  expected ${e ? `${e}s` : 'not measured'}`);
  }
  console.log(`${names.length} smokes, tier ${tier}, port ${port}, about ${Math.round(total / 60)} min (measured ones only), cache ${cache}`);
  console.log(`summary ${summaryFile}, logs ${logDir}`);
  process.exit(0);
}

mkdirSync(cache, { recursive: true });
mkdirSync(logDir, { recursive: true });
writeFileSync(summaryFile, '');
const say = (line) => {
  console.log(line);
  appendFileSync(summaryFile, `${line}\n`);
};

/** Kill what listens on the port, by process id. */
function freePort() {
  const r = spawnSync('lsof', ['-ti', `tcp:${port}`, '-sTCP:LISTEN'], { encoding: 'utf8' });
  for (const s of (r.stdout ?? '').split(/\s+/).filter(Boolean)) {
    try { process.kill(Number(s), 'SIGKILL'); } catch { /* already gone */ }
  }
}

function count(text) {
  const m = [...text.matchAll(/(\d+)\s*\/\s*(\d+)\s+checks passed/g)].pop();
  if (m) return { pass: Number(m[1]), fail: Number(m[2]) - Number(m[1]) };
  let pass = 0, fail = 0, known = 0;
  for (const line of text.split('\n')) {
    if (/^\s*PASS\b/.test(line)) pass++;
    else if (/^\s*FAIL\b/.test(line)) fail++;
    else if (/^\s*KNOWN\b/.test(line)) known++;
  }
  return { pass, fail, known };
}

function runOne(name) {
  return new Promise((done) => {
    const t0 = Date.now();
    const log = createWriteStream(join(logDir, `${name}.log`));
    let out = '';
    const child = spawn(process.execPath, [scriptOf(name)], {
      cwd: root,
      detached: true, // its own process group: a time-out kills the smoke and the vite server it started
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, SMOKE_PORT: String(port), BENCH_PORT: String(port), XRAY_VITE_CACHE_DIR: cache },
    });
    const take = (d) => { out += d; log.write(d); };
    child.stdout.on('data', take);
    child.stderr.on('data', take);
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      try { process.kill(-child.pid, 'SIGKILL'); } catch { /* gone */ }
    }, limitOf(name) * 1000);
    const finish = (rc) => {
      clearTimeout(timer);
      log.end();
      try { process.kill(-child.pid, 'SIGKILL'); } catch { /* group already gone */ }
      freePort();
      const { pass, fail, known } = count(out);
      done({ name, rc: timedOut ? 124 : rc ?? 1, pass, fail, known, seconds: Math.round((Date.now() - t0) / 1000) });
    };
    child.on('error', () => finish(1));
    child.on('close', (code) => finish(code));
  });
}

function restorePngs() {
  if (flag('keep-png')) return;
  // tracked pictures only; a picture that no smoke rewrote is left as it is
  spawnSync('git', ['checkout', '--', 'bench/*.png'], { cwd: root, stdio: 'ignore' });
}

let interrupted = false;
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { interrupted = true; freePort(); restorePngs(); process.exit(130); });

freePort();
const results = [];
for (const n of names) {
  if (interrupted) break;
  const r = await runOne(n);
  results.push(r);
  say(`${r.name} rc=${r.rc} pass=${r.pass} fail=${r.fail}${r.known ? ` known=${r.known}` : ''} ${r.seconds}s`);
}
restorePngs();
const bad = results.filter((r) => r.rc !== 0 || r.fail > 0);
const secs = results.reduce((a, r) => a + r.seconds, 0);
say(`TOTAL ${results.length} smokes, ${results.length - bad.length} ok, ${bad.length} not ok${bad.length ? ` (${bad.map((r) => r.name).join(', ')})` : ''}, ${Math.floor(secs / 60)}m${String(secs % 60).padStart(2, '0')}s`);
process.exit(bad.length ? 1 : 0);
