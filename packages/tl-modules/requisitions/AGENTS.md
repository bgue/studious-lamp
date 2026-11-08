# AGENTS.md — tl-mod-requisitions

Read the repository `AGENTS.md` first. These rules add to it and never relax it.

## Nevers
- Never change an event or a row in place. Corrections are new events (AGENTS.md rule 3).
- Never put SQLite- or Postgres-specific SQL in this package (repository rule 5).
- Never move a requisition past Approved by a command of its own: after approval the requisition follows its work order.
- Never read a requisition or work order without the viewer's class filter (ADR-0016); the confidentiality subject is `for_record_id`.

## Conventions
- A requisition's events are on its own stream; a work order's on the work order's, with `requisition_id` in every payload.
- Every event payload tags `at` with `tl:valid_time`; do not add classes to `tests/tools/valid_time_baseline.toml`.
