# P2-PTW-T06b - CLI `tl gastest` (record, ls) and `tl permit export --gas-tests`

Status: staged (written r5; base `p2/ip-r3` after PTW-T02 merges; PTW-S3 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, permits, confidentiality, safety
Depends on: P2-PTW-S3 (`RecordGasTest`, stub `cli_gastest.py`), P2-PTW-T02 (`gas_tests_for`, `gas_export_rows`), P2-PTW-T05 (`cli_permit_read.py`; merged)
Branch: `p2/ptw-t06b-cli-gastest`
Worktree: `/home/user/wt/ptw/t06b` (from `p2/ip-r3`)

## Goal
`tl gastest record PERMIT_KEY ...` files a gas test through the command and prints the computed result; `tl gastest ls PERMIT_KEY` lists a permit's tests newest first; `tl permit export --gas-tests` writes one row per reading for the project (the design section 8 report).

## Rules
- `tl_mod_permits/cli_gastest.py` registers on `gastest_app`; the `--gas-tests` flag is an edit of `cli_permit_read.py` `export` only (the one flag; the other options, output and tests of T05 stay as they are). Patterns: `cli_permit_write.py` (key resolution, `require_command`, `service_errors`) and `cli_permit_read.py`.
- `record PERMIT_KEY --project P --instrument TEXT [--taken-at ISO] [--o2 N] [--lel N] [--h2s N] [--co N] [--note TEXT]`: readings are passed as text (the model takes decimal text); builds `RecordGasTest`, runs the handler `COMMANDS` names. Prints `recorded <GAS key>  <pass|fail>` where the result is read back from `gas_tests_for` for that permit under the actor's viewer (the first row is the newest; if the new test is not it because of `--taken-at`, match the key the command returned); a failing test that suspended the permit also prints the line `permit <KEY> suspended` only when the handler's result says so (read the S3 report for what the result carries; do not re-derive the rule). `--taken-at` must carry an offset (usage error otherwise); no reading at all is the handler's refusal, printed as is.
- `ls PERMIT_KEY --project P [--limit N]`: `gas_tests_for`; columns key, taken, instrument, tester, O2, LEL, H2S, CO, result, note; an empty list prints `no gas tests` (a hidden permit prints the same: no difference from a permit with none, and an unknown key prints `error: no permit <KEY>` as everywhere).
- `permit export --gas-tests` (with `--format csv|jsonl --project P`): rows of `gas_tests_for` for each permit of `permit_list` the viewer can read, in permit key then newest-first order, through `gas_export_rows` (one header for csv; jsonl lines concatenated). The `--state/--type/--area/--holder` filters apply to the permits.
- `permits.view` on `project:P` before any read; `permits.gastest.record` through `require_command`. No record id printed, no SQL, no clock read (the command takes the time).

## Context (read these, nothing else)
- `packages/tl-modules/permits/src/tl_mod_permits/cli_gastest.py`, `cli_permit_write.py`, `cli_permit_read.py`, `iso_commands.py` (`RecordGasTest`), `iso_views.py` (signatures), `module.py` (COMMANDS)
- `docs/reports/P2-PTW/S3.md` (result carried by the handler)
- `packages/tl-cli/tests/test_cli_permit_read.py`, `packages/tl-modules/permits/tests/permit_world.py`

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/cli_gastest.py` (edit), `cli_permit_read.py` (the flag)
- `packages/tl-cli/tests/test_cli_gastest.py` (create), `packages/tl-cli/tests/test_cli_permit_read.py` (one added test for the flag; no other change)
- `docs/reports/P2-PTW/T06b.md` (create)

## Tests to add (`test_cli_gastest.py`)
1. `record` with passing and failing readings prints `pass` / `fail`; the failing test on an Active permit suspends it (stored state) and prints the suspend line; `ls` lists newest first with the readings.
2. A past `--taken-at` orders by time, not by entry; a naive `--taken-at` is a usage error; a reading out of range prints the handler's refusal.
3. Hidden permit: `ls` prints `no gas tests` for the reader who cannot see it (same as a permit with none); the cleared reader sees the rows; `record` on it prints `error: no permit <KEY>`.
4. `export --gas-tests` csv and jsonl equal `gas_export_rows` of the same permits, and hold no row of a hidden permit.
5. A person without the write word is refused; without `permits.view` refused before any read; no record id in any output.

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits packages/tl-cli/tests/test_cli_gastest.py packages/tl-cli/tests/test_cli_permit_read.py
uv run ruff check packages/tl-modules/permits packages/tl-cli/tests/test_cli_gastest.py packages/tl-cli/tests/test_cli_permit_read.py
uv run pyright packages/tl-modules/permits/src/tl_mod_permits/cli_gastest.py packages/tl-modules/permits/src/tl_mod_permits/cli_permit_read.py packages/tl-cli/tests/test_cli_gastest.py
just gate packages/tl-cli/tests/test_cli_gastest.py packages/tl-cli/tests/test_cli_permit_read.py
```
Expected: clean; `gate: PASS`. No `just check`, no whole-repo pyright.

## Escalation triggers
A verb needs a command field the models lack; `get_record` cannot tell the record type from another; a handler needs a change.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-PTW-TNN: ...` (the ticket id) with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
