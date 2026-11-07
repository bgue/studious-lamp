# P2-SEED-T04 — Runbook and README line for the demo project

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: T03 (merged on p2/seed; the runbook names `just tour wave1`)
Branch: `p2/seed-t04-runbook`   (from p2/seed, after T03 merged)

## Goal
`docs/runbooks/demo-project.md` tells a person how to build and use P200, and the root `README.md` and
`docs/runbooks/README.md` list it. Plain English for the owner; follow the `throughline-docs` runbook shape.

## Context (read these, nothing else)
- `docs/tickets/P2-SEED/README.md` (the project, volumes)
- `dev/seed/demo_project/__main__.py` (flags, output) and `dev/seed/demo_project/core.py` lines 25–70 (people, password)
- `dev/seed/demo_project/anchors.py` (fixed names)
- `docs/runbooks/awp.md` first 30 lines (runbook shape) and `docs/runbooks/README.md`
- `justfile` lines 50–60 (the recipe)

## Allowed paths
- `docs/runbooks/demo-project.md` (create), `docs/runbooks/README.md` (one index row), `README.md` (one line)
- `docs/reports/P2-SEED/T04.md`

## Content (sections, in order)
What it is; Build it (`just demo-project [db]`, SQLite and `postgresql://`, `--seed`, `--sections`, a fresh ledger each time,
it refuses a used one); Read it with the clients (`TL_SCHEMA_DIR=dev/data/demo-project-schema`, `TL_DB`, serve and TUI
commands as the other runbooks give them); The people (table of username, name, job; the shared demo password
`p200-demo-pass`, demo data only); Volumes (the README table, short); The fixed names (anchors); Determinism (same seed,
same rows; job keys are excluded from the key hash); The tour (`just tour wave1`); Extending (add a section module,
register in `SECTIONS`, a section is skipped when its record types are missing; quality is next).
Every command in the runbook must be one you ran or that appears verbatim in the repo; mark none as untested.

## Acceptance
- `just demo-project /tmp/<x>.db` exits 0; paste its summary line in the report
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- No gate paths (docs only)

## Escalation triggers
- A flag or name in the runbook differs from the code: the code wins; report it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
