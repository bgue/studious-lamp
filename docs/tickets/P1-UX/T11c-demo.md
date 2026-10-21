# P1-UX-T11c — Demo script `just demo P1-UX` (SQLite and Postgres)

Status: ready (staged: dispatch when T08c and T09a are merged)
Tier: haiku
Kind: ticket
Review: full
Labels: tests, docs
Depends on: S2, S3, T01-T10, T13, T08b, T09d (merged); T11 merged for clause 2 (it runs T11's test file)
Branch: `p1/ux-t11c-demo`

## Goal
`dev/demos/P1-UX.sh` and its driver `dev/demos/p1_ux_demo.py` prove SCOPE demo clauses 1 to 4 on a real ledger, once on SQLite and once on Postgres, in the structure of `dev/demos/P1-I8.sh` (header comment, `TL_DEMO_BACKENDS`, `step`/`expect`/`refuse`/`fail`/`as`, `PASS n:` lines, `DEMO FAILED`, final `P1-UX demo OK on: ...`). The ledger holds values for the three new sets (F7), so the Properties tab has something to show.

## Brief references (pasted)
> Demo 1: from each register (documents, tags, correspondence register/inbox/clocks, RFI log, commercial, schedule lists, review queue) Enter opens the record screen; its Properties tab lists the sets for that type with labels.
> Demo 2: as a plain user a test walks the screens and greps the text: no ULID, hash, schema version, internal key, clock or calendar id; the toggle key answers with a one-line refusal. Demo 3: as an admin the toggle shows those details and hides them again. Demo 4: a restricted record opened from a stale list row by a plain user reads exactly like a missing one.
> Sets (fixture co.acme.engineering 3.2.0): `document_data` (originator, area, system, confidentiality_note, native_format [DocumentFormat], review_due date) on documents.Document; `rfi_data` (location, drawing_ref, trade [Trade], cost_estimate decimal, cost_currency [Currency], schedule_impact_days int) on correspondence.TechnicalItem; `correspondence_data` (contract_clause, other_party_ref, response_required_by date, delivery_method [DeliveryMethod]) on Correspondence and CommercialItem.

## Interfaces (verbatim from repo)
```
tl pset set --project P123 KEY PSET NAME=VALUE...     # VALUE is JSON when it parses (packages/tl-cli/src/tl_cli/pset.py)
P1-I6.sh: tl rfi raise --project P123 --subject .. --question .. --discipline structural --required-by DATE --to "Meridian:pm@meridian.example"; tl rfi submit|issue NUMBER --project P123 (issue needs the controller dora)
P1-I5.sh: tl corr receive --project P123 --subject .. --from "Acme Construction" [--file F --body-file F]
P1-I2.sh: tl doc register ISO-1234 --project P123 --title .. --type ISO --discipline PIP --originator ..
driver pattern (p1_i6_demo.py): async def with TlApp(EmbeddedClient.for_target(os.environ["TL_DB"], actor=ACTOR), scope="project:P123", actor=ACTOR, is_admin=..) .run_test(size=(200, 50)); main() dispatches on argv[1]; say(); passed(n, text)
TUI: ctrl+g (domain screen, keys 1 2 3), f5 (correspondence), f7 documents, f8 tags, f12 schedule, ctrl+r review queue; Enter on a row -> RecordScreen; record tabs ids tab-details, tab-psets (Properties), tab-links, tab-history, tab-thread
```

## Context (read these, nothing else)
- `dev/demos/P1-I8.sh` (lines 1-110 and the last 12 lines: structure), `dev/demos/p1_i6_demo.py`, `dev/demos/P1-I6.sh` (lines 125-160: RFI and a restricted notice)
- `packages/tl-tui/src/tl_tui/widgets/record_screen.py`, `psets_tab.py` (what the Properties tab prints)
- `packages/tl-tui/tests/test_plain_walk.py` (T11, merged), `test_technical_toggle.py`
may explore: `dev/demos/P1-I5.sh`, `dev/demos/P1-I2.sh` for the seeding lines

## Allowed paths
- `dev/demos/P1-UX.sh` (create, executable), `dev/demos/p1_ux_demo.py` (create)
- `docs/reports/P1-UX/T11c.md` (create)

## Steps
1. Seed (shell): sign in demo (admin), amy (plain), dora (controller); register a document, raise and issue an RFI, receive a letter; `tl pset set` the three sets with conforming values (codes from `schema/fixtures/standards/co.acme.standards@1.0.0.yaml`; dates ISO), checking each prints `conformance`.
2. Clause 1, `driver registers`: as the controller, for F7, F8, F5 (register, inbox, clocks), Ctrl+G (RFI log, commercial), F12, Ctrl+R: Enter on the first row opens `RecordScreen`; press `2`; the Properties text contains the set label (`Document data`, `RFI data`, `Correspondence data`, or the tag's class set) and one value label (`Originator`, `Trade`, `Contract clause`); Esc returns to the same row. A register with no rows is `say`'d, not failed, except documents, tags, RFIs and letters.
3. Clause 2, plain user: `driver plain` opens each of those registers and each record screen as amy and asserts `find_technical(text, labels) == []`, then presses `ctrl+d` and asserts the one-line `REFUSAL` and that nothing changed. Also run `uv run pytest packages/tl-tui/tests/test_plain_walk.py -q` (as P0-I2.sh does) and `expect` its pass line.
4. Clause 3, `driver admin`: as demo, `ctrl+d` shows technical text on the document register (`find_technical != []`), `ctrl+d` again hides it (`== []`).
5. Clause 4, `driver hidden`: the restricted record of P1-I6 clause 3 (early warning) or another restricted record the script can make; as amy, `open_record` with its id (a stale row) and with an unknown ULID gives byte-equal screen text containing `No record` and neither id nor number.
6. End with `P1-UX demo OK on: ...`. Postgres is dropped afterwards like P1-I8.sh.

## Acceptance
```
just check
bash -n dev/demos/P1-UX.sh
TL_DEMO_BACKENDS=sqlite just demo P1-UX
just demo P1-UX
```
Expected: `PASS 1` to `PASS 4` per backend, `P1-UX demo OK on: sqlite postgres`. Paths: both files new. Do not run `just gate`.

## Tests to add
None (the demo is the test). Do not copy the walk into the driver; clause 2 runs T11's file.

## Report requirements
Standard report; paste only the `PASS` lines and the last line of each backend run. Say how each restricted record was made.

## Escalation triggers
- A register has no way to seed a row from the CLI: say which and stop.
- A seeded value is refused by the set: report the message; do not edit the schema.
- Postgres is unreachable: report `ge`, not a skip.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
