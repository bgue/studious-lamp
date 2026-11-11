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
- Each command in `REQUISITIONS_COMMANDS` names one access word that exists in `schema/settings/access-words.yaml`. A new word is a schema change (human gate).
- The only proposable command is `propose_requisition` (`PROPOSABLE`). Every other command is listed with its reason in `tests/tools/proposable_exclusions.toml`; an agent never approves, rejects, schedules, assigns, starts, completes or closes.
- Other modules read this module through `api.py` only (`open_requisitions_for`, `work_order_for`). Never import a handler from another module.
- The general requisition type is a code-list value of `GeneralRequisitionType` (`tl-mod-engineering`); a new type is data, not code.
