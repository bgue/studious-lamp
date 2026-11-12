# P2-REL-T01 — One release version, `--version` flags

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: cli, tui, docs
Depends on: S1 merged on p2/rel
Branch: `p2/rel-t01-version`
Wave 2: no

## Goal
Every package carries one version, `0.1.0` (Q-REL3 default), set by a script; `tl --version` and `tl-tui --version` print
`throughline 0.1.0`. The version is read from package metadata (`importlib.metadata.version("tl-cli")`), never typed twice.

## Requirements
1. `dev/release/set_version.sh <X.Y.Z>`: `set -euo pipefail`; rewrites the `version = "..."` line in the `[project]` table of
   every `packages/*/pyproject.toml` and `packages/tl-modules/*/pyproject.toml` (exit 2 on bad usage or a version not matching
   `^[0-9]+\.[0-9]+\.[0-9]+$`; exit 1 if a pyproject has no version line); prints one line per file; run it with `0.1.0` and commit the result.
2. `tl --version` (a root typer option, eager, exits 0) and `tl-tui --version` (argparse `action="version"`). Text:
   `throughline <version>`. In `tl_cli/main.py` and `tl_tui/main.py` only; no other behaviour changes.
3. `uv lock` must still be consistent: run `uv lock --check`; if it needs a refresh, run `uv lock` and commit `uv.lock` (say so).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/main.py` (the root callback near line 220), `packages/tl-tui/src/tl_tui/main.py` (`main`, argparse)
- `packages/tl-cli/pyproject.toml` (shape of the version line)
- `dev/state.sh` (house style for a shell tool and its test under `dev/tests/`)
may explore: none

## Allowed paths
- `dev/release/set_version.sh` (create), `dev/tests/test_set_version.py` (create; fixture tree in `tmp_path`)
- `packages/*/pyproject.toml`, `packages/tl-modules/*/pyproject.toml` (version line only), `uv.lock`
- `packages/tl-cli/src/tl_cli/main.py`, `packages/tl-tui/src/tl_tui/main.py`
- `packages/tl-cli/tests/test_version.py` (create), `packages/tl-tui/tests/test_version.py` (create)
- `docs/reports/P2-REL/T01.md`

## Acceptance
```
just check
just gate dev/tests packages/tl-cli/tests/test_version.py packages/tl-tui/tests/test_version.py
```
Expected: `gate: PASS`; `uv run tl --version` prints `throughline 0.1.0`.

## Tests to add
The script on a fixture tree (rewrites, refuses a bad version, refuses a missing line); the two `--version` outputs.

## Escalation triggers
Stop and report *Blocked* if `uv lock` changes anything but the workspace members' versions, or a pin test fails on `0.0.1`
(consequential pins are updated here and listed in the report, rule 12).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
