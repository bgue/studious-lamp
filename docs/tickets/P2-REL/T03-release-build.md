# P2-REL-T03 — `just release-build` and `check_wheels.py`

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: docs, tests, packaging
Depends on: S1, T01 merged on p2/rel
Branch: `p2/rel-t03-release-build`
Wave 2: no

## Goal
`just release-build` builds one wheel per workspace package into `dist/release-<version>/` and writes `SHA256SUMS`;
`dev/release/check_wheels.py dist/release-<version>` prints `OK <n> wheels` or one line per problem and exits 1 (Sec-6).

## Requirements
1. `dev/release/build.sh`: `set -euo pipefail`; version from `tl-cli`'s pyproject; `uv build --all-packages --wheel --out-dir <dir>`
   (confirm the flag exists with `uv build --help`; if not, loop over `packages/*` and `packages/tl-modules/*`); then
   `(cd <dir> && sha256sum *.whl > SHA256SUMS)` (use `shasum -a 256` where `sha256sum` is missing, so macOS works). `dist/` is git-ignored: add the line if missing.
2. `just release-build` wraps it.
3. `check_wheels.py` (stdlib only, `zipfile`): fails on any member whose basename is `tokens.json`, `*.db`, `*.sqlite*`, `*.pem`,
   `*.key`, `.env*`, or whose path contains `/dev/data/` or `.gate/`; fails when `tl-schema` lacks `tl_schema/_data/schema/core/core.yaml`
   or `tl-cli` lacks `tl_cli/main.py`; fails when two wheels disagree on version or the wheel count is not the workspace member count;
   fails on a member (any text file under 200 kB) containing the string `demo` followed within the same line by `password` (case-insensitive).
4. Test `dev/tests/test_check_wheels.py` builds tiny fixture wheels in `tmp_path` (one clean, six broken: one per rule) and pins the messages. No real build in the test.
5. Run the real build once and quote the last 6 lines and the `check_wheels.py` result in the report.

## Context (read these, nothing else)
- `justfile` (recipe style), `.gitignore`, `dev/gate.sh` header (script style), `dev/tests/` (one existing test as the pattern)
- `docs/tickets/P2-REL/S1-installable-wheels.md` requirement 3 (what must be in the wheel)
may explore: none

## Allowed paths
- `dev/release/build.sh`, `dev/release/check_wheels.py` (create), `dev/tests/test_check_wheels.py` (create), `justfile` (one recipe), `.gitignore` (one line)
- `docs/reports/P2-REL/T03.md`

## Acceptance
```
just check
just gate dev/tests/test_check_wheels.py
just release-build && uv run python dev/release/check_wheels.py dist/release-0.1.0
```
Expected: `gate: PASS`; `OK 20 wheels` (the real count is printed; say it).

## Escalation triggers
Stop and report *Blocked* if a package cannot build a wheel (name it), or the scan finds a real secret-like file in a wheel (that is a finding for the orchestrator, not for you to delete).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
