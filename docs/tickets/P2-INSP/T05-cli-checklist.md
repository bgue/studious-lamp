# P2-INSP-T05 - CLI group `tl checklist`

Status: ready (written r4; base `p2/ip-r3`; INSP-S2 and T01 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, quality
Depends on: P2-INSP-S2 (commands), P2-INSP-T01 (views), merged
Branch: `p2/insp-t05-cli-checklist`
Worktree: `/home/user/wt/insp/t05` (from `p2/ip-r3`)

## Goal
`tl checklist create | edit | publish | revise | retire | ls | show`, thin over the checklist commands (`CreateChecklist`, `EditChecklist`, `PublishChecklist`, `ReviseChecklist`, `RetireChecklist`) and `insp_views.checklist_list`/`checklist_detail`. The question rules (`insp_rules.validate_questions`) run in the handlers; the CLI only reads the question file.

## Rules
- Files: `tl_cli/checklist.py` (the group `app`, `register_all()`), `tl_cli/checklist_write.py`, `tl_cli/checklist_read.py`; patterns as INSP-T04 (`punch.py`, `punch_write.py`, `punch_read.py`).
- Hook: append `"tl_cli.checklist:app"` to `cli_groups` in `tl_mod_quality/module.py` (append only; INSP-T04 appends `"tl_cli.insp:app"`; a merge keeping both lines is correct). `OLD_GROUPS` gets `checklist` by union.
- Writes (`--project P --actor A`; keys as a read prints; unknown key `error: no checklist <KEY>`): `create --title T [--discipline D] [--questions-file F]` (JSON list of question objects as the command takes them, at most 256 KiB); `edit KEY [--title T] [--discipline D] [--questions-file F]`; `publish KEY`; `revise KEY` (prints the new key); `retire KEY`. Each prints `<past-verb> <key>  version <v>`.
- Reads: `ls --project P [--state Draft|Published|Retired] [--discipline D] [--limit N]` (`checklist_list`; key, title, discipline, version, state, questions; `n of total`); `show KEY` (`checklist_detail`: property lines, then a table of questions: id, text, kind, required, fails when). A checklist is company reference data at the lowest class, but reads still pass the viewer. Word `quality.view` first.
- Never print a record id; no SQL.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/punch.py`, `punch_write.py` (1-90, 140-230), `punch_read.py`
- `packages/tl-modules/quality/src/tl_mod_quality/commands.py` (lines 252-317), `module.py` (95-135, 156-180), `insp_views.py` (ChecklistRow, ChecklistDetail, `checklist_list`, `checklist_detail` signatures)
- `packages/tl-cli/tests/test_cli_punch.py` (1-130), `packages/tl-modules/quality/tests/insp_world.py` (`QUESTIONS`, `checklist`), `schema/fixtures/quality/checklists/` (ls; one file as a question-file sample)

## Allowed paths
- `packages/tl-cli/src/tl_cli/checklist.py`, `checklist_write.py`, `checklist_read.py` (create)
- `packages/tl-modules/quality/src/tl_mod_quality/module.py` (the one `cli_groups` line)
- `packages/tl-cli/tests/test_cli_checklist.py` (create), `packages/tl-cli/tests/test_module_cli_groups.py` (`checklist` in `OLD_GROUPS` only)
- `docs/reports/P2-INSP/T05.md` (create)

## Tests to add (`test_cli_checklist.py`; ledger from `InspWorld`)
1. create (with a questions file), edit, publish, revise (new key, old one Published until the new publishes as the handler says), retire: lines print, states move.
2. An invalid question file is the handler's refusal text; an oversized file is `error: questions file is too large`; a Published checklist refuses `edit` (handler text).
3. `ls` filters and total; `show` prints the question table and no id; an unknown key prints `error: no checklist <KEY>`.
4. An actor without `quality.checklist.*` word is refused on the write verbs; without `quality.view` on the reads.
5. `tl --help` lists `checklist`.

## Acceptance
```
uv run ruff format --check packages/tl-cli/src/tl_cli/checklist.py packages/tl-cli/src/tl_cli/checklist_write.py packages/tl-cli/src/tl_cli/checklist_read.py packages/tl-cli/tests/test_cli_checklist.py packages/tl-modules/quality/src/tl_mod_quality/module.py
uv run ruff check packages/tl-cli/src/tl_cli/checklist.py packages/tl-cli/src/tl_cli/checklist_write.py packages/tl-cli/src/tl_cli/checklist_read.py packages/tl-cli/tests/test_cli_checklist.py packages/tl-modules/quality/src/tl_mod_quality/module.py
uv run pyright packages/tl-cli/src/tl_cli/checklist.py packages/tl-cli/src/tl_cli/checklist_write.py packages/tl-cli/src/tl_cli/checklist_read.py packages/tl-cli/tests/test_cli_checklist.py packages/tl-modules/quality/src/tl_mod_quality/module.py
just gate packages/tl-cli/tests/test_cli_checklist.py packages/tl-cli/tests/test_module_cli_groups.py
```
Expected: clean on those paths; `gate: PASS` on each line. No `just check` (the orchestrator runs it at DONE), no whole-repo pyright, never `packages/tl-api/tests/test_commands.py`.

## Escalation triggers
A verb needs a command field the models lack; the handlers refuse a legitimate checklist the fixtures hold.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins and regenerated files outside Allowed paths. Commit subjects `P2-INSP-T05: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
