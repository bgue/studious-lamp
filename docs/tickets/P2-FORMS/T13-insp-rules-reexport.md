# P2-FORMS-T13 — `insp_rules` re-exports the core validators

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, tests
Depends on: S1 merged (`tl_core.forms.rules`), INSP T00 merged (`insp_rules.py`); both on `p2/ip` @f137cca7
Branch: `p2/forms-t13-insp-rules-reexport`
Worktree: harness-created under `/home/user/wt/forms/t13` (from `p2/ip` head)

## Goal
The format 1 question rules exist once. `tl_mod_quality.insp_rules.validate_questions` and `validate_answers` become the core
functions (`tl_core.forms.rules`, `fmt=1`); `failed_questions` and `result_of` stay in the module (they carry the inspection's
meaning). The T00 test, unchanged, is the proof that nothing the module promised has moved.

## Brief references (pasted)
> S1 report: `rules.validate_questions(fields, *, fmt=1)`, `rules.validate_answers(fields, answers, *, fmt=1, partial=False,
> intake=False)`; format 1 behaviour and problem texts match T00's (`packages/tl-core/tests/test_forms_rules_format1.py` is T00's
> validate half run on core). Core constants: `tl_core.forms.types.MAX_FIELDS` (60), `MAX_FIELD_TEXT` (200), `MAX_CHOICES` (8),
> `MAX_ANSWER_TEXT` (1000), `MAX_NOTE` (300), `KINDS_1`, `KEYS_1`.

## Interfaces (after the change; the names stay importable from `insp_rules`)
```python
from tl_core.forms import rules as _rules
from tl_core.forms import types as _types

MAX_QUESTIONS = _types.MAX_FIELDS; MAX_QUESTION_TEXT = _types.MAX_FIELD_TEXT; MAX_CHOICES = _types.MAX_CHOICES
MAX_ANSWER_TEXT = _types.MAX_ANSWER_TEXT; MAX_NOTE = _types.MAX_NOTE
validate_questions = _rules.validate_questions   # called with the questions only: fmt defaults to 1
validate_answers = _rules.validate_answers       # called with questions and answers only
def failed_questions(questions: list[dict], answers: list[dict]) -> list[str]: ...   # unchanged
def result_of(questions: list[dict], answers: list[dict]) -> Literal["accept", "reject", "conditional"]: ...   # unchanged
```
Keep `KINDS`, `QUESTION_FIELDS`, `ANSWER_FIELDS` and `YES_NO_NA` only if `failed_questions`, `result_of` or the T00 test still read them
(`grep` first); delete the private validation helpers nothing reads any more (`_label`, `_question_problems`, `_value_problems`).

## Context (read these, nothing else)
- `packages/tl-modules/quality/src/tl_mod_quality/insp_rules.py`
- `packages/tl-modules/quality/tests/test_insp_rules.py` (read only; it must pass byte-identical)
- `packages/tl-core/src/tl_core/forms/rules.py` (signatures and the two public functions only)
may explore: (none)

## Allowed paths
- `packages/tl-modules/quality/src/tl_mod_quality/insp_rules.py`
- `docs/reports/P2-FORMS/T13.md` (create)
Not allowed: `test_insp_rules.py`, any `tl_core` file, `schema/**`.

## Steps
1. Replace the validation half of `insp_rules.py` with the re-exports above; fix the module docstring (it said "no import from
   `tl_core`": now it says the validators are the core format 1 rules and the two functions below are the inspection's own).
2. `just check`, then the gate. If a T00 case fails, do not edit the test or core: report the failing case id and the two texts
   in Blocked (a difference between the two rule copies is a defect of S1 or T00, decided by the supervisor).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-modules/quality/tests/test_insp_rules.py packages/tl-core/tests/test_forms_rules_format1.py
```
Expected: all pass, `gate: PASS`; `git diff --stat` shows `insp_rules.py` (about 120 lines removed) and the report.

## Tests to add
None. The existing T00 test is the test.

## Report requirements
Standard report; first line deviations or none; the final public names of `insp_rules`; the lines removed.

## Escalation triggers
- A T00 case fails on the core functions.
- `pyright` rejects the re-exported signature where a caller passes a plain `list[dict]`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
