# Increment P0-I1 — Foundations (ticket folder)

Seed plan: `docs/build-spec/05-phase0-plan.md` §Increment 1. The supervisor expands it into
`docs/tickets/P0-I1/README.md` using `docs/templates/sonnet-increment.md` (replace this file).

Worked example tickets in this folder show the expected level of detail:

| File | Ticket | Why it is an example |
|---|---|---|
| `T01-monorepo-scaffold.md` | Scaffold | Pure file-list work; shows how precise *Allowed paths* and *Acceptance* must be |
| `T05-ledger-types-and-hashing.md` | Types + hash | Interface transcription with test vectors; no design freedom |
| `T06-sqlite-ledger-adapter.md` | Adapter | Implementer against a Protocol with a supervisor-provided failing test file |
| `T10-tl-cli.md` | CLI | Thin layer over services; shows the "no logic here" rule and an e2e acceptance |

Tickets T02, T04b, T07 are supervisor-built and have no implementer ticket file; the supervisor records them in the plan's "Supervisor-built pieces" table.
