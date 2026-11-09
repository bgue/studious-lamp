# P2-REL-T04 — `just release-starter`: the P200 starter bundle

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: docs, tooling
Depends on: T03 merged on p2/rel; wave 2 merged on the trunk (P2-SEED T01 and T06 sections need core.Constraint)
Branch: `p2/rel-t04-starter`
Wave 2: **yes**

## Goal
`just release-starter` builds `dist/release-<version>/starter-p200-<version>.tar.gz`: a SQLite ledger of the demo project P200
(default seed, all sections including the wave 2 constraint seeds), the overlay schema directory the clients need, and `START.txt`.
The bundle is the "try it" path; it is never a deployment.

## Requirements
1. `dev/release/starter.sh`: runs `just demo-project <tmp>/ledger/p200.db` (the recipe sets `TL_ENV=dev` for the object store), with
   the file store under `<tmp>/ledger/files`; copies the overlay `dev/data/demo-project-schema` as `<tmp>/schema`; writes `START.txt`
   (≤ 25 lines, plain English): install line, then `export TL_ENV=demo TL_DB=./ledger/p200.db TL_SCHEMA_DIR=./schema TL_OBJECT_ROOT=./ledger/files TL_OBJECT_SECRET=<a fixed documented try-it value>`,
   `tl serve`, `tl-tui --remote http://127.0.0.1:8765`, the demo account name and password (take them from
   `dev/seed/demo_project/core.py` and `docs/runbooks/demo-project.md`; do not invent), and three warnings: loopback only, never on a shared
   host, never import into a real ledger. Check first, with `grep -n TL_OBJECT_SECRET` in `tl_core`/`tl_cli`, that `TL_ENV=demo` can use the object
   store; if only `dev` can, `START.txt` uses `TL_ENV=dev` and the report says so as a finding (S2 refuses non-loopback binds in dev anyway).
2. Tar with `--sort=name`-style determinism where the tool allows (GNU `tar`; on macOS accept the difference and say so in the file); add the archive to `SHA256SUMS`.
3. Test `dev/tests/test_starter_script.py`: runs the script with `--sections core` into `tmp_path` (the script takes `--sections` through to the recipe and `--out`),
   asserts the tarball lists `ledger/p200.db`, `schema/`, `START.txt` and nothing else, and that `START.txt` holds the demo name and no other secret.
4. Run it once in full and quote the size and the tar listing's first 10 lines in the report.

## Context (read these, nothing else)
- `docs/runbooks/demo-project.md` (all), `dev/seed/demo_project/__main__.py` (flags), `dev/seed/demo_project/core.py` lines 25–70 (accounts)
- `justfile` lines 50–60, `dev/release/build.sh` (from T03, for the output directory and sums)
may explore: none

## Allowed paths
- `dev/release/starter.sh` (create), `dev/tests/test_starter_script.py` (create), `justfile` (one recipe)
- `docs/reports/P2-REL/T04.md`

## Acceptance
```
just check
just gate dev/tests/test_starter_script.py
just release-starter
```
Expected: `gate: PASS`; the bundle exists and its listing is the three items.

## Escalation triggers
Stop and report *Blocked* if the full build fails on a section (name it; the starter needs all sections), or the demo password is not documented anywhere.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
