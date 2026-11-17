# P2-FORMS-T09 — Demo project section `forms`: general templates and submissions

Status: ready
Tier: haiku
Kind: ticket
Review: full  (the section runs real commands as roster people; pins move)
Labels: tests, docs
Depends on: S3, CR1 merged (commands, rows); S7c merged is not needed (no intake in this section)
Branch: `p2/forms-t09-demo-forms`
Worktree: harness-created under `/home/user/wt/forms/t09` (from `p2/ip` head)

## Goal
The demo project P200 gains a `forms` section (`dev/seed/demo_project/forms.py`, registered after `quality`): three published general templates and fourteen submissions in every state, all made through the real handlers as roster people, each command read through its actor's own viewer (ADR-0016).
The generator reads nothing from the clock and draws only from its own `rng`; one seed gives one ledger. No intake rows: intake needs the public route (S6) and its own section later.

## Brief references (pasted)
Section pattern: `dev/seed/demo_project/quality.py` (module docstring, `_run(world, actor, day, handler, Command, **fields)`, `register("quality", build, needs=("quality.PunchItem",))`, `world.on(day)`, `actor_of`, `use_viewer(viewer_for_actor(...))`).
Templates: the fixture YAML files `schema/fixtures/forms/templates/{toolbox-talk,pre-use-check,job-hazard-assessment}.yaml` give `title`, `format_version`, `answer_class`, `fields`; each is passed to `DraftFormTemplate` (title, fields, answer_class where the command takes it: read `commands.py`), then `PublishFormTemplate`.
Commands and handlers (`tl_mod_forms.commands`, `tl_mod_forms.handlers.*`; `FORMS_COMMANDS` in `module.py` names each handler): `DraftFormTemplate`, `PublishFormTemplate`, `SaveFormDraft`, `SubmitForm`, `DiscardFormDraft`, `AcceptFormSubmission`, `ReturnFormSubmission`, `VoidFormSubmission`.
Rules: submissions are project scope (`PROJECT` of `world`); the reviewer is never the submitter (`MSG_SELF_REVIEW`); a draft is its author's alone; `forms.template.publish`, `forms.review`, `forms.void` are controller words, `forms.submit` a user word (`schema/settings/access-words.yaml`).
Final states by position (`FINAL`, a tuple in the module, the same style as quality): 14 submissions = 4 Submitted, 4 Accepted, 2 Returned, 1 Voided, 2 Draft (never submitted), 1 Discarded. Spread over three templates (6 toolbox talks, 5 pre-use checks, 3 hazard assessments), dates on the project calendar (`world.on(day)`, days before `TODAY`), answers valid for the template (build each from the fields: yes/no/na `yes` mostly,
one `no` with a note on two pre-use checks, numbers inside the range, texts from a short fixed list in the module; no photo fields are in these three templates).
Roster: pick people from `dev/seed/demo_project/core.py`: one controller (publishes, accepts, returns, voids), three users who submit; name the choice in the module docstring.

## Interfaces
```python
# dev/seed/demo_project/forms.py (create)
def build(world: World, rng: random.Random) -> None
register("forms", build, needs=("forms.Template", "forms.Submission"))
```
`dev/seed/demo_project/registry.py`: add `"forms"` to `ORDER` after `"quality"` (one line; nothing else), and `dev/seed/demo_project/__init__.py` imports the module the way the others are imported (one name).
The section's summary line follows the others (rows per type); a run with the module `forms` not installed prints the one-line skip note the other sections print (copy how `needs` is used) and changes nothing else.

## Context (read these, nothing else)
- `dev/seed/demo_project/quality.py` (whole; the pattern), `dev/seed/demo_project/registry.py`, `dev/seed/demo_project/world.py` (`World`, `actor_of`, `on`)
- `packages/tl-modules/forms/src/tl_mod_forms/commands.py` (fields of the eight commands), `packages/tl-modules/forms/src/tl_mod_forms/module.py` (`FORMS_COMMANDS`)
- `tests/tools/test_demo_project_quality.py` (test pattern: child process runs; read its docstring)
may explore: `dev/seed/demo_project/core.py` (roster), `tests/tools/test_demo_project.py` (the pinned section list and totals)

## Allowed paths
- `dev/seed/demo_project/forms.py` (create); `dev/seed/demo_project/registry.py` (the `ORDER` line); `dev/seed/demo_project/__init__.py` (the import name)
- `tests/tools/test_demo_project_forms.py` (create)
- Consequential pins, each listed in the report with old and new value: `tests/tools/test_demo_project*.py` (section lists, totals, event counts that move because the section exists), `docs/` pages that list the demo sections only if a test pins them
- `docs/reports/P2-FORMS/T09.md` (create)
Not allowed: any `packages/**` file, `schema/**`, the `data/` fixtures of the generator, another section's file, a dependency.

## Tests to add (`test_demo_project_forms.py`; lint-clean under `ruff format`, `ruff check`, strict `pyright`; child-process runs like the quality test: build once per module scope)
- The section on its own sources (`core` plus what it needs): 3 templates Published; 14 submissions by state exactly as `FINAL`; every Accepted or Returned submission has a reviewer who is not its author; Voided has a reason; the two drafts have `key` null and `submitted_on` null; keys of submitted ones are unique.
- Same seed twice gives the same ledger (hash of ordered events equals); the same run without `forms` leaves every other type's row count unchanged.
- A viewer test: read through `tl_mod_forms.views` is T03's, not available here; query `cur_forms_submission` with `tl_core.confidentiality` `not_hidden` for the default (lowest) viewer: no draft and no discarded submission is visible to it, and every other row of the 14 is (11 rows). If the real number differs, report the number and the rule; do not bend the data.
- No event payload of the section holds a person's password or token (scan the section's events for the words `password`, `token`).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate tests/tools/test_demo_project_forms.py
just gate tests/tools/test_demo_project.py tests/tools/test_demo_project_quality.py
```
Expected: all pass, `gate: PASS`. (Child-process runs are heavy: one gate run at a time; the second line may exceed 10 minutes: split per file and name the halves.)

## Report requirements
Standard report; first line deviations or none; the final row counts by type and state; every pinned test changed with old and new numbers.

## Escalation triggers
- A command refuses valid-looking input as the chosen roster person (report the refusal text; do not widen a role).
- A pin outside `tests/tools/test_demo_project*.py` fails.
- The section would change another section's output (the other types must not move).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
