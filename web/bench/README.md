# bench: smoke tests and benchmarks

Each `smoke-*.mjs` starts its own vite server (`vite.smoke.config.mjs`: no file watching, no HMR), opens the viewer in headless
Chromium with a software renderer, drives it and prints `PASS ...` and `FAIL ...` lines. They read the port from `SMOKE_PORT`
(`bench.mjs` and the bench scripts from `BENCH_PORT`) and the vite cache directory from `XRAY_VITE_CACHE_DIR`.
Run one alone: `SMOKE_PORT=5701 node bench/smoke-keys.mjs`. Some smokes rewrite tracked pictures in this folder; the runner restores them.

## The runner: `run-smokes.mjs`

```sh
npm run smoke:fast         # node bench/run-smokes.mjs --tier fast
npm run smoke:full         # node bench/run-smokes.mjs --tier full
node bench/run-smokes.mjs --tier fast --list
```

Runs the smokes serially. For each one:

- the port (`--port`, default 5790) is given as `SMOKE_PORT` and `BENCH_PORT`, and the cache directory (`--cache`, default
  `<tmp>/xray-smoke-vite-cache`) as `XRAY_VITE_CACHE_DIR`; one cache for all, so dependencies are optimised once;
- a time limit (four times the expected duration, at least 5 minutes, 15 minutes when not measured) ends the smoke and the vite server
  it started (the whole process group) with rc 124;
- one summary line is printed and appended to the summary file (`--summary`, default `<tmp>/xray-smoke-summary.txt`):
  `smoke-keys rc=0 pass=68 fail=0 47s`; the full output of each smoke goes to `--logs` (default `<tmp>/xray-smoke-logs/<name>.log`);
- whatever still listens on the port is killed by process id (`lsof`), so a crashed smoke leaves nothing behind.

At the end, `git checkout -- bench/*.png` restores the tracked pictures the smokes rewrote (`--keep-png` keeps them) and a `TOTAL` line is
printed. The exit code is 0 only when every smoke exited 0 with no `FAIL`. `--only a,b` runs just those (`keys`, `smoke-keys` and
`smoke-keys.mjs` are the same); `--list` prints the plan and stops.

### Tiers

| Tier | Smokes | Expected time |
| --- | --- | --- |
| `fast` | `smoke-right-sidebar` (start-up, tabs), `smoke-keys` (keys, navigation), `smoke-tree-keys` (model tree), `smoke-pointer-undo` (pointer modes, undo), `smoke-issue-clash` (issues), `smoke-4d-play` (4D film), `smoke-animation-script` (scripts), `help-smoke` (help texts) | about 12 minutes |
| `full` | every `smoke-*.mjs` and `help-smoke.mjs` | about 2 to 3 hours |

The fast tier leaves out the slow smokes of views (`smoke-views`, about 8 minutes), issues (`smoke-issues`, about 5), sheets, markup, view modes
(about 20) and presets. The durations come from serial runs on the software renderer and grow with a loaded machine.

## Git worktrees

A worktree whose `web/node_modules` is a symlink to another checkout serves `pdfjs-dist` as `/@fs/<other checkout>/node_modules/...`, which vite
refuses (403 "outside of Vite serving allow list"), so PDF smokes hung when opening the PDF. `server.fs.allow` in `web/vite.config.ts` (dev server)
and `bench/vite.smoke.config.mjs` (smokes) now holds the defaults, the repository root and the real path of `node_modules`.
Give each worktree its own `--cache` and `--port` when two run at once.

## Benchmarks

`bench.mjs`, `bench-*.mjs` and `RESULTS-*.md`: see the main README ("Benchmark and smoke scripts").
