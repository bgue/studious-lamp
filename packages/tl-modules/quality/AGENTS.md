# AGENTS.md: tl-mod-quality

Rules of the root `AGENTS.md` apply. Local rules:

- Table `cur_quality_punch_item` is generated; never hand-write DDL (use `ddl_for`).
- Events are immutable; a punch item is hidden through its source record, never by a class of its own.
- Every move of the workflow is a module command (`by_module=True`); `Void` is the only terminal state.
- Tests live in `tests/`; S2 adds commands in `commands.py` and fills `PUNCH_COMMANDS`.
