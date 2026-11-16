# P2-QR-T07 - CLI group `tl qr`

Status: ready (written r4; base `p2/ip-r3`; QR-S2, T01, T02 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, qr
Depends on: P2-QR-S2 (service, resolver), P2-QR-T01 (views), P2-QR-T02 (renderer), all merged
Branch: `p2/qr-t07-cli-qr`
Worktree: `/home/user/wt/qr/t07` (from `p2/ip-r3`)

## Goal
`tl qr` (the group `qr_app` the module hook already names in `tl_mod_qr/cli.py`) has the verbs `label`, `ls`, `revoke`, `rotate`, `resolve`, `export`. The hidden `placeholder` command is removed. Each verb parses options and makes one call into the module (service, views, renderer, resolver); no rule is repeated here.

## Rules
- Pattern to copy: `tl_cli/punch_read.py` (`enter`, `source_key`, viewer from `session_viewer`, `--actor`, `--project`) and `tl_cli/punch_write.py` (one unit of work, `service_errors()`, one output line). Module-package files may import `tl_cli.*` (do not add a dependency).
- Record keys resolve with `get_record` under the viewer (as `punch_write` does); a hidden or unknown key prints the one text `error: no record <key>`.
- `tl qr label KEY --project P [--label TEXT] [--size tag] [--expires YYYY-MM-DD] -o FILE [--force] [--actor A]`: `service.issue(uow, IssueScanCode(scope="project:P", actor=..., target_id=<id>, label_text=..., size=..., expires_on=...))` gated with `require_command` (see `punch_write._execute`), then `labels.label_url(base, code)`, `labels.make_svg(url)`, `labels.render_label(code=..., text=..., size=..., svg=...)`; write FILE (refuse an existing file unless `--force`). Base = `value_of(conn, "api.public_base_url", project=P)` as `service.py:137` reads it. Without `--label` the text is `labels.label_fields(conn, id, viewer).text`. Output: one line with the register id and the file path, never the code or the URL. A `LabelError` or service refusal is `error: <fixed text>`; when `make_svg` is `None` the file still holds `NO_QR_NOTE` and the line says so. Warn on stderr when `TL_WEB` is not set. Size `card` or `sheet` gives the renderer's refusal text.
- `ls KEY --project P`: `views.codes_for_record(conn, id, viewer=...)` as a table (id, label, size, state, issued by, issued at, expires), never a code or hash. `export KEY --project P --format csv|jsonl`: `views.export_rows(rows, fmt)` over the same rows as `ls`; KEY is required.
- `revoke CODE_ID --reason TEXT`, `rotate CODE_ID --reason TEXT`: `service.revoke` / `service.rotate` (gated by `require_command`); `rotate` also writes the new label (`-o FILE`, as `label`). The register id is printed, never the code.
- `resolve --project P [--actor A]`: the code comes from standard input when it is not a terminal, else from `typer.prompt(hide_input=True)`; there is no code option or argument. Prints the card of `resolve.resolve(conn, code, viewer)` as plain lines (banner, key, title, lines, `as of <time>`); a miss prints the one text `no such code` and exits 1 (all misses alike).
- No output contains the 16-character code outside the label file's grouped print (tests grep for it).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/punch_write.py` and `punch_read.py` (patterns), `packages/tl-modules/qr/src/tl_mod_qr/cli.py` (the stub)
- `packages/tl-modules/qr/src/tl_mod_qr/service.py` (lines 55-80, 125-160, 225-285), `labels.py` (names `label_url`, `make_svg`, `render_label`, `label_fields`, `LabelError`), `views.py`, `resolve.py` (signature)
- `packages/tl-cli/tests/test_cli_punch.py` lines 1-110 (the `Cli` helper pattern), `packages/tl-modules/qr/tests/qr_world.py`
may explore: `packages/tl-cli/src/tl_cli/derive_support.py`

## Interfaces (verbatim)
```python
def issue(uow: UnitOfWork, cmd: IssueScanCode) -> IssuedCode: ...   # IssuedCode(code: str, result: CommandResult)
def revoke(uow: UnitOfWork, cmd: RevokeScanCode) -> CommandResult: ...
def rotate(uow: UnitOfWork, cmd: RotateScanCode) -> IssuedCode: ...
def resolve(conn, code: str, viewer: Viewer = LOWEST, now: datetime | None = None) -> ScanCard | None: ...
def codes_for_record(conn, record_id: str, *, viewer: Viewer = LOWEST) -> list[CodeRow]: ...
def export_rows(rows: list[CodeRow], fmt: Literal["csv", "jsonl"]) -> str: ...
```

## Allowed paths
- `packages/tl-modules/qr/src/tl_mod_qr/cli.py` (edit: remove the placeholder, add the verbs; may split into `cli_write.py` and `cli_read.py` created here, registered by import at the bottom of `cli.py`)
- `packages/tl-cli/tests/test_cli_qr.py` (create)
- `docs/reports/P2-QR/T07.md` (create)
`qr_app` and the hook ref `tl_mod_qr.cli:qr_app` do not change; `OLD_GROUPS` already holds `qr`. A pin that breaks only because the placeholder is gone is updated here (rule 12) and listed.

## Tests to add (`test_cli_qr.py`; the ledger comes from `qr_world`, the setting is patched as the S2 tests do)
1. `label` without the base setting: the fixed refusal, no file; with it: the file exists, holds an SVG or the note, no key, id, project code or 16-character code outside the grouped print; the output has no code.
2. `ls` shows the label's row and no code; `export --format csv` and `jsonl` rows equal the `ls` rows; a bad format is a usage error.
3. `rotate`: the old code resolves to the miss text, the new one resolves (code from stdin); `ls` shows both rows. `revoke`: the code answers the miss text.
4. `resolve` from stdin prints the banner and lines of `resolve.resolve`; five misses (unknown, revoked, expired, hidden record, actor without the view word) print the identical text and exit 1.
5. A reader who cannot see the record gets `error: no record <key>` for `label`, `ls`, `export`, identical to an unknown key.
6. The placeholder is gone: `tl qr --help` lists the six verbs only.

## Acceptance
```
uv run ruff format --check packages/tl-modules/qr packages/tl-cli/tests/test_cli_qr.py
uv run ruff check packages/tl-modules/qr packages/tl-cli/tests/test_cli_qr.py
uv run pyright packages/tl-modules/qr packages/tl-cli/tests/test_cli_qr.py
just gate packages/tl-cli/tests/test_cli_qr.py packages/tl-cli/tests/test_module_cli_groups.py packages/tl-modules/qr/tests/test_module_spec.py
```
Expected: ruff and pyright clean on those paths; `gate: PASS`. Do not run `just check` or whole-repo pyright (the box is OOM-killed); the orchestrator runs it at DONE.

## Escalation triggers
A rule needs a change to the service or views; `get_record` cannot resolve the key under the viewer; `require_command` refuses the commands for a legitimate actor in the test world.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-QR-T07: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
