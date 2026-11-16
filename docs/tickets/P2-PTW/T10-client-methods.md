# P2-PTW-T10 - Permit, isolation and gas test read methods, the command door and the fake

Status: ready (written r6; base `p2/ip-r3`; PTW-T07, T07b, T01, T02 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, api, read, access
Depends on: P2-PTW-T01, T02 (views), P2-PTW-T07, T07b (routes), merged; pattern P2-INSP-T08 (merged, `docs/reports/P2-IP/INSPT08.md`)
Branch: `p2/ptw-t10-client`
Worktree: `/home/user/wt/ptw/t10` (from `p2/ip-r3`)

## Goal
Seven methods exist on `ClientInterface` (`tl_tui/client.py`), the embedded client, `ApiClient` and `FakeClient`, so the terminal screens of T11 read permits, the board, isolations and gas tests and run permit commands from any of them. Follow the INSP-T08 result file by file: a new `tl_api/client/permits.py` mixin (`PermitsApi`, wired in `tl_api/client/__init__.py` as `QualityApi` is), a block in `embedded.py` with the same `_module_command` door, a block in `client.py`, a fake `fakes_permits.py`.

## Interfaces (same names, parameters and errors on every implementation)
```python
def list_permits(self, project, *, state=None, permit_type=None, area=None, holder=None, limit=100, offset=0) -> PermitPage
def get_permit(self, project, key) -> PermitDetail            # RecordNotFoundError("no permit"): missing, hidden, other project: one text
def get_permit_board(self, project, *, area=None) -> PermitBoard
def list_isolations(self, project, *, state=None, energy=None, limit=100) -> IsolationPage
def get_isolation(self, project, key) -> IsolationDetail      # RecordNotFoundError("no isolation")
def list_gas_tests(self, project, permit_key) -> list[GasRow] # RecordNotFoundError("no permit") for a missing or hidden permit
def permit_command(self, name, cmd) -> CommandResult          # a model of tl_mod_permits.module.COMMANDS or iso_commands' table, by name
```
Types are the dataclasses of `tl_mod_permits.views` and `iso_views`. Routes are those of `tl_mod_permits/routes.py` (`/permits`, `/permits/board`, `/permits/{key}`, `/permits/isolations`, `/permits/isolations/{key}`, `/permits/{key}/gas-tests`). `ApiClient` decodes with `TypeAdapter` as `quality.py` does (the gas route returns a list: use `TypeAdapter(list[GasRow])`; read `routes.py` for its exact body). Embedded: the same calls the routes make, under the signed-in viewer, after the same `permits.view` check on `project:P` the routes make (read `_view_reader`), `now=utcnow()`; never a second SQL path. Which table names the command door accepts: read `module.py` (`COMMANDS`) and `iso_commands.py`; one union, an unknown name keeps the error `quality_command` gives. A command names its record by `id` (the `.id` of the row types). Fake: answers from lists a test gives it (`load_permits`, `load_isolations`, `load_gas_tests`), filters like the views, records each command in the list the quality fake uses; `seed_permits(client)` makes 8 permits (one of each shown state: Requested, Approved, Active, Lapsed, Suspended, Handed back, Closed, Rejected; two with an area), 3 isolations (Applied, Verified, Removed) and 3 gas tests on the Active permit (newest a Pass); the board is computed from the permit list as the view does (read `permit_board`'s output shape).

## Context (read these, nothing else)
- `docs/reports/P2-IP/INSPT08.md`, `packages/tl-api/src/tl_api/client/quality.py` and `__init__.py` (whole), `packages/tl-modules/permits/src/tl_mod_permits/routes.py` (signatures and the reader helper)
- `packages/tl-modules/permits/src/tl_mod_permits/views.py`, `iso_views.py` (dataclasses and signatures only)
- `packages/tl-tui/src/tl_tui/client.py` (the quality block), `embedded.py` (the quality block and `_module_command`), `packages/tl-tui/tests/fakes_insp.py`, `fakes.py` (mixin and init lines), `tests/api/test_client_insp.py` (the roundtrip pattern)
- `packages/tl-modules/permits/tests/permit_world.py`

## Allowed paths
- `packages/tl-api/src/tl_api/client/permits.py` (create), `packages/tl-api/src/tl_api/client/__init__.py`, `packages/tl-tui/src/tl_tui/client.py`, `packages/tl-tui/src/tl_tui/embedded.py` (edit)
- `packages/tl-tui/tests/fakes_permits.py` (create), `packages/tl-tui/tests/fakes.py` (mixin and init lines)
- `tests/api/test_client_permits.py` (create), `packages/tl-tui/tests/test_fakes_permits.py` (create)
- pins in union form, listed (rule 12): `tests/api/test_client_roundtrip.py`, `packages/tl-tui/tests/test_remote_client.py`, `packages/tl-tui/tests/test_client_module_roles.py` if they fail by method list only
- `docs/reports/P2-IP/PTWT10.md` (create)

## Tests to add
- `tests/api/test_client_permits.py` (ledger built by commands from `permit_world.py`; no projection writes): the embedded client and `ApiClient` over a `TestClient` give equal answers for the six reads; `permit_command("ApprovePermit", ...)` by a controller who is not the requester changes state through both and the next read shows it; approve by the requester is refused with the S2 text on both; one `RecordNotFoundError` text for a missing permit key, isolation key and gas-test permit key on both; a permit for a restricted record is absent from the list, its `total` and the board counts, and answers the missing text for `get_permit` and `list_gas_tests`, for the lowest-clearance client; a Lapsed permit reads Lapsed on both (clock moved past `valid_until` by passing the stored time, never by sleeping).
- `packages/tl-tui/tests/test_fakes_permits.py`: `seed_permits` counts, each filter narrows, `total` equals rows, missing key raises, board counts equal the list, `permit_command` is recorded.

## Acceptance
```
uv run ruff format --check packages/tl-api/src/tl_api/client packages/tl-tui tests/api/test_client_permits.py
uv run ruff check packages/tl-api/src/tl_api/client packages/tl-tui tests/api/test_client_permits.py
uv run pyright packages/tl-api/src/tl_api/client/permits.py packages/tl-tui/src/tl_tui/client.py packages/tl-tui/src/tl_tui/embedded.py packages/tl-tui/tests/fakes_permits.py tests/api/test_client_permits.py packages/tl-tui/tests/test_fakes_permits.py
just gate tests/api/test_client_permits.py packages/tl-tui/tests/test_fakes_permits.py
just gate tests/api/test_client_insp.py tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_remote_client.py packages/tl-tui/tests/test_client_module_roles.py
```
Expected: clean; `gate: PASS`. No `just check`, no whole-repo pyright, never `packages/tl-api/tests/test_commands.py`.

## Escalation triggers
A T07 or T07b model lacks a field the screens need; `ClientInterface` already holds one of the names; the roundtrip test needs a change other than a method list; the board's shape cannot be rebuilt in the fake without reading the view.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins listed. Commit subjects `P2-PTW-T10: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
