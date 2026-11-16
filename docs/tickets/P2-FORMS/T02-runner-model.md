# P2-FORMS-T02 — Runner model (pure): one field per step, back, skip, review, confirm

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: core, tests
Depends on: S1 merged (`tl_core.forms.rules`)
Branch: `p2/forms-t02-runner`
Worktree: harness-created under `/home/user/wt/forms/t02` (from `p2/ip` head)

## Goal
`tl_core.forms.runner` is the state machine a terminal or a web fill page drives: it shows one visible field at a time, takes an answer
or a skip, goes back, lists the answers for review and returns the final `answers` list. Pure: no I/O, no clock, no database, inputs never
mutated. The terminal screen (T07) and draft resume (T08) are written over it later; this ticket changes no screen.

## Brief references (pasted)
Answer shape `{q, value, note}`; format 1 answers carry all three keys (`note` may be null); format 2 answers carry `q` and `value`, and `note`
only when text. `validate_answers(fields, answers, *, fmt, partial, intake)` returns problem strings (`"<id>: ..."`); with `partial=True`
required answers may be missing; it refuses an answer for a field that is not shown (`"<id>: question is not shown for these answers"`).
`visible_ids(fields, answers)` returns the ids shown for those answers, in field order.

## Interfaces (the contract of the provided test; write exactly these names)
```python
# packages/tl-core/src/tl_core/forms/runner.py  (create; imports tl_core.forms.rules, dataclasses, collections.abc, typing only)
class RunnerError(ValueError):
    problems: list[str]
    def __init__(self, problems: list[str]) -> None: ...        # str(self) is the problems joined by "; "

@dataclass(frozen=True)
class RunnerState:
    fmt: int                      # 1 or 2
    values: Mapping[str, Any]     # field id -> value, only visible fields
    notes: Mapping[str, str]      # field id -> note text
    at: str | None                # id of the current field; None in review
    phase: str                    # "fill" | "review"

@dataclass(frozen=True)
class Step:   # the current field as the screen shows it
    id: str; text: str; kind: str; required: bool; section: str | None; help: str | None; unit: str | None
    min: float | None; max: float | None; choices: tuple[str, ...]; value: Any; note: str | None
    number: int                   # 1-based position among the visible fields
    total: int                    # count of visible fields now

@dataclass(frozen=True)
class ReviewLine: id: str; text: str; kind: str; value: Any; note: str | None
@dataclass(frozen=True)
class Review: lines: tuple[ReviewLine, ...]; missing: tuple[str, ...]   # visible fields in order; visible required ids with no value

def start(fields, *, fmt: int = 2, answers: Sequence[Mapping[str, Any]] | None = None) -> RunnerState
def step(state, fields) -> Step | None
def answer(state, fields, value: Any, note: str | None = None) -> tuple[RunnerState, list[str]]
def skip(state, fields) -> tuple[RunnerState, list[str]]
def back(state, fields) -> RunnerState
def review(state, fields) -> Review
def confirm(state, fields) -> list[dict[str, Any]]
```
Behaviour (the test pins each line):
- `start`: copy `answers` (a value of `None` is no answer; a text `note` is kept), drop answers of fields that are not visible, `at` = the first visible
  field, phase `fill`; with no visible field the phase is `review` and `at` is `None`.
- `answer`: set the value (and the note, else clear the note) of the current field, **drop the answers of fields that are no longer visible, then**
  run `validate_answers(..., partial=True)` over the result. Problems: return the unchanged state and the problems. Else advance to the next visible
  field **after the current one in field order** (not the next unanswered), or to phase `review` when there is none. In review, or with no current
  field, return the state and `["not at a field"]`.
- `skip`: a required field returns the state and `["<id>: answer required"]`. An optional field loses its value and note and the state advances as in
  `answer`.
- `back`: from review the last visible field (phase `fill`); from the first visible field no change; else the previous visible field (visibility from
  the current answers). Answers are kept.
- `review`: visible fields in order with their values and notes; `missing` lists visible required fields with no value.
- `confirm`: only in phase `review` (else `RunnerError(["not finished"])`); `missing` not empty gives `RunnerError(["<id>: answer required", ...])`;
  else the answers of visible fields that have a value, in field order: format 1 `{q, value, note}` (note may be None); format 2 `{q, value}` plus `note`
  only when the field has a note.
- Fields are dicts as `tl_core.forms.rules` takes them; `choices` None gives `()`.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/forms/rules.py` (signatures of `visible_ids`, `validate_answers` only)
- `docs/tickets/P2-FORMS/provided/T02_test_forms_runner.py` (the test)
- `packages/tl-core/tests/test_forms_rules.py` (test file style only)
may explore: none

## Allowed paths
- `packages/tl-core/src/tl_core/forms/runner.py` (create)
- `packages/tl-core/tests/test_forms_runner.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-FORMS/T02.md` (create)
Not allowed: `forms/__init__.py`, `rules.py`, any other file.

## Steps
1. Copy the provided test to its target (no edit, not even formatting: it is already `ruff format` clean). 2. Write `runner.py`, strict-pyright clean
(`from __future__ import annotations`; typed parameters; `# pyright: basic` is not allowed). 3. Run the acceptance commands.

## Acceptance
```
just check
just gate packages/tl-core/tests/test_forms_runner.py
cmp docs/tickets/P2-FORMS/provided/T02_test_forms_runner.py packages/tl-core/tests/test_forms_runner.py
```
Expected: 14 passed, `just check` clean, `cmp` silent.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Say `101` for the cmp line and `100` when no deviation.

## Escalation triggers
- The provided test cannot pass without a change to `rules.py` or the test: stop with `122`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
