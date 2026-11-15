# P2-FORMS CR1 — Confidentiality rows for forms: subjects, the answer class and the author-only draft

kind: piece
review: full
branch: p2/forms-cr1-conf-rows
worktree: /home/user/wt/forms/cr1
Depends on: S2 merged (tables and columns), S3 merged first (both pieces touch `tl_mod_forms/module.py`; S3 owns it, CR1 adds one line).
Serialised owner (plan-check F8): CR1 is the only forms piece that edits `tl_core/confidentiality.py`. Before dispatch the orchestrator confirms that
no other piece with that file in its Allowed paths (QR, INSP, PTW rows) is in flight, and the builder starts with `git merge p2/ip`.
Gated: security (APPROVALS line, the owner approves: subject rows and the author-only draft rule). Labels: core, security.

## Why
ADR-0031 decision 11 and 13, ADR-0032 decision 6, ADR-0016, `AGENTS.md` ("never read a module record, its history or its events without the
viewer's class filter"). S2 declared no `confidential` source on purpose: no reader existed. S3 makes the first records and T03, T04, T06 the first
readers, so the rows land before any of them. Answers are record text and are hidden through the record's subject; a draft is readable by its
author alone (it is the one record kind whose visibility depends on who asks and not on a class).

## Goal
1. **Subject rows** in `SUBJECT_LINKS` (`tl_core/confidentiality.py`), appended in one block under the comment `# forms (P2-FORMS CR1)`:
   `("forms.Submission", "cur_forms_submission", "id", "subject_id")`, `("forms.IntakeItem", "cur_forms_intake_item", "id", "code_id")`,
   `("forms.IntakeCode", "cur_forms_intake_code", "id", "context_id")`. A submission is hidden when its subject is; an intake item is hidden when its
   code's context is (two hops, item then code then context; `_HOPS` is 2 and stays). A submission whose subject is itself a record that names a
   subject (a punch item) follows the second hop; a deeper chain stops there: document that in the docstring of the block.
2. **The answer class.** `forms.Submission.answer_class` (copied from the template at the first save; null means `internal`) must govern in two cases:
   (a) a submission with no subject is its own subject: it is classed by its own `answer_class`; (b) a submission whose `answer_class` is higher than
   the class of its subject's record is hidden from a viewer who may not read that class, even when the subject is readable. (a) follows from a
   `confidential` declaration in the forms module (`ConfidentialSource(record_types={forms.Submission}, table=cur_forms_submission, id_column=id,
   class_column=answer_class, null_class="internal")`, in `tl_mod_forms/confidential.py`, handed to `spec(confidential=...)`: one line in `module.py`).
   (b) needs one new, small, generic notion in `confidentiality.py`: record types whose own source row is also checked when a subject governs
   (suggested name `OWN_CLASS_TYPES`, a frozenset the module declares through the same `ConfidentialSource` or a new field; the builder chooses, within
   the rules below). The check stays one flat LEFT JOIN per table; no nested subqueries (nesting overflows SQLite's parser stack).
3. **The author-only draft rule.** A `forms.Submission` whose row has `submitted_on IS NULL` (a draft, kept or discarded) is hidden from every viewer
   except the one whose `actor` is the row's `author`. The viewer's actor reaches the SQL as a bind parameter next to `_cf_acct` (`params_for` supplies
   it; a viewer with no actor, the lowest default and an agent, never matches). The `system` viewer hides nothing, as today: jobs and rebuilds read
   with it, and no reader serves a person through it (say so in the docstring). Once `Submitted` sets `submitted_on` the rule stops and the class rules
   (1 and 2) govern. Hidden means the record answers as one that never existed on every path that uses `hidden_sql`: `require_visible`, `is_hidden`,
   `visible_rows`, links, history, events (`hidden_event_streams`, `filter_events`), feeds and search; the builder proves each path it can reach in a test.
4. **Intake rows with no context.** An `IntakeCode` or `IntakeItem` whose `context_id` is null is its own subject and no source classes it: it is not hidden
   by this module (the controller words guard those reads in S7c and T03). Say so in the module `AGENTS.md` and test it; do not invent a class column.
5. **Join budget.** The three rows add six LEFT JOINs to `_subject_chain`. A test builds `hidden_sql` for a viewer with every installed module's rows and
   prepares it on SQLite and on Postgres (the statement parses; no parser-stack overflow); the join count in a docstring or constant is asserted below SQLite's 64.

## Allowed paths
- `packages/tl-core/src/tl_core/confidentiality.py` (the rows, the own-class notion, the actor parameter, docstrings)
- `packages/tl-core/src/tl_core/modules.py` only if the own-class notion needs a field on `ConfidentialSource` (name the lines in the report)
- `packages/tl-modules/forms/src/tl_mod_forms/confidential.py` (create); `packages/tl-modules/forms/src/tl_mod_forms/module.py` (one line: `confidential=`)
- `packages/tl-modules/forms/{README.md,AGENTS.md}` (the visibility rules)
- `tests/confidentiality/test_forms_rows.py` (create); `packages/tl-modules/forms/tests/test_visibility.py` (create)
- pinned lists, named in the report with old and new count: `tests/confidentiality/test_core.py` (the `SUBJECT_LINKS` pin near line 707) and any test that
  fails only because the rows now exist
- `docs/reports/P2-FORMS/CR1.md` (create)
Not allowed: any other `tl_core` file, `schema/**`, forms commands and handlers (S3), views, routes, CLI, tools.

## Tests to add
Lint-clean where they land (`ruff format`, `ruff check`, strict `pyright` over `tests/`). Any statement-count assertion ignores `BEGIN`, `COMMIT`,
`ROLLBACK`. Records are made through S3's commands and the correspondence module's own confidentiality command, never by a projection write
(style of `packages/tl-modules/quality/tests/punch_world.py`). Readers: the five kinds of `packages/tl-api/tests/test_confidentiality_walk.py`
(anonymous or lowest, a plain user, a restricted-level controller, the draft's author, an agent), plus the system viewer.
- `test_forms_rows.py`: for a submission with a restricted subject: the lowest viewer and an agent do not see the record, its history, its events or its
  link rows and get the text of a record that never existed; a cleared viewer does. A submission with an internal subject and `answer_class` restricted
  is hidden from the lowest viewer (goal 2b) and shown to a cleared one. A submission with no subject and `answer_class` privileged: hidden from the cleared
  viewer without a clearance row. An intake item whose code's context is restricted is hidden; one with a visible context is shown; null context is shown.
  `OWN_CLASS_TYPES` (or its name) holds only `forms.Submission`; an existing module's records are unchanged (the old `SUBJECT_LINKS` rows still pass
  `tests/confidentiality/test_core.py`).
- `test_visibility.py`: a draft is visible to its author only: another user, a controller, an admin, an agent and a viewer with no actor see nothing,
  through `require_visible`, `visible_rows` (the filter runs before LIMIT: a page of 5 over 8 rows with 3 drafts of another author returns the
  remaining visible rows and the count of them), `hidden_event_streams` and the feed; the same row after `SubmitForm` is visible per class; a discarded
  draft stays author-only; a Returned submission is not a draft. The system viewer reads a draft.
- The join budget test of goal 5 on both adapters (SQLite and Postgres via the parity fixture).
- Webhook scenario: after the rows exist, `tests/contract/test_webhook_catalog_contract.py` must still pass (T14 merged, scenario delivers the forms
  events). If it fails because a draft event is no longer delivered, stop with `122` and the failing event; do not remove an event from the scenario.

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); then one run at a time:
1. `just gate tests/confidentiality`
2. `just gate packages/tl-modules/forms/tests packages/tl-modules/quality/tests/test_punch_visibility.py tests/contract/test_webhook_catalog_contract.py`
3. `just gate tests/services/test_modules.py packages/tl-api/tests/test_confidentiality_walk.py packages/tl-mcp/tests/test_confidentiality_walk.py`
`just gate-pg tests/confidentiality packages/tl-modules/forms/tests/test_visibility.py`. Existing paths were checked with `ls` on `p2/ip` at the head
this piece starts from; `test_forms_rows.py`, `test_visibility.py` and `confidential.py` are created here.

## Mutation cap
One sentinel plus at most 5 targeted mutants: the author check removed (any actor reads a draft); the draft test uses `submitted_on IS NOT NULL`;
the Submission row removed from `SUBJECT_LINKS`; the own-class check skipped when a subject governs; the filter applied after LIMIT in `visible_rows`
for forms. 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines at `docs/reports/P2-FORMS/CR1.md`; first line deviations or none; the final names (the three rows, the
own-class notion, the actor parameter), the join count, each pinned file with old and new count, and one line per path of goal 3 you proved or could not
reach. Commit `P2-FORMS-CR1: ...` with the session trailers; no model names in committed text.

## Amendment 1 (orchestrator, 2026-11-15; from the S3 report)
Two more items are CR1's, because CR1 is the one forms piece in `confidentiality.py`:
1. **F-S3a (HI until fixed):** `cur_proposals.command_json` holds an agent-proposed submission's answers. `get_proposal`,
   `list_proposals`, `_pending` (`tl_core/services/proposals.py` ~393-424, 776-785) and the API/CLI/sim surfaces return
   it; the only filter (`_readable`, ~370-390) hides a proposal that names a hidden record id, so a privileged-class
   template with no subject leaks its answers to the lowest viewer (reproduced by the S3 builder). Fix: a viewer who may
   not read the template's answer class sees that proposal as absent (hidden == missing), on every reader and on the
   `Proposal.Created` event filter. Test: five readers, list and get, API and CLI, plus the event stream.
2. **Feed cards:** `feed/cards.py` `POLICY_EVENT_TYPES` ignores `feed_policy: none` for forms events, so a draft save
   shows "created a record". Drafts make no card; a submit card carries no answer text and follows the subject rule.
Allowed paths gain `packages/tl-core/src/tl_core/services/proposals.py` and `packages/tl-core/src/tl_core/feed/cards.py`
for these two items only.
