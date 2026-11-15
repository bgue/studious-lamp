# AGENTS.md: tl-mod-scaffold

Rules of the root `AGENTS.md` apply. Local rules:

- Tables `cur_scaffold_scaffold` and `cur_scaffold_scaffold_inspection` are generated; never hand-write DDL (use `ddl_for`).
- Events are immutable. A scaffold's tag and state change only through the module's nine commands (`by_module=True`); the
  inspections-due job never changes a tag or a state, it only appends `Scaffold.InspectionDue`.
- An inspection is a fact: it takes no generic commands. A removed scaffold refuses every generic command (`guards.not_removed`).
- `TagScaffoldGreen` (`scaffold.tag.green`) is the one controller word. Do not add an account role for it.
- Read the requisitions through `tl_mod_requisitions.api` (`open_requisitions_for`, `viewer=LOWEST`) and its `names`. Never import
  a requisitions handler. The one direct read is `cur_requisitions_scaffold_request` (`names.REQUEST_TABLE`, decision S1-F4).
- Every read takes keyword `viewer=` (default `confidentiality.LOWEST`). The routes pass the request's viewer, never the default.
- A hidden scaffold answers as a missing one. A hidden work package counts in the dismantle check and is named only as
  "a work package you cannot see".
- No CLI group and no MCP tool yet. They wait for the extension hooks: the command splat in `tl_api/commands.py` and the router
  line in `tl_api/app.py` move into `module.py`, then the CLI and MCP surfaces can register.
- Screens hold no business logic: the TUI calls the same views and commands the API uses.
