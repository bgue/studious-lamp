# P2-I3-T08 — Demo `just demo P2-I3`: eleven clauses on SQLite and Postgres

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tests, docs
Depends on: S3, S4, S5, T05a-d, T06a-h, T07 (merged). Clause 6 uses the awp commands: the orchestrator merges p2/i1 into p2/i3 before this ticket runs (Q10); S6 and T06i are not needed.
Branch: `p2/i3-t08-demo`   (from p2/i3; check `git rev-list --left-right --count p2/i3...HEAD` is `0 0`)

## Goal
`just demo P2-I3` builds a fresh ledger on SQLite, then on a throw-away Postgres database, and prints one `PASS clause N` per clause of the spec (section 10), each on both adapters, then `P2-I3 demo OK on: sqlite postgres`. Same shape as `dev/demos/P2-W0.sh` + `p2_w0_demo.py`: the shell script drives `tl` commands as named people (`as NAME tl ...`); the Python driver covers what is not a command (API as a person, TUI at 170 columns, MCP, bounds). Exits non-zero and prints `DEMO FAILED: ...` on any miss. Nothing is left behind (temp dir, Postgres database dropped by the existing `p1_i0_demo.py pg-create|pg-drop` helpers).

## Brief references (pasted)
> Spec `docs/build-spec/specs/m4-materials.md` section 10 (the clauses, verbatim):
> 1. An admin loads `co.acme.materials@1.0.0` (twice: no change) and the 50-item library with `tl load --company` (plan, load, reconcile 0 mismatches); a company materials superuser's `DefineItem` is accepted, a project user's is refused. 2. A superuser loads the location tree project → warehouse → laydown L2 → toolcrib → gang box; a user's `DefineLocation` is refused. 3. A receipt of two flange lines, heat `H-7781`, against PO line `4471-3`; Accept without the MTR is refused with the fixed message; with it, two lots are on hand at L2. 4. Issue to a crew against a cost code (a consumable without one is refused), transfer, return one, a superuser adjust with a reason; a user's adjust and an over-issue are refused; stock equals the sum of movements and a rebuild gives the same rows. 5. `heat_trace H-7781` shows lots, receipt, MTR, locations, issues. 6. A derived `mto` document is published into an MTO for `P123-CWP-PIP-0001` (the driver creates that CWP through the awp commands); compensation removes it; republished. 7. A reservation against an MTO line; over-reserving is refused; `shortages` lists the rest; the `materials_reserved` check passes `check_readiness_contract` (its `ok` on a real IWP is a P2-I2 demo clause). 8. API, TUI (stock, receipts, MTO lines at 170 columns) and MCP agree; an agent's `propose_reservation` waits for a person. 9. A quantity with a non-ASCII digit, a negative, 4 decimals or over the bound is refused with a fixed message. 10. The item library shows the 50 items with project counts, and the locations screen shows the five-level tree with lot counts, at 170 columns. 11. The movement log lists the clause-4 movements in order with kind, from, to and by, and filtered by kind `issue` shows one row.

## Interfaces (what exists; do not change any of it)
- Shell shape and helpers to copy: `dev/demos/P2-W0.sh` (`quiet`, `tl`, `step`, `fail`, `clause`, `driver`, `as`, `expect`, `refuse`, backend loop, `TL_DEMO_BACKENDS`, Postgres create/drop). `just demo P2-I3` runs `bash dev/demos/P2-I3.sh` (no justfile change).
- Commands that exist: `tl admin user add`, `tl admin roles grant USER --project P123|company --module materials --role user|superuser --reason R`, `tl standards load FILE`, `tl load loaders|open|extract|profile|plan|load|reconcile` (`--company`, `--loader mat-items|mat-locations|mat-po-lines`), `tl mat item|loc|po|stock|lot|movements|report|move|item-projects`, `tl mat receipt receive|inspect|accept|reject|void|list|show`, `tl mat mto list|show|assign`, `tl derive schema register|open|content|start|worker|show|publish --apply`, `tl doc register|rev create|rendition add|rev issue`, `tl file put` (slot `mtr`). Verb options: run `tl mat <verb> --help`.
- Not commands (the driver does these through the in-process API test client as a named person, as `p2_w0_demo.py` does): `DefineItem`, `DefineLocation`, the CreateCwp of clause 6 (`tl_mod_awp.commands.CreateCwp`, handler `handle_create_cwp`), clause 4's refused issue without a cost code, clauses 8 and 9, the TUI screens (`TlApp` with an `EmbeddedClient`, 170x40, text of the screen compared with the API rows), MCP (`propose_reservation` via the test harness `packages/tl-mcp/tests/mcp_harness.py` pattern, see `dev/accept/P2-I3/T07.py`).
- People: `ada` (admin), `mara` (company materials superuser: `roles grant mara --project company --module materials --role superuser`), `pete` (project user, materials `user` on P123), `sue` (project superuser on P123, `--role superuser`), `plain` (no grant). Passwords as `P2-W0.sh` (`a long passphrase for <name>`).

## Context (read these, nothing else)
- `dev/demos/P2-W0.sh` (shape), `dev/demos/p2_w0_demo.py` (driver shape; modes by first argument; `PASS clause N: ...` / `FAIL`)
- `dev/accept/P2-I3/S3.py` (receipt, accept, issue, transfer, return, adjust, reserve flows and the World helper), `S4.py` (the derived `mto` publish, compensation, republish: the schema code, CSV text and the calls), `T05c.py` (accounts and role grants), `T07.py` (MCP), `T06b.py` (TUI screen on `TlApp` over `EmbeddedClient`)
- `docs/tickets/P2-I3/text-contracts.md` (only to read what a screen shows at 170 columns)
may explore: the report of a ticket named above (`docs/reports/P2-I3/<id>.md`) for a command's exact output text; `packages/tl-modules/materials/src/tl_mod_materials/errors.py` for the fixed refusal messages.

## Allowed paths
- `dev/demos/P2-I3.sh` (create), `dev/demos/p2_i3_demo.py` (create)
- `dev/accept/P2-I3/T08.py` (create: runs the demo on SQLite only, `TL_DEMO_BACKENDS=sqlite`, and checks its last line), `docs/reports/P2-I3/T08.md` (create)
No change to any source under `packages/`. A fixed message you need that is not in `errors.py` or a report: stop and write *Blocked*.

## Steps
1. Driver modes, one per non-command clause group (`clause1-people`, `clause2`, `clause4`, `clause6`, `clause8`, `clause9`, `clause10-11`); each prints `PASS clause N: <what>` per check and `FAIL <what>` + exit 1 on a miss. TUI checks: the screen text contains the numbers the API returned (stock on hand, receipt number, MTO line key), at 170 columns; no pixel checks.
2. Clause 6: if `tl_mod_awp` imports, create `P123-CWP-PIP-0001` with `CreateCwp` through the awp handler/API and print `CWP via awp`; if it does not import, append the record as `S4.py` does and print `CWP appended (awp not on this tree)`. The C4 run must print the first form (the report says which one ran).
3. Clause 9: four refusals of one `tl mat move issue` or `receipt receive` quantity (`١٢` Arabic-Indic digits, `-1`, `1.2345`, over `limits` bound) each with the fixed message text read from the CLI output (copy it into the script as the expected text).
4. `T08.py` runs `TL_DEMO_BACKENDS=sqlite bash dev/demos/P2-I3.sh` and asserts the `PASS clause 1` ... `PASS clause 11` lines and the final `P2-I3 demo OK on: sqlite` line.

## Acceptance (run once; no pytest)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
just check
uv run python dev/accept/P2-I3/T08.py
just demo P2-I3
```
Expected: `just check` clean; `T08.py` exit 0; `just demo P2-I3` prints `PASS clause 1` to `PASS clause 11` twice (sqlite, postgres), ends `P2-I3 demo OK on: sqlite postgres`, exit 0. Postgres down (exit 3 style failure) is a failure to report, not a skip: run `just dev up` per `P2-W0.sh` notes.

## Tests to add
None under `tests/` (T11). The demo is the acceptance.

## Report requirements
Standard report (`docs/templates/haiku-report.md`, ≤ 60 lines): deviations first; the `PASS clause` lines of both adapters (11 + 11, one line each, compact), the clause 6 path that ran, any message copied from the CLI. The diff is over the 400-line trigger by nature (shell + driver): accepted (D46). Commit subjects `P2-I3-T08: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if a clause cannot pass without a source change (say which, with the failing command and its output, at most 8 lines): do not edit `packages/`, do not weaken a clause, do not skip a backend.
- A command in a clause is refused for a reason that is not the clause's intended refusal: report it, do not change the person's grant to get past it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
