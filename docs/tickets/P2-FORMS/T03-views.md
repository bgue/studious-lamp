# P2-FORMS-T03 — Read views of templates and submissions, and `form_for`

Status: ready
Tier: haiku
Kind: ticket
Review: full  (read path over confidential text; filter before LIMIT and counts)
Labels: module, tests
Depends on: S3, CR1 merged (rows, `confidential.py`, `hidden_answer_templates`); nothing else
Branch: `p2/forms-t03-views`
Worktree: harness-created under `/home/user/wt/forms/t03` (from `p2/ip` head)

## Goal
`tl_mod_forms/views.py`: the reads that the CLI (T05), the MCP tools (T06), the routes (T04) and the runner screen (T07) share. Nothing here writes and no access word is checked (the entry points check `forms.view`).
Pattern: `packages/tl-modules/requisitions/src/tl_mod_requisitions/views.py` (module docstring, `viewer=` keyword-only defaulting to `confidentiality.LOWEST`, `not_hidden_each` inside the statement and before `LIMIT`, clamped limits, frozen dataclasses). Read the `v_forms_*` views (`names.py` has the names).

## Brief references (pasted)
A hidden record answers as one that never existed (ADR-0016): lists omit it and its count, detail is `None`. A draft submission is read by its author alone (CR1 rule inside `not_hidden`); a submission's answers are record text. Templates are company-scope records, states Draft, Published, Retired;
submissions are project-scope, states Draft, Submitted, Returned, Accepted, Voided, Discarded (`names.py`). A record key can be null (a draft or a template has none).
`FormSource.binding(conn, record_id, viewer, now) -> FormBinding | None` (`tl_core/forms/types.py`); sources come from `tl_core.forms.registry.load_form_sources()` (empty today: no source is registered).

## Interfaces
```python
# packages/tl-modules/forms/src/tl_mod_forms/views.py (create)
MAX_LIMIT: Final = 500; MIN_LIMIT: Final = 1
@dataclass(frozen=True) class TemplateRow:  id, key (str|None), title, version, state, format_version, field_count, content_hash, bound_record_type, answer_class, intake, purpose, published_on, retired_on   # all str|int|None as stored; no fields list
@dataclass(frozen=True) class TemplateDetail:  row: TemplateRow, fields: list[dict[str, Any]], accepts_as: list[str]    # decoded JSON columns
@dataclass(frozen=True) class SubmissionRow:  id, key, state, template_id, template_version, subject_id, answer_class, author, submitted_on, reviewed_by, reviewed_on, draft_saves, version   # no answers, no notes
@dataclass(frozen=True) class SubmissionDetail:  row: SubmissionRow, answers: list[dict[str, Any]], review_note: str|None, void_reason: str|None
@dataclass(frozen=True) class Page[T]:  rows: list[T], total: int          # total counts only rows the viewer may read
def template_list(conn, *, state: str|None=None, intake: str|None=None, limit: int=100, offset: int=0, viewer=LOWEST) -> Page[TemplateRow]
def template_detail(conn, template_id: str, *, viewer=LOWEST) -> TemplateDetail | None
def submission_list(conn, scope: str, *, state=None, template_id=None, subject_id=None, author=None, limit=100, offset=0, viewer=LOWEST) -> Page[SubmissionRow]
def submission_detail(conn, scope: str, ref: str, *, viewer=LOWEST) -> SubmissionDetail | None      # ref is the record key or the id
def form_for(conn, record_id: str, *, now: datetime, viewer=LOWEST) -> FormBinding | None            # the source of the record's type, else None
```
An unknown `state` or `intake` value is a `ValueError("unknown state")` (fixed text). Order: templates by `title, version, id`; submissions by `submitted_on DESC NULLS LAST` written portably (`COALESCE`), `id`. A list runs at most two statements (rows, count). `form_for` loads the record type from the core record row the viewer may read
(absent or hidden: `None`), looks up the source, calls `binding`, and returns what it returns; no source for the type: `None`; it never raises for a bad record.
`answers`, `form_fields` and `accepts_as` are decoded from the JSON columns of the view; a column that is not valid JSON gives an empty list, not an exception.

## Context (read these, nothing else)
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/views.py` (the pattern), `packages/tl-modules/forms/src/tl_mod_forms/names.py`, `packages/tl-modules/forms/src/tl_mod_forms/confidential.py`
- `packages/tl-core/src/tl_core/forms/types.py` (`FormBinding`, `FormSource`), `packages/tl-core/src/tl_core/forms/registry.py`
- `packages/tl-modules/forms/tests/forms_world.py` (world helpers: `World.template`, `save`, `submit`, `call`) and `tests/test_visibility.py` (how a viewer is built; style)
may explore: `packages/tl-schema/src/tl_schema/generated/ddl/sqlite/v_forms_submission.sql` (column names)

## Allowed paths
- `packages/tl-modules/forms/src/tl_mod_forms/views.py` (create)
- `packages/tl-modules/forms/tests/test_views.py` (create); `packages/tl-modules/forms/tests/test_views_walk.py` (create)
- `docs/reports/P2-FORMS/T03.md` (create)
Not allowed: `module.py`, `names.py`, `confidential.py`, `tl_core/**`, `schema/**`, any other package, the intake tables (I03 owns them: no intake name in this file).

## Tests to add (lint-clean under `ruff format`, `ruff check`, strict `pyright`; each test builds its own world)
- `test_views.py`: template list (all states, filter by state and intake, order, limit clamp 0 -> 1 and 9999 -> 500, offset); detail decodes `fields` and `accepts_as`, an unknown id is `None`; submission list excludes `answers` (the dataclass has no such attribute) and filters by state, template, subject, author;
  detail by key and by id; a draft has `key None`; an unknown state is `ValueError("unknown state")`; `form_for` with an injected source (monkeypatch `load_form_sources` in the module namespace: no entry points) returns its binding, with no source returns `None`, for a hidden record returns `None` without calling the source.
- `test_views_walk.py` (the five readers, as `tests/test_visibility.py` builds them: the lowest clearance default, a reader of each class, the author, an admin, the system viewer): a restricted-class submission and a draft are absent from every list, from `total`, and `None` in detail for the readers who may not read them,
  and byte-identical to an absent id; **filter before LIMIT**: 8 rows with 3 hidden, `limit=5` gives 5 rows and `total == 5` readable ones counted correctly on page two; the default viewer (no `viewer=`) is the lowest clearance; a test that passes a wider viewer by default is wrong.
- A repo-style test: `views.py` source text holds no `forms_intake_body`, no `code_hash` and no `INSERT`, `UPDATE`, `DELETE`.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-modules/forms/tests/test_views.py packages/tl-modules/forms/tests/test_views_walk.py packages/tl-modules/forms/tests/test_visibility.py
```
Expected: all pass, `gate: PASS`. (If whole-repo pyright is killed for memory, run it scoped to `packages/tl-modules/forms` and say so.)

## Report requirements
Standard report; first line deviations or none; the statement count per list; the five-reader table result.

## Escalation triggers
- The hidden filter needs a change in `confidentiality.py` (stop; CR1's rows are frozen).
- `v_forms_*` lacks a column named above (report the real names; do not edit schema).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
