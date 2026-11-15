# P2-QR-T03 — Scan-card contract harness and a fake provider

Status: ready (dispatch after QR S1 is merged to `p2/ip`; the provided test is committed)
Tier: haiku
Kind: ticket
Review: full
Labels: tests, core-module
Depends on: S1 (merged: `tl_core.qr.types` and `tl_core.qr.registry` exist)
Branch: `p2/qr-t03-card-harness`
Worktree: harness-created under `/home/user/wt/qr/t03` (from `p2/ip` head)

## Goal
One test helper that every status-card provider (awp, scaffold, inspection, permit) calls on its own provider to prove
it keeps the S1 contract. Test code only: `tests/contract/scan_card_harness.py`. The plan named the helper inside
`test_scan_card_contract.py`; it is a separate module so other tests can import it (deviation, recorded in the plan check).

## Brief references (pasted)
> `ScanCardProvider` (S1, `tl_core.qr.types`): `record_type: str`, `view_word: str`,
> `card(conn, record_id, viewer, now) -> ScanCard | None`. A pure read; never writes; never raises for a bad or hidden
> record (answers `None`); `None` for a record the viewer cannot see; never opens the network.
> `Viewer(actor, level, account, system)` and `LOWEST` are in `tl_core.confidentiality`.

## Interfaces (final)
```python
class ScanCardContractViolation(AssertionError): ...
def check_scan_card_contract(provider: object, conn: Connection, *, visible_id: str, hidden_id: str,
                             privileged: Viewer, now: datetime) -> ScanCard
```
Checks, in this order; each failure raises `ScanCardContractViolation` whose message contains the quoted word:
1. `isinstance(provider, ScanCardProvider)` ("protocol").
2. `provider.view_word` matches `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$` ("view_word").
3. `card(conn, visible_id, LOWEST, now)` returns a `ScanCard` ("visible"); its `record_type == provider.record_type`
   ("record_type"); `as_of` is aware.
4. `card(conn, hidden_id, LOWEST, now)` is `None` ("hidden"); with `privileged` it returns a `ScanCard`.
5. For the ids `""`, `"x" * 300`, `"00000000000000000000000000"` the call returns `None` and does not raise ("raised").
6. No statement run through `conn` during checks 3 to 5 starts with INSERT, UPDATE, DELETE, REPLACE, CREATE, DROP or
   ALTER ("write"): count them with `sqlalchemy.event.listen(conn, "before_cursor_execute", ...)` and remove the listener.
Return the card of check 3. Any exception from `card` in checks 3 and 4 is also a violation ("raised").

## Context (read these, nothing else)
- `docs/tickets/P2-QR/provided/T03_test_scan_card_contract.py` (the test; copy it byte-identical)
- `packages/tl-core/src/tl_core/qr/types.py`
- `packages/tl-core/src/tl_core/readiness/harness.py` (the same pattern for readiness checks; style only)
may explore: (none)

## Allowed paths
- `tests/contract/scan_card_harness.py` (create); `tests/contract/test_scan_card_contract.py` (create: byte-identical copy)
- `docs/reports/P2-QR/T03.md` (create)

## Acceptance
```
just check
just gate tests/contract/test_scan_card_contract.py
```
Expected: all pass, `gate: PASS`.

## Tests to add
The provided test only.

## Report requirements
Standard report; first line: test copy byte-identical or not (phrase 101).

## Escalation triggers
- Stop if `tl_core.qr.types` lacks a name used above.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

## Amendment 1 (orchestrator, 2026-11-15)
The provided test failed `just check` (ruff E501 and format) where it lands. Decision: the landed copy is reformatted with
`ruff format` and docstring wraps only, no assertion changed, and `docs/tickets/P2-QR/provided/<this test>` is updated to
the same bytes so the two stay identical. Allowed paths gain that provided file for this purpose only.
