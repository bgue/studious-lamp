# P2-PTW-T05 - CLI `tl permit` reads

Status: ready (written r4; base `p2/ip-r3`; PTW-T01 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, permits, confidentiality
Depends on: P2-PTW-T01 (views `permit_list`, `permit_detail`, `permit_board`, `permit_counts`, `export_rows`), merged
Branch: `p2/ptw-t05-cli-permit-reads`
Worktree: `/home/user/wt/ptw/t05` (from `p2/ip-r3`)

## Goal
`tl permit ls | show | board | export` read the register through `tl_mod_permits.views` under the signed-in viewer. None writes; the CLI queries nothing itself and prints the fields the views return.

## Rules
- Fill `tl_mod_permits/cli_permit_read.py` only, registering on `permit_app` (`from tl_mod_permits.cli import permit_app`); `cli.py` already imports this file. Pattern: `tl_cli/punch_read.py` whole (`enter`, `require_view`, `session_viewer`, table printing). The word is `permits.view` (module `permits`, `names.VIEW`), checked on `project:P` before any read; a refusal is `error: forbidden: ...`.
- Time: `now = tl_core.util.utcnow()` read once per command and passed to the views (`now=`); no other clock.
- `ls --project P [--state S] [--type T] [--area A] [--holder H] [--limit N]`: `permit_list`; columns key, subject, state (as shown, Lapsed in place of Active), type, area, holder, valid until, for (key); last line `n of total`. Limit default 200, at most `views.MAX_LIMIT`.
- `show KEY --project P`: `permit_detail`; property:value lines (`tui-layout` rule: label, value; an empty value is left out); precautions as a comma list; a hidden, unknown or other-project key is `error: no permit <KEY>` (one text).
- `board --project P [--area A]`: `permit_board`; one block per area (no area last, `-`), rows key, type, holder, valid until, state; first line the counts by shown state.
- `export --project P --format csv|jsonl [--state ... --type ... --area ... --holder ...]`: `export_rows(permit_list(...).rows, fmt)` written to stdout as is; another format is a usage error. (`--gas-tests` waits for the gas-test views.)
- Never print a record id (`PermitRow.id` is for commands only).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/punch_read.py` (whole), `packages/tl-cli/src/tl_cli/derive_support.py` (names only)
- `packages/tl-modules/permits/src/tl_mod_permits/views.py` (dataclasses and signatures; do not read the SQL), `cli.py`, `cli_permit_read.py`
- `packages/tl-cli/tests/test_cli_punch.py` lines 1-130 (`Cli` helper, `as_person`), `packages/tl-modules/permits/tests/permit_world.py`
may explore: `.claude/skills/tui-layout/SKILL.md` (property lines only)

## Interfaces (verbatim)
```python
def permit_list(conn, scope, *, now, state=None, permit_type=None, area=None, holder=None, limit=100, offset=0, viewer=LOWEST) -> PermitPage
def permit_detail(conn, scope, number, *, now, viewer=LOWEST) -> PermitDetail | None
def permit_board(conn, scope, area=None, *, now, viewer=LOWEST) -> PermitBoard
def permit_counts(conn, scope, *, now, viewer=LOWEST) -> dict[str, int]
def export_rows(rows: Sequence[PermitRow], fmt: str) -> str     # ValueError for another format
```

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/cli_permit_read.py` (edit)
- `packages/tl-cli/tests/test_cli_permit_read.py` (create)
- `docs/reports/P2-PTW/T05.md` (create)

## Tests to add (`test_cli_permit_read.py`; ledger from `permit_world.World`; readers as `test_cli_punch.py`)
1. `ls` after a request and an issue shows both keys and the total; filters by state, type, area, holder each narrow it; `--limit 1` prints `1 of 2`.
2. A Lapsed permit (move the clock with the world's `at`, or issue with a past `valid_until` as `test_views_lapse.py` does) shows `Lapsed` in `ls`, `show` and `board`, first on the board.
3. `show` prints the detail lines and no id; unknown, hidden and other-project keys print the identical text; the reader who cannot see a restricted-subject permit sees no row, no count in `ls`/`board`, and the same missing text in `show`.
4. `export --format csv` and `jsonl` equal `export_rows` of the same list; a bad format is a usage error.
5. An actor without `permits.view` is refused before any read.

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits packages/tl-cli/tests/test_cli_permit_read.py
uv run ruff check packages/tl-modules/permits packages/tl-cli/tests/test_cli_permit_read.py
uv run pyright packages/tl-modules/permits packages/tl-cli/tests/test_cli_permit_read.py
just gate packages/tl-cli/tests/test_cli_permit_read.py packages/tl-modules/permits/tests/test_views.py
```
Expected: clean; `gate: PASS`. No `just check`, no whole-repo pyright.

## Escalation triggers
A column a screen line needs is not in the view dataclasses; the viewer filter leaks a count; any change to `views.py`.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-PTW-T05: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
