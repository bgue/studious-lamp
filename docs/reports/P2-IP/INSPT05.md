# Report — P2-INSP-T05

Branch: `p2/insp-t05-cli-checklist`   Commit(s): `ab12284` (code), report commit follows

## Deviations
- Commit subject uses the ticket ID `P2-INSP-T05:` (the ticket file and AGENTS rule 9), not the dispatch's `P2-IP-INSPT05:`.
- `--questions-file` is read as JSON, as the ticket says. The fixtures in `schema/fixtures/quality/checklists/` are YAML documents with `title`, `discipline` and `questions` keys, so they are not directly loadable; no YAML parser was added.
- `ls` prints a header `checklists: <shown> of <total>` (the ticket gives `n of total` without a fixed form).
- Nothing outside Allowed paths changed. No pins, no regenerated files.

## Changed files
- `packages/tl-cli/src/tl_cli/checklist.py` — the `checklist` Typer group and `register_all()`.
- `packages/tl-cli/src/tl_cli/checklist_write.py` — create, edit, publish, revise, retire; question-file reader (256 KiB cap).
- `packages/tl-cli/src/tl_cli/checklist_read.py` — ls (filters, limit, total header) and show (properties, question table).
- `packages/tl-cli/tests/test_cli_checklist.py` — 11 tests covering ticket items 1 to 5.
- `packages/tl-cli/tests/test_module_cli_groups.py` — `"checklist"` added to `OLD_GROUPS` only.
- `packages/tl-modules/quality/src/tl_mod_quality/module.py` — `cli_groups` gains `"tl_cli.checklist:app"` (appended).
- `docs/reports/P2-IP/INSPT05.md` — this report.

## Commands and output
```
$ uv run ruff format --check <5 paths>
5 files already formatted
$ uv run ruff check <5 paths>
All checks passed!
$ uv run pyright <5 paths>
0 errors, 0 warnings, 0 informations
$ just gate packages/tl-cli/tests/test_cli_checklist.py packages/tl-cli/tests/test_module_cli_groups.py
part 1: exit 0, 17 passed in 37.94s
gate: PASS
```
Ruff format and ruff check were first run with failures (long lines, import order); fixed, then re-run to the clean output above.

## Tests added
- `test_cli_checklist.py::test_create_edit_publish_revise_retire_move_the_states` — lines print; states move; the old version stays Published until the revision publishes, then Retires.
- `test_an_invalid_question_file_is_the_publish_refusal` — publish prints the handler's `error: the question list cannot be published: ...`.
- `test_an_oversized_question_file_is_refused_before_it_is_read` — `error: questions file is too large`.
- `test_a_published_checklist_refuses_edit` — exact handler text.
- `test_ls_filters_and_total` — discipline, state, limit, and a bad `--state` (exit 2).
- `test_show_prints_the_question_table_and_no_id` — exact table lines, no record id.
- `test_an_unknown_key_is_no_checklist` — show and edit.
- `test_a_viewer_is_refused_the_write_verbs` — viewer grant refused on create.
- `test_a_user_is_refused_publish_and_retire` — user refused on publish and retire.
- `test_an_actor_without_quality_view_is_refused_the_reads` — disabled account, ls and show.
- `test_tl_help_lists_checklist` — `checklist` row in `tl --help`.

## Learnings (proposed)
- Every platform role except `admin` derives module `read` (`schema/settings/module-roles.yaml`, `derive: user`), and `admin` holds every word. So a "no quality.view" test needs a disabled account (`_account_is_live` gives no words), not a role-less account (which `accounts.create_account` refuses).
- `handle_retire_checklist` and `handle_publish_checklist` return `key=None`; only create and revise return a key. The CLI prints the key the user typed for the other verbs.

## Open questions / Blocked
- None blocking. Question for the supervisor: should `schema/fixtures/quality/checklists/*.yaml` (a title/discipline/questions wrapper) be accepted by `--questions-file`, or should the fixtures get a plain JSON question-list sibling? The ticket says JSON list, so I did not add YAML support.
- `--discipline` cannot clear a discipline from the CLI (the model sends `null` for that, and the CLI only sends given values). The ticket did not ask for a clear flag, so none was added.
