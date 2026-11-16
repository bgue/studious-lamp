# P2-FORMS-B1 — SurveyJS model projection of a form's fields

Status: ready
Tier: haiku
Kind: ticket
Review: full  (its output reaches a script-bearing page in W2; no provided test, so the lite rule does not apply)
Labels: core, tests
Depends on: S1, T01 merged (`tl_core.forms.jsonschema` is the model for style and tests); W1 merged (the renderer class is `SurveyUI.Model`)
Branch: `p2/forms-b1-surveyjs`
Worktree: harness-created under `/home/user/wt/forms/b1` (from `p2/ip` head)

## Goal
`tl_core.forms.surveyjs` turns a template's fields into the JSON model that the vendored SurveyJS renderer (W1) builds a page from, and names the fields the
renderer cannot show. Pure projection: no I/O, imports only `tl_core.forms.rules`, `tl_core.forms.types`, `typing`. The browser only helps the person; the server
stays the validator (`validate_answers`). The `?as=surveyjs` route is T04's, not this ticket's.

## Interfaces
```python
# packages/tl-core/src/tl_core/forms/surveyjs.py  (create)
def to_surveyjs(fields: list[dict[str, Any]], fmt: int = 2) -> dict[str, Any]: ...
def surveyjs_unsupported(fields: list[dict[str, Any]]) -> list[str]: ...   # ids of fields left out of the model, in field order
```
Bad `fmt` or fields that `validate_questions(fields, fmt=fmt)` reports: `ValueError` (first problem as the text), as in T01.

## Shape (deterministic; JSON-serialisable; the same output whatever the dict key order)
`{"showQuestionNumbers": "off", "clearInvisibleValues": "onHidden", "checkErrorsMode": "onComplete", "pages": [{"name": "page1", "elements": [<element or panel>...]}]}`.
No other top-level key (the renderer must get nothing it does not know). All text is plain: every title, description and choice is the template's string, unchanged
(no markup is added or interpreted here; W2 turns markdown off in the renderer).
Element of a field (`name` = field id, `title` = field text, plus the keys below; `description` = help, left out when none; `isRequired` = required):
| kind | element |
|---|---|
| `yes_no_na` | `{"type": "radiogroup", "choices": [{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}, {"value": "na", "text": "Not applicable"}], "colCount": 3}` |
| `number` | `{"type": "text", "inputType": "number"}`; **no** `min` or `max` (S1: an out-of-range number is valid, it only fails a rule); a `unit` is shown as `title` = `"<text> (<unit>)"` |
| `text` | `{"type": "text", "maxLength": 1000}` |
| `choice` | up to 4 choices `{"type": "radiogroup", "choices": [..strings..]}`, more `{"type": "dropdown", "choices": [...]}` |
| `multi` | `{"type": "checkbox", "choices": [...strings...]}` |
| `date` | `{"type": "text", "inputType": "date"}` |
| `photo` | **not in the model**; its id is in `surveyjs_unsupported` (a file upload is the terminal's job in v1) |
Format 2 sections: consecutive fields with the same non-null `section` go in one `{"type": "panel", "name": "sec<n>" (n from 1, in order), "title": <section>, "elements": [...]}`; a field with no
section (and every format 1 field) is a top-level element. A panel left empty because all its fields are photos is not emitted.
`visible_when` becomes the element's `visibleIf` string (left out when null). Grammar, one rule per node, exactly these strings (`Q` = `{id}`):
`{"q": id, "is": v}` -> `Q = V`; `"in": [v1, v2]` -> `(Q = V1 or Q = V2)`; `"gte": n` -> `Q >= N`; `"lte": n` -> `Q <= N`; `"answered": true` -> `Q notempty`; `"answered": false` -> `Q empty`;
`{"all": [a, b]}` -> `(A and B)`; `{"any": [a, b]}` -> `(A or B)`; `{"not": a}` -> `!(A)`. V: a string is single-quoted with `\` written `\\` and `'` written `\'`; a number is its `repr` (no exponent change); `true`/`false` for bools.
A condition that names a photo field is rendered as written (the field is not in the model, so the renderer sees it as never answered); do not special-case it.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/forms/jsonschema.py` (style, error handling), `packages/tl-core/tests/test_forms_jsonschema.py` (fixture loading helper)
- `packages/tl-core/src/tl_core/forms/rules.py` (`validate_questions` signature; the `visible_when` grammar lines 180-225)
- `schema/fixtures/forms/templates/*.yaml` (the five property data files; `intake/*.yaml` are not projected here)
may explore: `packages/tl-core/src/tl_core/forms/types.py` constants

## Allowed paths
- `packages/tl-core/src/tl_core/forms/surveyjs.py` (create)
- `packages/tl-core/tests/test_forms_surveyjs.py` (create)
- `docs/reports/P2-FORMS/B1.md` (create)
Not allowed: `forms/__init__.py`, any other `tl_core` file, `pyproject.toml`, anything under `static/` (the library is W1's).

## Tests to add (`test_forms_surveyjs.py`; lint-clean under `ruff format`, `ruff check` and strict `pyright`)
- Every top-level fixture template projects; `json.dumps(sort_keys=True)` identical when each field dict is rebuilt in reverse key order; the set of element names (walking panels) equals the field ids minus `surveyjs_unsupported`; every `isRequired` equals `required`;
  no element has `min`, `max`, `html` or a key outside {`type name title description isRequired choices colCount inputType maxLength visibleIf elements`}.
- Table test of the nine `visible_when` nodes above (with `Q` = a real field id), including a string `it's a \ test` and a nested `all` of `any` of `not`; the exact strings are pinned.
- Kind table: one field per kind gives the pinned element; a 5-choice `choice` is a dropdown, a 4-choice one a radiogroup; a number with `min`, `max`, `unit` has the unit in the title and no `min`/`max` key.
- Sections: three fields, A and B in section "S" then C with none: one panel `sec1` with two elements, then C; a section that holds only a photo field emits no panel; format 1 fields (no section) are all top level.
- Texts pass through unchanged: a field text `<img src=x onerror=1> {topic}` and a choice `</script>` appear byte-identical in the model (no escaping here; the page escapes).
- `fmt=3` and a field list with a bad kind raise `ValueError`.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-core/tests/test_forms_surveyjs.py packages/tl-core/tests/test_forms_jsonschema.py
```
Expected: all pass, `gate: PASS`. (Whole-repo pyright can be killed for memory on a busy box: run `uv run pyright packages/tl-core/src/tl_core/forms packages/tl-core/tests/test_forms_surveyjs.py` and say so.)

## Report requirements
Standard report; first line deviations or none; the element count per fixture. Note for W2: the expression strings are only pinned here; the W2 probe loads them into the real library.

## Escalation triggers
- A fixture field cannot be expressed by the table (say which; do not invent an element type).
- The S1 `visible_when` grammar has an operator this ticket does not list.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
