# P2-FORMS CR1 report

Deviations: (1) `modules.py` untouched: `OWN_CLASS_TYPES` is a frozenset in `confidentiality.py` (spec's suggested name); the
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

## Open questions (4)
- **Q1 (security, needs an owner decision):** after `SubmitForm` the class rules govern the author too, and the submit unit reads the
  record back as its author (`handle_transition_workflow` `_load`). A person who may not read the template's `answer_class` (restricted
  for a user, any privileged: no clearance table exists) cannot finish a submit (RecordNotFound), though a draft saves. Options: S3
  handlers run the move under `system_view`, or the author reads their own submissions. Tests build such records with the handler
  under `system_view` (`as_system`).
- **Q2:** `propose()` reads its proposal back as the proposer, so an agent proposing for a restricted template gets
  `ProposalNotFoundError` and the proposal rolls back. Consistent with hidden == missing; the tests seed under `system_view`.
- **Q3 (LO, `nested.py`, not mine):** a stored key the command does not know (`{MARKER: 1}`) is echoed in `str(ValidationError)`
  through `loc`; values are not. The accept path is safe (fixed text). Fix: wrap `model_validate` in `run_nested_command` and raise
  `NestedCommandError`. Untested here for that reason; no test was weakened.
- **Q5:** `gate-pg` of `tests/confidentiality` needs a long slot (or the twin walks run alone on Postgres, base against this branch).
- **Q4:** `answer_class` privileged on a submission with a subject hides it from everyone (forms declares no clearance table).
