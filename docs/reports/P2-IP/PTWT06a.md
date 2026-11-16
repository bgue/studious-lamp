# Report — P2-PTW-T06a (dispatched as P2-IP-PTWT06a)

Branch: `p2/ptw-t06a-cli-isolation`   Commit(s): this report is in the one commit on the branch (`git log -1`)

## Deviations
- Commit subject uses the dispatch prefix `P2-IP-PTWT06a:`; the ticket id is `P2-PTW-T06a` (ticket says `P2-PTW-TNN`).
- Report path is `docs/reports/P2-IP/PTWT06a.md` (dispatch), not the ticket's `docs/reports/P2-PTW/T06a.md`.
- Every write verb takes `--actor` (default dev), as the T04 permit writes do; the ticket's option list omits it.
- Isolation writes run build, gate and handler under the acting person's viewer (`_execute` in `cli_isolation.py`). T04's `cli_permit_write._execute` does not. Reason in Learnings 1. Handler code is untouched.

## Changed files
- `packages/tl-modules/permits/src/tl_mod_permits/cli_isolation.py` — apply, verify, remove, link, unlink, ls, show, export on `isolation_app`.
- `packages/tl-cli/tests/test_cli_isolation.py` — new, 9 tests (the five ticket groups, plus help).
- `docs/reports/P2-IP/PTWT06a.md` — this report.

## Commands and output
```
$ uv run ruff format --check packages/tl-modules/permits packages/tl-cli/tests/test_cli_isolation.py
50 files already formatted
$ uv run ruff check packages/tl-modules/permits packages/tl-cli/tests/test_cli_isolation.py
All checks passed!
$ uv run pyright packages/tl-modules/permits/src/tl_mod_permits/cli_isolation.py packages/tl-cli/tests/test_cli_isolation.py
0 errors, 0 warnings, 0 informations
$ just gate packages/tl-cli/tests/test_cli_isolation.py packages/tl-modules/permits/tests/test_module_spec.py
part 1: exit 0, 15 passed in 27.01s
gate: PASS
```

## Tests added
- `test_cli_isolation.py::test_apply_verify_link_unlink_and_remove_print_their_line_and_move_the_state` — each verb prints its line; state moves; ls depends 1, then 0; show lists the permit key.
- `::test_the_applier_cannot_verify_and_a_needed_isolation_cannot_be_removed` — handler text for self-verify; remove refused while Approved, then Active.
- `::test_removing_while_a_hidden_permit_needs_it_prints_the_fixed_text_and_no_key` — "a permit you cannot see", no key.
- `::test_a_hidden_point_record_leaves_no_row_and_no_count_and_show_answers_as_missing` — uma 1 of 1, dora 2 of 2; show text equal to unknown key.
- `::test_export_is_the_views_export_of_the_same_list` — csv and jsonl equal `isolation_export_rows`.
- `::test_a_bad_export_format_and_a_bad_state_are_usage_errors` — xml, Nope, bad energy exit 2.
- `::test_a_person_without_the_write_word_is_refused_by_require_command` — vera refused.
- `::test_an_actor_without_permits_view_is_refused_before_any_read` — agent:nobody on ls, show, export.
- `::test_help_lists_the_eight_verbs`.

## Learnings (proposed)
1. The CLI root sets the process viewer to `session_viewer(target)` (`tl_cli/main.py:275`). On a dev ledger with no session that is the file owner, who reads restricted records. A handler refusal that calls `confidentiality.is_hidden` under that ambient viewer named a permit `pam` cannot see (`MSG_IN_USE` plus the hidden text came out as a key). T04's `_execute` runs handlers the same way, so any T04 refusal that names a record may leak. Supervisor should check.
2. `tl_mod_permits.iso_views` does not re-export `EXPORT_FORMATS` (pyright: reportPrivateImportUsage). Import it from `tl_mod_permits.views`.
3. `isolation_list` has no offset, so an export cannot page (see Open questions).

## Open questions / Blocked
- Export is capped. `isolation_list` takes no offset, so `isolation export` reads at most `iso_views.MAX_LIMIT` (500) rows and cuts silently. Permit export pages. Decide: add an offset to `iso_views` (outside this ticket) or accept the cap.
- Output lines not fixed by the ticket, chosen here: `linked|unlinked <permit-key> <isolation-key>  version <v>`; show label `Linked permits`. Say if other wording is wanted.
- Status: done; no Blocked items.
