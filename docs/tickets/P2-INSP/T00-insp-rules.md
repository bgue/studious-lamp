# P2-INSP-T00 — Pure inspection rules: validate, failed questions, result

Status: ready (dispatch after INSP S1 is merged to `p2/ip`; the provided test is committed)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, tests
Depends on: S1 (merged: the question shape is documented in the `Checklist` class description)
Branch: `p2/insp-t00-insp-rules`
Worktree: harness-created under `/home/user/wt/insp/t00` (from `p2/ip` head)

## Goal
`tl_mod_quality.insp_rules` holds the rules the handler, the CLI and the checklist runner share, as pure functions over
plain dicts (the JSON the record stores). No database, no clock, no import from `tl_core` or any other module. S2 and
the runner call it; this ticket moves it out of S2 so the builder does not write it.

## Brief references (pasted)
> Question `{id, text, kind, required, unit, min, max, choices, fails_when}`, at most 60. Answer `{q, value, note}`.
> Kinds: `yes_no_na` (value `"yes"|"no"|"na"`), `number` (int or float, not bool), `text` (str), `choice` (a str in
> `choices`). `fails_when`: `"no"` (only `yes_no_na`), `"out_of_range"` (only `number`; needs `min` or `max`), or null.
> The result is computed: `reject` when a required question fails, `conditional` when only a non-required one fails,
> else `accept`. A question that is unanswered, or answered `na`, does not fail.

## Interfaces (final; create exactly these names)
```python
MAX_QUESTIONS = 60; MAX_QUESTION_TEXT = 200; MAX_CHOICES = 8; MAX_ANSWER_TEXT = 1000; MAX_NOTE = 300
def validate_questions(questions: list[dict]) -> list[str]   # problems; [] means publishable
def validate_answers(questions: list[dict], answers: list[dict]) -> list[str]
def failed_questions(questions: list[dict], answers: list[dict]) -> list[str]   # ids, in question order; assumes valid input
def result_of(questions: list[dict], answers: list[dict]) -> Literal["accept", "reject", "conditional"]
```
`validate_questions` problems, each starting `q<id>:` (use `question <n>:` with n the 1-based position when the id is
not `q` plus digits): empty list; more than 60; unknown or missing field; bad id; duplicate id; bad kind; empty or
over-long text; `required` not a bool; `fails_when` on the wrong kind; `out_of_range` without `min` or `max`;
`min` above `max`; `choice` without choices, with more than 8 or with duplicates; `choices` on a non-choice kind is allowed only as null.
`validate_answers` problems start with the question id (`q1: answer required` exactly, for an unanswered required
question; an answer naming an unknown question starts with that id): wrong value type or value (bool is not a number;
number given as a string), choice not in `choices`, text over 1000, note over 300, a repeated answer, an unknown
field in an answer. An out-of-range number is valid (it fails the question, it is not a problem). Never mutate the inputs.

## Context (read these, nothing else)
- `docs/tickets/P2-INSP/provided/T00_test_insp_rules.py` (the test; copy it byte-identical)
- `schema/modules/quality/checklist.yaml` (the class description of the question shape)
may explore: (none)

## Allowed paths
- `packages/tl-modules/quality/src/tl_mod_quality/insp_rules.py` (create)
- `packages/tl-modules/quality/tests/test_insp_rules.py` (create: byte-identical copy)
- `docs/reports/P2-INSP/T00.md` (create)

## Acceptance
```
just check
just gate packages/tl-modules/quality/tests/test_insp_rules.py
```
Expected: all pass, `gate: PASS`.

## Tests to add
The provided test only.

## Report requirements
Standard report; first line: test copy byte-identical or not (phrase 101). Note any rule the provided test did not pin.

## Escalation triggers
- Stop if `schema/modules/quality/checklist.yaml` describes a question field this ticket does not list.
- Stop rather than change a provided test case.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
