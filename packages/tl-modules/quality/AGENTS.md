# AGENTS.md: tl-mod-quality

Rules of the root `AGENTS.md` apply. Local rules:

- Table `cur_quality_punch_item` is generated; never hand-write DDL (use `ddl_for`).
- Events are immutable; a punch item is hidden through its source record, never by a class of its own.
- Every move of the workflow is a module command (`by_module=True`); `Void` is the only terminal state.
- Commands are defined in `commands.py` and listed in `PUNCH_COMMANDS` (`module.py`); a command that is not a row there,
  or an exclusion in `tests/tools/proposable_exclusions.toml`, fails `test_exclusions.py`.
- Clear and verify are never agent tools: no MCP tool may clear, verify, edit, reopen or void. `propose_punch_item` is the
  only agent write, and it proposes a `RaisePunchItem` that a person accepts.
- Screens hold no business logic: the TUI calls the same commands and views (`views.py`) that the API and CLI use.
- Every read takes keyword `viewer=` (default `confidentiality.LOWEST`); a caller that reads for a person says so.
- A void item refuses every further change (`guards.not_void`, `MSG_VOID`); a new command on punch items needs a guard row.
- Tests live in `tests/`; the shared world is `tests/punch_world.py`. Handlers read the ambient viewer, so a test world
  runs them under `use_viewer(viewer_for_actor(...))`.

Inspections and checklists (P2-INSP):

- Verifier differs from recorder: `VerifyInspection` refuses the person in `recorded_by` (`MSG_SELF_VERIFY`). Do not relax it.
- A Published checklist never changes; a change is a revision (version n+1, Draft, `supersedes_id`). A Cancelled inspection and a
  Retired checklist refuse further change (`guards.MSG_CANCELLED`, `guards.MSG_RETIRED`).
- Result is computed, never typed: `insp_rules.result_of` is the one rule. The screen, the CLI and the handler call it.
- Hidden subject reads as missing: `insp_views` and the handlers apply the viewer filter before a count or a `LIMIT`.
- Agents: `propose_inspection` is the only inspection agent write, and it proposes a `PlanInspection`. No MCP tool schedules,
  records, verifies, reinspects or cancels.
- `checks.py` (`inspections_planned`) reads only quality tables and returns keys and counts, never titles.
- Words `quality.checklist.*` and `quality.inspection.*` are rows of `schema/settings/access-words.yaml`; a command's word is
  `command_words` in `module.py`, and `test_access_words.py` pins the count.
