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
