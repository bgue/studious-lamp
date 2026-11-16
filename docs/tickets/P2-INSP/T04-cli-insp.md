# P2-INSP-T04 - CLI group `tl insp`

Status: ready (written r4; base `p2/ip-r3`; INSP-S2 and T01 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, quality, confidentiality
Depends on: P2-INSP-S2 (commands), P2-INSP-T01 (views), merged
Branch: `p2/insp-t04-cli-insp`
Worktree: `/home/user/wt/insp/t04` (from `p2/ip-r3`)

## Goal
`tl insp plan | schedule | record | verify | reinspect | cancel | ls | show | export`, each thin: one command model of `tl_mod_quality.commands` through `require_command` and the handler `INSP_COMMANDS` names, or one call into `tl_mod_quality.insp_views`. The guards (verifier is not the recorder, published checklist only, hidden subject reads as missing) are the handlers'.

## Rules
- Files: `tl_cli/insp.py` (the group `app`, `register_all()` as `tl_cli/punch.py`), `tl_cli/insp_write.py`, `tl_cli/insp_read.py`. Patterns, copied not reinvented: `tl_cli/punch.py`, `punch_write.py` (`_handler`, `_execute`, key to id with `get_record` under the actor's viewer), `punch_read.py` (`enter`, `require_view`, tables).
- Hook: append `"tl_cli.insp:app"` to `cli_groups` in `packages/tl-modules/quality/src/tl_mod_quality/module.py` (the tuple holds `"tl_cli.punch:app"`; append only: INSP-T05 appends `"tl_cli.checklist:app"` the same way, a merge that keeps both lines is correct). `OLD_GROUPS` in `packages/tl-cli/tests/test_module_cli_groups.py` gets `insp` by union (one name).
- Writes (`--project P --actor A`, keys are the keys a read prints; a hidden or unknown key is `error: no inspection <KEY>`, one text): `plan --subject KEY --title T --point hold|witness|review|surveillance [--for IWPKEY] [--area A] [--planned-on D]` (subject and `--for` resolve with `get_record`; a hidden one is `error: no record <KEY>`); `schedule KEY --checklist CHKKEY --on D --inspector U`; `record KEY [--answer Q=VALUE ...] [--answers-file F] [--note T]` (`--answer q1=yes` repeats; the file is a JSON list of `{"id", "value", ...}` objects read as the command model takes them, at most 256 KiB, else `error: answers file is too large`; both given is a usage error); `verify KEY`; `reinspect KEY [--planned-on D]`; `cancel KEY --reason T`. Each prints `<past-verb> <key>  version <v>`; `record` also prints `result <accept|reject|conditional>` and `punch <n>` from the command result or a follow-up `inspection_detail`.
- Reads: `ls --project P [--state S] [--point P] [--area A] [--inspector U] [--subject KEY] [--for KEY] [--limit N]` (`inspection_list`; columns key, title, state, point, subject, for, inspector, scheduled, result; last line `n of total`); `show KEY` (`inspection_detail`, property:value lines, answers as a table, punch keys; per `tui-layout`); `export --project P --format csv|jsonl` (`export_rows`). The `--answers` export of the design waits for a view that returns answer rows. Word `quality.view` checked first as `punch_read.require_view`.
- Never print a record id; no SQL; no import of `tl_api`, `tl_mcp`.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/punch.py`, `punch_write.py` (lines 1-90, 140-230), `punch_read.py` (whole)
- `packages/tl-modules/quality/src/tl_mod_quality/commands.py` (lines 318-420 only), `module.py` (lines 95-135, 156-180), `insp_views.py` (dataclasses and signatures only)
- `packages/tl-cli/tests/test_cli_punch.py` (lines 1-130), `packages/tl-modules/quality/tests/insp_world.py`

## Interfaces (verbatim)
```python
INSP_COMMANDS: tuple[PunchCommand, ...]   # PunchCommand(model, handler, access); in tl_mod_quality.module
def inspection_list(conn, scope, *, state=None, point=None, area=None, inspector=None, subject_key=None, for_key=None, limit=200, viewer=LOWEST) -> InspectionPage
def inspection_detail(conn, scope, key, *, viewer=LOWEST) -> InspectionDetail | None
def export_rows(rows: Sequence[InspectionRow], fmt: str) -> str
```

## Allowed paths
- `packages/tl-cli/src/tl_cli/insp.py`, `insp_write.py`, `insp_read.py` (create)
- `packages/tl-modules/quality/src/tl_mod_quality/module.py` (the one `cli_groups` line)
- `packages/tl-cli/tests/test_cli_insp.py` (create), `packages/tl-cli/tests/test_module_cli_groups.py` (`insp` in `OLD_GROUPS` only)
- `docs/reports/P2-INSP/T04.md` (create)

## Tests to add (`test_cli_insp.py`; ledger from `InspWorld`, loaded by path)
1. Plan, schedule (published checklist), record (answers by `--answer` and by `--answers-file`), verify by another person: each line prints and the state moves; a failed answer prints `punch <n>`.
2. The recorder cannot verify (handler text); an actor without the word is refused; reinspect and cancel paths.
3. `ls` filters and total; `show` has no id; unknown, hidden-subject and other-project keys print the same text; the reader who cannot see the subject gets no row and no count.
4. `export` csv and jsonl equal `export_rows` of the list; a bad format is a usage error; an oversized answers file is refused.
5. `tl --help` lists `insp`.

## Acceptance
```
uv run ruff format --check packages/tl-cli/src/tl_cli/insp.py packages/tl-cli/src/tl_cli/insp_write.py packages/tl-cli/src/tl_cli/insp_read.py packages/tl-cli/tests/test_cli_insp.py packages/tl-modules/quality/src/tl_mod_quality/module.py
uv run ruff check packages/tl-cli/src/tl_cli/insp.py packages/tl-cli/src/tl_cli/insp_write.py packages/tl-cli/src/tl_cli/insp_read.py packages/tl-cli/tests/test_cli_insp.py packages/tl-modules/quality/src/tl_mod_quality/module.py
uv run pyright packages/tl-cli/src/tl_cli/insp.py packages/tl-cli/src/tl_cli/insp_write.py packages/tl-cli/src/tl_cli/insp_read.py packages/tl-cli/tests/test_cli_insp.py packages/tl-modules/quality/src/tl_mod_quality/module.py
just gate packages/tl-cli/tests/test_cli_insp.py packages/tl-cli/tests/test_module_cli_groups.py
```
Expected: clean on those paths; `gate: PASS` on each line. No `just check` (the orchestrator runs it at DONE), no whole-repo pyright, never `packages/tl-api/tests/test_commands.py`.

## Escalation triggers
A verb needs a command field the models lack; `get_record` cannot tell an inspection from another type; a handler change.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins and regenerated files outside Allowed paths. Commit subjects `P2-INSP-T04: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
