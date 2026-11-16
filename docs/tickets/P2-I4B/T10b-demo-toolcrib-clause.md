# P2-I4B-T10b — Demo clause 7: the toolcrib screen issues a tool and takes it back

Status: ready after T10a merges (same script and driver)
Tier: haiku
Kind: ticket
Review: full
Labels: tests
Depends on: T06, T07a (merged), T10a
Branch: `p2/i4b-t10b-demo-toolcrib`
Worktree: `/home/user/wt/i4b/t10b` (from `p2/i4b` head)

## Goal
**Clause 7** (plan clause 6) of `just demo P2-I4`: the toolcrib screen issues a tool to a person and takes it back, one line each, keyboard only, on both adapters.

## Brief references (pasted)
> Plan clause 6: "The toolcrib screen issues a tool to a person and takes it back, one line each, keyboard only." Keys: F2 issue, F3 return, Ctrl+R (D11, D15).

## Interfaces (verbatim from repo at the branch point)
Driver mode `toolcrib` added to `dev/demos/p2_i4b_demo.py` (created by T10a; the `World` copy, `passed`, `miss`, `check`, `main` dispatch exist there). It copies the method of `dev/accept/P2-I4B/T06.py`: `receive_at_crib` (put stock at crib TC1 through the materials receipt commands; the demo world has the item library and PO lines but no receipts), `pick_lot`, `check_issue_and_return` and `with_screen` (Textual pilot over `EmbeddedClient`, the typed lines, the status text, the on-hand check before and after). Actor `user:crib` in that script; here use a person the script seeded and who holds the materials words (`uma` has `user` by derivation; if issue is refused for her, grant `materials user` to a new person `cal` as the script does for the others, and say so). Crib `TC1` is a location of the project in the demo world only if the script loads it: if not, the driver creates it the way T06.py does. Output: `PASS clause 7: issued <qty> <lot> to <person>, on hand <a> -> <b>; returned, on hand <b> -> <a>`.

## Context (read these, nothing else)
- `dev/accept/P2-I4B/T06.py`, `dev/demos/p2_i4b_demo.py`, `dev/demos/P2-I4.sh` (the block T10a added)
- `packages/tl-tui/src/tl_tui/widgets/toolcrib_screen.py` (docstring and key bindings only)
- `docs/reports/P2-I4B/{T06,T07a}.md`

## Allowed paths
- `dev/demos/p2_i4b_demo.py` (edit: one mode and its helpers); `dev/demos/P2-I4.sh` (edit: header comment line, one step block before the final `drop_pg`)
- `docs/reports/P2-I4B/T10b.md` (create)

## Acceptance
```
just check
TL_DEMO_BACKENDS=sqlite just demo P2-I4
TL_DEMO_BACKENDS=postgres just demo P2-I4
```
Expected: `PASS clause 1` to `PASS clause 7`, `P2-I4 demo OK`. Background, long timeout, once each; paste the PASS lines and the last line only.

## Tests to add
none beyond the demo; ruff and pyright clean.

## Report requirements
Standard report; first line lists any deviation (who acted, how the crib stock was made).

## Escalation triggers
- Stop if the screen needs a setting or a location the demo world lacks and the T06.py method does not create it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

## Amendment 1 (orchestrator, 2026-11-15; review F1)
The demo world has no crib TC1 and T06.py creates none. Accepted as built: the driver defines TC1 with `DefineLocation`
in the demo world (demo data only), and the script grants the demo's sue the role needed to do so. No product code changed.
