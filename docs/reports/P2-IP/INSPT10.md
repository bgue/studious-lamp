# Report — P2-INSP-T10

Branch: `p2/insp-t10-terminal`   Commit(s): the single report commit on the branch (sha in the return message)

## Deviations
- Stopped before writing code. No source, test or pin file changed. Only this report is added, under the dispatch's path `docs/reports/P2-IP/INSPT10.md`, not the ticket's `docs/reports/P2-INSP/...`.
- Commit subject is `P2-IP-INSPT10: ...` as the dispatch names it, not the ticket's `P2-INSP-T10: ...`.
- Base is `229bc67b` per the dispatch, not `p2/ip-r3` as the ticket says. The dispatch says it supersedes.

## Changed files
- `docs/reports/P2-IP/INSPT10.md` — this report (new).

## Commands and output
The Acceptance commands were not run. They test code that does not exist yet on this branch, so a run would prove nothing. The read-only checks below confirm the blocking fact.
```
$ grep -n "answers" packages/tl-modules/quality/src/tl_mod_quality/handlers/inspection.py
  (stored answers are the command's `answers` list, `{q, value, note}`; see Blocked)
$ grep -n "class InspectionDetail" -A 18 packages/tl-modules/quality/src/tl_mod_quality/insp_views.py
  (fields: row, checklist_key, checklist_version, answers: list[dict[str, Any]], note, done_at, recorded_by, verified_by, verified_on, reinspection_of_key, cancel_reason, punch_keys, version; no questions)
$ grep -n "fail" packages/tl-tui/tests/fakes_insp.py
  (no failed answer is seeded; every seeded detail has answers=[])
```

## Tests added
none (blocked before any test was written).

## Learnings (proposed)
- The ticket's Result section says "failed answers are the dicts of `detail.answers` whose result is `fail`". The stored answer dict is `{q, value, note}`. It has no `result` field. Failure is decided by `insp_rules._fails(question, value)`, which needs the checklist question (`fails_when`, `kind`, `min`, `max`). The question text is the other field a failed line needs. Neither is on `InspectionDetail`. A future ticket should either add the checklist questions to the detail or pass them to `inspection_page`.

## Open questions / Blocked
**Blocked: the Result section cannot be built from the ticket's interface.**

The ticket's `inspection_page(detail, labels=None, technical=False, panel=False)` takes only `InspectionDetail`. The spec requires the Result section to list, for each failed answer, its question text and note, and never an index or id.
- `InspectionDetail.answers` holds `{q, value, note}` only. The `q` field is a question id.
- `InspectionDetail` carries `checklist_key` and `checklist_version`, but not the checklist's questions. `get_checklist` is a separate read.
- Whether an answer fails needs the question's `fails_when`, `kind`, `min` and `max` (`insp_rules._fails`). The detail does not carry them.
- The ticket's text "whose result is `fail`" matches no field the code writes.

Question for the supervisor: which of these should T10 do?
1. Keep `inspection_page(detail, ...)` as written, and extend `InspectionDetail` (in `insp_views.py`) with the checklist questions, or with a precomputed failed-answer list (question text and note). That is a change to a Context file outside T10's Allowed paths, and it needs a ticket in its own right.
2. Change `inspection_page` to take the questions as an extra argument, and have `InspectionScreen` call `get_checklist(project, detail.checklist_key)`. That is an interface change; the ticket forbids it.
3. Drop the failed-answer lines from T10 and show only the count of failed answers.

No code was written until this is answered. The ticket's other parts (the log, the screen, the palette glue) do not depend on this question, but they cannot be finished cleanly without a decision here.
