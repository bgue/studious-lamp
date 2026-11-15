# P2-FORMS-T01 — JSON Schema projection of a form's answers

Status: ready
Tier: haiku
Kind: ticket
Review: full  (README said lite: no provided test exists, so the lite rule does not apply)
Labels: core, tests
Depends on: S1 merged (`tl_core.forms`), S2 merged (fixtures under `schema/fixtures/forms/templates/`); both on `p2/ip` @f137cca7
Branch: `p2/forms-t01-json-schema`
Worktree: harness-created under `/home/user/wt/forms/t01` (from `p2/ip` head)

## Goal
`tl_core.forms.jsonschema.to_json_schema(fields, fmt)` returns a JSON Schema (draft 2020-12) that describes the **answers list** of a
template: what a client or an agent may send as `answers`. It is a pure projection (routes, the CLI and tools use it later). It
describes the shape of each answer; it does not decide visibility, required answers or duplicates (those stay in `validate_answers`),
and it says so in `x-` annotations.

## Brief references (pasted)
Answer `{q, value, note}`; `note` a string up to 300 or null or absent. Value by kind (S1 rules): `yes_no_na` one of `"yes"`, `"no"`, `"na"`;
`number` int or float, not bool (an out-of-range number is valid); `text` a string up to 1000; `choice` one string of `choices`;
`multi` a list of distinct members of `choices` (empty allowed); `date` a real `YYYY-MM-DD` day; `photo` a list of 1 to 10 distinct
26-character ULIDs (pattern `^[0-9A-HJKMNP-TV-Z]{26}$`). Field keys: `id text kind required unit min max choices fails_when`, and in
format 2 `section help visible_when`.

## Interfaces
```python
# packages/tl-core/src/tl_core/forms/jsonschema.py  (create; imports only tl_core.forms.rules/types and typing)
def to_json_schema(fields: list[dict[str, Any]], fmt: int = 2) -> dict[str, Any]: ...
```
Shape of the result (deterministic; JSON-serialisable; same output for the same fields whatever the dict key order):
```json
{"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "array", "maxItems": <len(fields)>,
 "items": {"oneOf": [<one branch per field, in field order>]}}
```
Branch of a field: `{"type": "object", "additionalProperties": false, "required": ["q", "value"], "title": <field text>,
"properties": {"q": {"const": <id>}, "value": <value schema>, "note": {"type": ["string", "null"], "maxLength": 300}},
"x-required": <bool>, "x-section": <str|null>, "x-help": <str|null>, "x-visible-when": <node|null>, "x-unit": <str|null>}`;
`x-` keys with a null value are left out. Value schema: `yes_no_na` `{"enum": ["yes", "no", "na"]}`; `number` `{"type": "number"}`
(`x-min`, `x-max` carried on the branch, never as `minimum`); `text` `{"type": "string", "maxLength": 1000}`; `choice` `{"enum": choices}`;
`multi` `{"type": "array", "items": {"enum": choices}, "uniqueItems": true}`; `date` `{"type": "string", "format": "date"}`;
`photo` `{"type": "array", "minItems": 1, "maxItems": 10, "uniqueItems": true, "items": {"type": "string", "pattern": <ULID pattern>}}`.
The top-level schema also carries `"x-note": "visibility, required answers and repeated questions are checked by validate_answers"`.
`fmt` other than 1 or 2, or fields for which `validate_questions(fields, fmt=fmt)` reports a problem: `ValueError` (the first problem in the text).

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/forms/rules.py` (signatures and the ULID pattern only)
- `packages/tl-core/src/tl_core/forms/types.py` (constants)
- `schema/fixtures/forms/templates/toolbox-talk.yaml` (shape; the five fixtures are the property data)
- `packages/tl-core/tests/test_forms_rules.py` (test style only)
may explore: `schema/fixtures/forms/templates/**`

## Allowed paths
- `packages/tl-core/src/tl_core/forms/jsonschema.py` (create)
- `packages/tl-core/tests/test_forms_jsonschema.py` (create)
- `docs/reports/P2-FORMS/T01.md` (create)
Not allowed: `forms/__init__.py` (no re-export), any other `tl_core` file, `pyproject.toml` (the `jsonschema` library is already installed: the
contract tests import it; the module itself does not import it).

## Tests to add (`test_forms_jsonschema.py`; lint-clean under `ruff format`, `ruff check` and strict `pyright`, which `just check` runs over tests)
- Every fixture template (the five YAML files; `fields` and `format_version` from the file) projects, the result is a valid schema
  (`Draft202012Validator.check_schema`) and `json.dumps(..., sort_keys=True)` is identical when each field dict is rebuilt in reverse key order.
- Property (the agreement test): for every field of every fixture, with `visible_when` removed from a copy of the fields, for each sample value
  of its kind (yes_no_na `"yes"`, `"maybe"`; number `3`, `2.5`, `"3"`, `True`; text `"x"`, `5`, a 1001-character string; choice the first
  choice, `"zzz"`; multi the first choice as a one-item list, `["zzz"]`, a repeated pair, `[]`; date `"2026-02-03"`, `"2026-13-40"`;
  photo one ULID in a list, `[]`, the same ULID twice, `["short"]`) and the note values `None` and a 301-character string: the schema
  accepts `[{"q": id, "value": v, "note": n}]` (validator built with `Draft202012Validator.FORMAT_CHECKER`) exactly when
  `validate_answers([field], answer, fmt=2, partial=True)` returns no problem. A mismatch is a defect of the projection, not of the test.
- Unit: format 1 fields project (no `x-section` keys); `fmt=3` and a field list with a bad kind raise `ValueError`; an answer naming an
  unknown `q` is refused by the schema; an answer with an extra key is refused.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-core/tests/test_forms_jsonschema.py packages/tl-core/tests/test_forms_rules.py
```
Expected: all pass, `gate: PASS`.

## Report requirements
Standard report; first line deviations or none; the property data (value counts) and any value the two disagree on that you fixed in the projection.

## Escalation triggers
- The two disagree on a value the S1 rules define differently from the brief references above (report both outputs; do not edit `rules.py`).
- Strict pyright rejects a fixture-loading helper that cannot be typed with `Any`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
