# P2-I4B-T13: DONE-gate fallout of the scaffold module

Goal: make the DONE gate green after the scaffold module landed. Tests, pins and snapshots only, unless a real product bug is proven (then the report says so).

## Fix
1. TUI snapshots: `packages/tl-tui/tests/test_module_roles_log.py` (80x24, 170x40) and `test_snapshots_links.py::test_command_palette`. Regenerate with the repo snapshot-update flag; check the new rows are scaffold rows only.
2. Webhook scenario: `tests/webhooks/scenario.py` never delivers the scaffold events. Extend it through the real scaffold commands so every scaffold event type is delivered and validates. Do not exclude them.
   Red tests: `tests/contract/test_webhook_catalog_contract.py`, `tests/parity/test_webhooks_parity.py` (sqlite).
3. `tests/services/test_module_role_seams.py`: add scaffold to the expected API-table index set and to the require-generic walk, in union form.

## Allowed paths
`packages/tl-tui/tests/**` (snapshots included), `tests/webhooks/**`, `tests/contract/**`, `tests/parity/**`, `tests/services/test_module_role_seams.py`, `docs/tickets/P2-I4B/T13*`, `docs/reports/P2-I4B/T13.md`.

## Gate
`NODE_OPTIONS=--max-old-space-size=6144 just check`; `just gate` on the TUI tests; on `tests/contract tests/webhooks`; on the parity and seams tests; `just gate-pg tests/parity/test_webhooks_parity.py`.
