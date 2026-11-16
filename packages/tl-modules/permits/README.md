# tl-mod-permits

Purpose: permit to work (brief §7.1, §9 M3, §9 M9). Three record types: `permits.Permit` (`P123-PTW-0001`),
`permits.Isolation` (`P123-ISL-0001`) and `permits.GasTest` (`P123-GAS-0001`). Design:
`docs/build-spec/module-designs/permits.md`. This piece (P2-PTW S1) is the schema, workflows, numbering, words,
settings, type table, projectors and the module skeleton. P2-PTW S2 adds the ten permit commands, the issue
guards and the hooks (commands, read router, tools, three CLI groups).

## Files
- Schema `schema/modules/permits/` (`module.yaml`, `permit.yaml`, `isolation.yaml`, `gas_test.yaml`, `events.yaml`);
  workflows `schema/fixtures/workflows/permits-{permit,isolation}.yaml`; type table `schema/fixtures/permits/types.yaml`.
- `names.py`: record types, states, words, event names. `types_table.py`: `load_types()` and `TypeRule`.
- `projectors/`: `PermitProjector`, `IsolationProjector`, `GasTestProjector`. `module.py`: `COMMANDS`, `PROPOSABLE`, `spec()`.
- `commands.py` (ten models), `handlers/permit.py` (handlers; the clock is `handlers.common.now`), `guards.py`
  (`issue_guards`, `NEEDS`), `errors.py`. `views.py`: stub until T01.
- Surfaces: `routes.py`, `tools.py` (empty until T05 and later), `cli.py` (the three Typer groups `permit`, `isolation`,
  `gastest`; each ticket adds commands in its own `cli_*.py`, imported at the bottom of `cli.py`).

## Names
Record types `permits.Permit`, `permits.Isolation`, `permits.GasTest`; tables `cur_permits_permit`,
`cur_permits_isolation`, `cur_permits_gas_test`. Permit states: Requested, Approved, Active, Suspended, Handed back,
Closed, Rejected, Cancelled (Lapsed is derived, not a state). Isolation states: Applied, Verified, Removed.
