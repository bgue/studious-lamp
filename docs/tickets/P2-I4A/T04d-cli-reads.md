# P2-I4A-T04d — CLI reads: `tl req ls|show`, `tl wo ls|show`

Status: staged (dispatch after T04a and T04e1 merge)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, read
Depends on: T04a, T04e1
Branch: `p2/i4a-t04d-cli-reads`
Worktree: harness-created under `/home/user/wt/i4a/t04d` (from `p2/i4a` head)

## Goal
Read verbs on the two groups T04e1 created. Output is one fact per line, two spaces between fields, `-` for none (print keys, never labels or ids: L-P2-I3-3). Reads open `open_uow(db, readonly=True)`, pass `viewer=session_viewer(db)` (`tl_cli.session`), and first require the word `requisitions.view` for the actor on the project scope as `constraint_read.require_view` does. Never print a URL or a traceback.

## Brief references (pasted)
> - `req ls [--kind K] [--state S] [--requester user:X] [--for IWPNUMBER] [--limit N]` -> `requisitions: <n>` then `<key>  <kind>  <state>  <priority>  <need_by|->  <requester>  <subject cut 50>`; filters pass to `views.requisition_list`. `--for` resolves the IWP number by key; unknown prints `error: no record <number>` (exit 1).
> - `req show KEY` -> `requisition <key>`, `kind`, `state`, `subject`, `priority`, `need by`, `requester`, `approved by`, `serves <IWP key|->`, then the kind fields as `  <name>  <value>` in sorted order, `work order <key|->`. Missing or hidden: `error: no requisition <key>` (exit 1).
> - `wo ls [--state S] [--assigned user:X] [--limit N]` -> `work orders: <n>` then `<key>  <work_kind>  <state>  <assigned|->  <planned_start|->  <planned_finish|->  <hours_planned|->`.
> - `wo show KEY` -> `work order <key>`, `requisition <key>`, `kind`, `state`, `assigned`, `planned <start> to <finish>`, `actual <start> to <finish>`, `hours <planned> planned  <actual> actual`. Missing or hidden: `error: no work order <key>`.
> The `serves` key and the requisition key of a work order are read through the views (the viewer filter has already run); never a second query.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/{req.py, req_write.py}` (T04e1), `awp_iwp_read.py` and `constraint_read.py` (pattern and `require_view`), `session.py`
- `docs/reports/P2-I4A/T04a.md`, `docs/reports/P2-I4A/T04e1.md`

## Allowed paths
- `packages/tl-cli/src/tl_cli/req_read.py` (create: `register(req_app, wo_app)`), `packages/tl-cli/src/tl_cli/req.py` (one import and one `register` call)
- `packages/tl-cli/tests/test_req_read.py` (create), `docs/reports/P2-I4A/T04d.md` (create)

## Acceptance
```
just check
just gate packages/tl-cli/tests/test_req_read.py packages/tl-cli/tests/test_req_write.py
```

## Tests to add
`packages/tl-cli/tests/test_req_read.py`: ledger built by commands (module `req_world.py` helper loaded by path; no projection writes). `req ls` count equals the data lines and order is by key; each filter narrows; `req show` lines for a labour and a general requisition; `wo ls` and `wo show` after approve and schedule; unknown key and a key of another project print byte-identical errors; an actor without `requisitions.view` is refused before any SELECT (count statements with a `before_cursor_execute` listener); no output holds a 32-hex id or `Traceback`.

## Escalation triggers
- A field a verb prints is not on the T04a dataclasses (write which); `req.py` differs from the T04e1 report.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4A-T04d: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
D-r3d (orchestrator, 2026-11-11, after attempt 1 blocked): option (b). `req show` may make ONE keyed lookup of `for_record_id` (the record's key through the existing core record read the CLI already uses, e.g. `get_record_by_id`) to print the serves key; a missing or unreadable record prints `-` (a requisition already inherits its subject's class, so a hidden IWP means a hidden requisition). No other second query; no change to the module views.
