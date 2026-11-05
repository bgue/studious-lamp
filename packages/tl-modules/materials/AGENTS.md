# AGENTS.md — tl-mod-materials

Read the repository `AGENTS.md` first. These rules add to it and never relax it.

## Nevers
- Never write stock with a command other than `AcceptReceipt`. There is no direct receive command; stock enters only when a receipt is accepted (spec §3).
- Never change an event or a row in place. Corrections are new events: a void is `Record.Voided`, a wrong movement is an opposite movement (AGENTS.md rule 3).
- Never do quantity arithmetic in SQL. Read a stored quantity with `common.dec`, sum and compare in `Decimal`, quantize to 3 places, bind with `common.num`. Event text is the quantity as `"12.500"` (`common.py` docstring; S2 report).
- Never read a stored quantity as a float. SQLite returns `NUMERIC` as a float; `dec(str(x))` restores it.
- Never give an agent a materials command. Agents get the `mcp.*` materials tools only; `propose_reservation` files a proposal, and a person with `materials.reserve` accepts it.
- Never let a hidden record show as present. A hidden record answers as one that never existed (`RecordNotFoundError` with the same text as a missing one). Every read filters by the viewer's class (ADR-0016); the viewer defaults to the lowest clearance. A test must not widen that default.
- Never put SQLite- or Postgres-specific SQL in this package. Statements stay dialect-neutral (repository rule 5); runtime dialect code lives under `packages/tl-adapters/`.

## Conventions
- **Stored `available`.** `cur_materials_stock.available` is a stored decimal column, not a view column (S1 report). Movements keep it current; a reader uses it and does not recompute it.
- **Reserve and issue check.** A movement that takes more than the lot has available at the location, plus what the named take-off line already holds there, is refused with `InsufficientStockError` (`handlers/movements.py`). A consumable is issued against a cost code (`MovementRuleError` otherwise).
- **MTR rule.** When a receipt line's item category is listed in `materials.receipt.mtr_required_categories`, the receipt's `mtr` slot must hold an available file before `AcceptReceipt` succeeds (`handlers/receipts.py`, `actions.py` `_mtr_ok`). After Accept only `certificate` and `photo` files attach (S6 report).
- **Reserve check for readiness.** `materials_reserved` is read-only. It counts covered lines (`reserved_qty + issued_qty >= qty`) in at most three statements and never raises for a bad record; a failed read is `unknown` with a fixed detail.
- **Take-off lines.** `AssignMtoLines` is refused when a line has a reservation. Compensation of an MTO publication is refused when a line has a reservation or an issue (spec §3).
- **Commands.** Each handler calls `require_project`, `require_visible` on each id it takes, and `correlated(cmd)` (spec §3).
- **Tests.** Test every new access word against the `access` of its command row (`actions.py` `Rule` table). Test the hidden case: a hidden record reads as missing in views and commands.
