# P2-FORMS S3 — Forms commands and the one seam that runs a command inside the caller's unit of work

kind: piece
review: full
branch: p2/forms-s3-commands
worktree: /home/user/wt/forms/s3
Depends on: S1 and S2 merged on `p2/ip` (@f137cca7, APPROVALS lines in). Independent of CR1 (CR1 runs after this piece and edits `module.py` by one line).
Gated: core interface (the seam), security (draft saves are ledger text; numbering at submit), words unchanged (S2 has all eight).
Labels: core, module. Heavy runs: at most 2 at once on the box (16 GB).

## Why
`forms-eval.md` §3 and §8.3; ADR-0031 decisions 5, 11, 13, 16; ADR-0032 decisions 7, 8; plan-check F3 (the seam is S3's) and F14 (drafts).
S3 turns S2's tables into behaviour. Views (T03), routes, CLI, tools, the generator, the form sources (S3s) and the intake commands (S7c)
are written against the command names, messages and the seam fixed here. The S2 report (`docs/reports/P2-FORMS/S2.md`) handed two
questions to this piece; they are answered by D6 and D7 below.

## Decisions this spec makes (record them in the report and in the module `AGENTS.md`)
- **D6 numbering at submit (S2 Q2).** `create_module_record` allocates a key when it creates a record, and a key cannot be changed by
  `UpdateRecord`; but `RecordProjector` does apply `Record.Updated` with `{"key": [null, KEY]}` (`_CHANGEABLE_COLUMNS`), and the
  `Record.Created` key is documented "null until numbering assigns one". So: the first `SaveFormDraft` appends `Record.Created` itself with
  `key: null` (no allocator call, title = the template's title, never an answer) and `Submission.DraftSaved` in one append. `SubmitForm`
  of an existing draft calls `allocate_key` (pattern `forms.Submission`, project scope, `record_id` = the submission, `is_taken` as
  `create_module_record` does) and appends `Record.Updated {key: [null, KEY]}`, `Submission.Submitted` and the `submit` transition in the
  same unit of work. `SubmitForm` with no draft uses `create_module_record(key=None, extra_events=[Submitted])` (the number is taken at
  creation, which is the submit). A resubmit of a Returned submission keeps its number. A discarded draft never takes a number, so the
  sequence stays gap-free. If the ledger refuses a null-key `Record.Created` or a module-written `Record.Updated` key, stop with `122`.
- **D7 scope.** A template lives at `company` scope. A submission lives in a project scope: a command with company scope is refused
  (`MSG_PROJECT`, "a form is filled in a project"); `patterns.yaml` has no company `FRM` block and none is added (owner question Q4 in
  STATE.md: default project only in v1).
- **D8 the seam is closed.** It runs only a module's `ProposableCommand` (`module_proposables()`), never a core command and never
  `TransitionWorkflow`, `DispatchFromThread`, `InvokeAction` or `ChangeSetting`: the intake accept (S7c) and the late delivery (Phase 3)
  name commands from that closed table.
- **D9 template versions.** One record per version. `ReviseFormTemplate` makes version n+1 as a new `Draft` (`supersedes_id` = the old
  record) and refuses a second open Draft in a lineage. Publishing does not retire the predecessor; retiring is its own command.
  A Draft is always clean under `validate_questions` (an incomplete template is not stored): `Edit` and `Draft` run it.
- **D10 who fills what.** `SaveFormDraft` and `SubmitForm` take only a general template (`bound_record_type` null, `intake` null) that is
  `Published`; typed forms go through their typed command (S3s) and a public template is filled at its address (S6). An existing draft may
  still be saved and submitted after its template is `Retired` (the answers pin `(id, version, hash)`); a new draft may not start.
- **D11 order of refusals** (each is checked before the next; every refusal is a fixed text, none carries answer text): 1 scope is a project
  (D7); 2 the subject, when named: `confidentiality.require_visible` (a hidden, absent or other-project subject answers `MSG_UNKNOWN`
  *before any answer is validated*); 3 the template loads and is fillable (D10); 4 the existing submission is the actor's own (else
  `MSG_UNKNOWN`, the same text as an absent id) and in a state the command takes; 5 `expected_version`; 6 the save bound
  (`forms.draft_saves_max`, `MSG_DRAFT_SAVES`); 7 answers: `validate_answers(fields, answers, fmt=..., partial=<save>)`; problems
  join into one `FormAnswersError` whose text lists problem texts of the rules (they name field ids and never repeat an answer value).

## Goal
1. **The seam** `packages/tl-core/src/tl_core/services/nested.py`:
   ```python
   def run_nested_command(uow: UnitOfWork, *, command_type: str, args: Mapping[str, Any], actor: str, scope: str, source: str,
                          causation_id: str | None = None, correlation_id: str | None = None,
                          holds: Callable[[str], bool] | None = None, holder: Holder | None = None) -> CommandResult
   ```
   The shape `accept_proposal` uses (`tl_core/services/proposals.py:838-975`, read it): look the type up in the module proposables (D8;
   `NestedCommandError` with a fixed text for an unknown or core type), build the model from `args` with `actor`, `scope`, `source`,
   `causation_id`, `correlation_id` set by the caller and any `actor`, `actor_roles`, `source` key of `args` ignored (a stored body never
   names its actor), check access as `accept_proposal` does (`access_of` with `holds`; with neither `holds` nor `holder` only a command open
   to any signed-in person; with a `holder` also `require_command_access`), run `handler(uow, command)` **in the caller's unit of
   work** (it opens no unit, commits nothing), return its `CommandResult`. A refusal propagates and the caller's block rolls back. Pure
   addition: `accept_proposal` is not edited.
2. **Commands** `tl_mod_forms/commands.py` (`extra="forbid"`; texts cleaned with `tl_core.text.clean_text`; every model takes
   `expected_version` where it changes a record; copy the punch style, `tl_mod_quality/commands.py`):
   | Command | Word (access) | Does |
   |---|---|---|
   | `DraftFormTemplate` | `forms.template.edit` (user) | company scope; `title` ≤ 200, `format_version` 1 or 2, `fields`, `bound_record_type`, `answer_class`, `intake`, `purpose`, `accepts_as`; `Record.Created` (key `TPL`) + `Template.Created` |
   | `EditFormTemplate` | `forms.template.edit` | Draft only; `changes` of title, fields, answer_class, intake, purpose, accepts_as; `Template.Edited {changes}`; `field_count` follows |
   | `PublishFormTemplate` | `forms.template.publish` (controller) | Draft → Published; re-runs `validate_questions`; `intake: public` also needs `intake_problems` clean; sets `content_hash` (`rules.content_hash`) and `published_on`; `Template.Published` |
   | `ReviseFormTemplate` | `forms.template.edit` | from Published or Retired; new Draft version n+1 copying fields and flags (D9) |
   | `RetireFormTemplate` | `forms.template.publish` | Published or Draft → Retired; `Template.Retired` |
   | `SaveFormDraft` | `forms.submit` (user), offline draft | D6, D10, D11; `draft_id` None starts one; `Submission.DraftSaved` with `save_no`, `answer_class` copied from the template at the first save; draft state Draft or Returned |
   | `DiscardFormDraft` | `forms.submit` | author only; state Draft (not Submitted); `Submission.DraftDiscarded` + the `discard` transition |
   | `SubmitForm` | `forms.submit`, offline draft | D6, D10, D11 with `partial=False`; Draft or Returned (resubmit) or no draft; `Submission.Submitted {submitted_on = server day}` (receipt time is the only time in v1); the `submit` transition |
   | `AcceptFormSubmission` | `forms.review` (controller) | Submitted only; **the actor is not the submission's author** (`MSG_SELF_REVIEW`); `Submission.Accepted {note}` + `accept` |
   | `ReturnFormSubmission` | `forms.review` | as Accept; `note` 1 to 300 required; `Submission.Returned` + `return` |
   | `VoidFormSubmission` | `forms.void` (controller) | Submitted, Accepted or Returned; `reason` 1 to 300; `Submission.Voided` + `void`, and the envelope `Record.Voided` as `VoidPunchItem` does |
   Template commands: a hidden-looks-missing rule does not apply (a template holds no project text); an unknown id is `MSG_UNKNOWN`.
3. **Handlers** `tl_mod_forms/handlers/{common,template,submission,review}.py`, `errors.py`, `guards.py` as the quality module does: every
   state move is a `by_module` transition run in the same unit of work as the module's own event (copy `handlers/common.move`);
   the submission loader answers an id the actor may not read, a draft of another author and an absent id with the one text `MSG_UNKNOWN`.
   Nothing logs, prints or puts an answer value in an exception text, a feed card or an event other than `DraftSaved` and `Submitted`.
4. **Registration** `module.py`: `FORMS_COMMANDS` rows (model, handler, word), `command_words` from them, `offline_drafts={SUBMISSION:
   frozenset({"SaveFormDraft", "SubmitForm"})}` (both carry `user`), `PROPOSABLE = (ProposableCommand("propose_form_submission",
   SubmitForm, handle_submit_form, "user"),)`; generic commands none (the record fields and state change only through these commands:
   copy the `generic_commands`/`generic_guards` idea of `PUNCH_GENERIC_COMMANDS`, allowing `SetPsetValues`, `AddLink`, `AttachFile`
   and the link life only on a Submitted-or-later submission). If a test requires every `agent_tool` proposable to have an MCP tool,
   set `agent_tool=False` and say so in the report (T06 flips it). `tests/tools/proposable_exclusions.toml`: one `person acts directly` or
   `act:` line for each of the other ten commands.
5. **Words and settings** are S2's; nothing is added. The draft bound reads `forms.draft_saves_max` through the settings resolver
   (`tl_core.settings.resolver.value_of`, scope of the submission).
6. **Docs**: module `README.md` and `AGENTS.md` gain the commands, the messages table, D6 to D11. No other docs (T12).

## Allowed paths
- `packages/tl-core/src/tl_core/services/nested.py` (create); `packages/tl-core/tests/test_nested_commands.py` (create)
- `packages/tl-modules/forms/src/tl_mod_forms/{commands.py,errors.py,guards.py,module.py,names.py}`, `.../handlers/**` (create or edit as listed)
- `packages/tl-modules/forms/{README.md,AGENTS.md}`; `packages/tl-modules/forms/tests/**` (the existing `test_module_spec.py` is edited: it asserts no commands today)
- `tests/tools/proposable_exclusions.toml` (ten lines)
- Pinned lists, each named in the report with old and new count, only where they fail because the commands or the proposable row now exist
  (candidates: `tests/services/test_modules.py`, `tests/services/test_modules_offline.py`, `packages/tl-mcp/tests/test_mcp_server.py`,
  `packages/tl-api/tests/test_auth_review.py`)
- `docs/reports/P2-FORMS/S3.md` (create)
Not allowed: `tl_core/confidentiality.py` (CR1), `tl_core/modules.py`, `tl_core/services/proposals.py`, `tl_core/forms/**` (S1), `schema/**`, any other
module, `tl_api`, `tl_cli`, `tl_mcp`, `tl_tui`, `tl_web`. A change in `tl_core` beyond `nested.py` is an escalation (README).

## Tests to add
Lint-clean where they land (`ruff format`, `ruff check`, strict `pyright` run over `tests/` by `just check`: a deliberately wrong-typed call
needs a `# pyright: ignore[...]`). Any statement-count assertion ignores `BEGIN`, `COMMIT` and `ROLLBACK`. Commands run as a person would,
in the style of `packages/tl-modules/quality/tests/punch_world.py` (access word first, then the handler as that person's viewer, one unit each).
- `test_nested_commands.py` (core): a proposable module command runs in the caller's unit and an earlier append of the same unit is rolled back
  with it when the command is refused; core command types, `TransitionWorkflow`, `DispatchFromThread`, `InvokeAction`, `ChangeSetting` and an
  unknown name are refused with the one fixed text; `args` naming `actor` or `source` cannot impersonate (the events carry the caller's);
  without `holds` and `holder` a `controller` command is refused and a `user` command runs; causation and correlation reach the events.
- `test_template_commands.py`: draft, edit, publish (hash equals `rules.content_hash`), revise (version n+1, one open Draft), retire; an unclean
  field list is refused at draft, edit and publish; an `intake: public` template with nine fields or a `visible_when` is refused at publish;
  the fixtures of S2 draft and publish; workflow moves refuse Retired → Published.
- `test_submission_commands.py`: save twice (`draft_saves` 2, key null, no `Numbering.Allocated`), resume by `draft_id`, submit (key `P123-FRM-0001`,
  one allocation, `Record.Updated` key event, state Submitted); submit with no draft; discard then submit another (the next key is
  `FRM-0001`: a discarded draft took no number); return then resubmit keeps the number; the save bound (`forms.draft_saves_max` set to 2: the
  third save refused); bound and public templates refused (D10); a retired template: new draft refused, existing draft submits; company scope refused.
- `test_submission_security.py`: a hidden subject (restricted record, viewer at the lowest clearance) answers the same text and status
  as an absent subject and the answers are never validated (answers that would fail validation give no answer problem); another person's
  draft: save, discard, submit and accept all answer `MSG_UNKNOWN`; no exception text contains a marker value placed in an answer;
  hostile answers (60 fields with 1000-character text, a 3-deep `visible_when` chain, unknown ids) are refused or bounded without error text echo;
  the proposal row of `propose_form_submission` accepted by a person submits as that person (the author is the accepter).
- `test_review_commands.py`: accept and return by a controller who is not the author; the author is refused (`MSG_SELF_REVIEW`) even as a
  controller; a user holds no `forms.review`; void from the three states and refused from Draft; transitions are by_module only.
- `test_module_spec.py` (edited) and `test_exclusions.py` (as `quality/tests/test_exclusions.py`): eleven commands, every one a row or an exclusion,
  offline drafts, the one proposable row.
- The five-reader walk of drafts is T10, not here; the confidentiality rows are CR1. Say in the report which of your tests would change with them.

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); then one run at a time:
1. `just gate packages/tl-core/tests/test_nested_commands.py tests/services/test_rule_proposals.py tests/integration/test_int_actions.py`
2. `just gate packages/tl-modules/forms/tests`
3. `just gate tests/services/test_modules.py tests/services/test_modules_offline.py packages/tl-core/tests/test_numbering_config.py`
4. `just gate packages/tl-mcp/tests/test_mcp_server.py packages/tl-api/tests/test_auth_review.py` (only if the proposable row changed them)
`just gate-pg packages/tl-modules/forms/tests packages/tl-core/tests/test_nested_commands.py`. Existing paths were checked with `ls` on `p2/ip`
@f137cca7; every `forms/tests/test_*` file named above except `test_module_spec.py`, `test_projectors.py` and `test_intake_body_operational.py`
is created by this piece.

## Mutation cap
One sentinel plus at most 5 targeted mutants: the reviewer-is-not-submitter check removed; the hidden-subject check moved after answer validation;
a draft of another author readable (ownership check removed in the loader); `allocate_key` called on the first save; the seam accepts a core
command. 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines at `docs/reports/P2-FORMS/S3.md`; first line deviations or none. List: the final command table
(names, words, messages), the seam signature, every pinned file with old and new count, D6 to D11 as applied, and **one line on where the
stored command of a proposal can be read** (`cur_proposals.command_json` holds the answers of an agent's submission: say which readers
filter it today; a gap is a finding for the wave review, not a change here). Commit `P2-FORMS-S3: ...` with the session trailers; no model
names in committed text.
