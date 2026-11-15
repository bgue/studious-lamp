# P2-FORMS CR1 report

Deviations: (0) later rulings, see the end. (1) `modules.py` untouched: `OWN_CLASS_TYPES` is a frozenset in `confidentiality.py` (spec's suggested name); the
module declares the source, core names the type. (2) Author exemption added: a draft is its author's whatever its class
(`_own_draft`), else an author could not save a restricted draft again. (3) Feed cards: the rule is by stream
(`cards.is_draft_plumbing`), not by adding forms events to `POLICY_EVENT_TYPES`, so the pinned awp test is unchanged. (4) Gate
run 2 fails on `tests/contract/test_webhook_catalog_contract.py`, and failed the same on the base with my changes stashed: the
scenario lacks the permits, checklist and forms events (T14 not merged at this base). Not a draft event of mine; no `122`.

## Final names
- Rows (`SUBJECT_LINKS`, one block `# forms (P2-FORMS CR1)`): `forms.Submission` (`subject_id`), `forms.IntakeItem` (`code_id`),
  `forms.IntakeCode` (`context_id`); `_HOPS` stays 2. Source: `tl_mod_forms/confidential.py` `CONFIDENTIAL`, one line in `module.py`.
- Own class: `OWN_CLASS_TYPES = {forms.Submission}`; an extra flat part `_own_hidden` per source that holds such a type, and the
  source part skips `hr.id = rr.id` author drafts. Actor parameter `ACTOR_PARAM = "_cf_actor"`, bound by `params_for` only when the
  SQL names it; a viewer with no `account` (default, agent) binds nothing and every draft is hidden from it.
- Draft rule: `_draft_parts`: the draft itself, and a record whose governing subject is a draft. `system` hides nothing (docstring).
- New: `hidden_answer_templates(conn, ids, viewer)`; used by `proposals._readable` (list, get, `_pending`, so accept, reject, fail)
  and by `names_hidden_record` for `core.Proposal` (so `filter_events`, `hidden_row_ids`, webhooks, streams).
- Join count: at most 22 JOINs in one part (14 parts), asserted below 64; `EXPLAIN` and the statement run on both adapters.
- Pinned lists: none changed. Tests edited only because the rows exist: `forms/tests/test_module_spec.py` (no-declaration test now
  asserts the one source), `forms/tests/test_review_commands.py` (a draft is read as its author).

## Goal 3 paths (proved in `test_visibility.py`, `test_forms_rows.py`)
`require_visible`, `is_hidden`: proved. `visible_rows` (filter before LIMIT, page of 5 over 8 with 3 drafts): proved. `record_history`,
`get_record_by_id`, `list_records`: proved. `hidden_event_streams`, `hidden_row_ids`, `filter_events`: proved. links (`links_of`): proved
for a hidden subject. Feed: a draft and a discard make no card; the submit card has no answer text. Search: not reached (no forms search).
Amendment: proposals list, get, API `/proposals`, CLI `tl proposal ls|show`, `Proposal.Created` events: proved, five readers.
Seam (S3 F1): value-bearing refusals do not echo; the accept path stores a fixed sentence (proved).

## Gate (`.gate/summary.txt`)
`just check` rc 0 (old pyright warning in `twin_channels.py`). Run 1 `tests/confidentiality`: 141 passed, 4 xfailed (old), PASS.
Run 2 (forms tests, punch visibility, webhook contract): 137 passed, 1 failed (pre-existing, above). Run 3: 68 passed. Proposals: 50 passed.
`gate-pg` did NOT complete: run 1 exit 137 (OOM, after about 2h), rerun stalled at the same test,
`tests/confidentiality/test_twin_walk.py::test_twin_walk[postgres-amy]` (the first Postgres twin walk; 256 tests before it passed on both
adapters, including `test_paths_equal_old` and every `test_forms_rows` and `test_core` test). Run directly, not through the gate, with
`--adapters sqlite,postgres`: `packages/tl-modules/forms/tests`, `test_forms_rows.py`, `test_core.py`: 303 passed (incl. `test_visibility.py`).
Cost seen on Postgres: planning the link query (`hidden_event_streams`) 132 ms against 108 ms with the old rows (join budget test
holds). Not measured: the twin walks on the base, so a slow-down or a pre-existing slowness is not told apart (open question Q5).

## Mutation
Sentinel (`hidden_sql` returns None for everyone) killed. 5/5 targeted killed: answer-class check skipped in list; in get; in the
event filter; draft card made (`is_draft_plumbing` off); `forms.Submission` row removed (killed by the pin and by two behaviour tests).

## Rulings applied (coordinator)
- Q1: the author always reads their own submission, draft or submitted, whatever its class (`_own_draft` now tests the author only,
  in the source part and `_own_hidden`; a hidden subject still hides it). Test: a plain user completes `SubmitForm` for a restricted and
  a privileged template and reads it back; other readers see it as missing. The `as_system` helper stays for one test only.
- Q2: accepted as is (hidden == missing; tests seed proposals under `system_view`).
- Q3: `run_nested_command` catches `ValidationError` and raises `NestedCommandError` with the fixed `MSG_ARGS`; test with an unknown key
  marker and value markers. (`nested.py` added to the touched files by ruling.)
- Q4 (deferred): a privileged answer class on a submission with a subject hides it from everyone but its author until forms has a
  clearance table; the orchestrator logs it.
- Q5 stands (Postgres twin walks; PID 8782 still alive, `gate-pg` not run).

## Review round (security review: changes)
- F1: `insights/activity.py` `_visible` also drops `core.Proposal` events that hit `hidden_answer_templates` (same helper). Other
  hand-written filters: `integration/visibility.py` and `webhooks/dispatch.py` use `names_hidden_record` (covered);
  `threads/queries.py` scans `dispatch_json` of core thread commands only, not a forms proposal. Tests with a subject: service
  `record_activity` and `GET /records/{id}/activity` (an agent gets 403), five readers.
- F3: test: a plain user files on an internal item, a controller reclassifies it restricted, the author then gets never-existed.
- F4 mutants, all killed: author check removed; `submitted_on IS NOT NULL`; own class skipped; filter after LIMIT; activity check removed.
- F5: `hidden_answer_templates` names the template columns (`_TEMPLATE_ID`, `_TEMPLATE_CLASS`).
- F2 gates: `tests/confidentiality` 144 passed, 4 xfailed; forms 120; proposals 50; punch visibility 13; API walk 41; MCP walk + `test_modules` 27.
