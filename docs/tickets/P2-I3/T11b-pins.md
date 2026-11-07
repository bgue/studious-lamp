# P2-I3-T11b — Three missing pins in the materials tests (review of T11)

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tests
Depends on: T11 (this branch).
Branch: `p2/i3-t11-tests` (the same branch; commit on top)

## Goal
The review of T11 (`docs/reports/P2-I3/T11.md`) found three gaps. Add tests only; change no file under `src/`.
1. **D29, republished take-off key.** In `packages/tl-modules/materials/tests/test_pins.py`, add a test that publishes
   a derived `mto` document, compensates the publication, republishes, and asserts the republished take-off line key
   ends in `-2` (the first publish gives `-1`). Reuse the publish/compensate setup the existing S4 acceptance tests
   use (`grep -rn "CompensatePublication\|PublishDerivedMto" packages/tl-modules/materials/tests`). If the key
   suffix is not `-2` in the code, stop and write Blocked with the actual key: do not change the assertion to fit.
2. **Q5, adopt is a project word at company scope.** In `test_pins.py`, add a test that `AdoptItem` at company scope
   is refused for an account without the project word and accepted with it (find the access word with
   `grep -n "AdoptItem" packages/tl-modules/materials/src/tl_mod_materials/commands.py`; the refusal text is the
   standard "<Cmd> needs the <word> access word for materials on <scope>").
3. **Seeded rebuild loop.** In `packages/tl-modules/materials/tests/test_projection_rebuild.py`, add one test: with
   `random.Random(7)`, apply 25 random valid movements (receipt, issue, transfer, return, adjust within stock) to a
   fresh world, then rebuild the projections and assert the stock and movement rows equal the rows before the rebuild.
   Use the World helper the file already uses.

## Allowed paths
- `packages/tl-modules/materials/tests/test_pins.py`, `packages/tl-modules/materials/tests/test_projection_rebuild.py`
- `docs/reports/P2-I3/T11.md` (append a section "T11b" with the three tests and their output)

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate packages/tl-modules/materials | tail -45 | tee .gate/summary.txt` ends `gate: PASS`
