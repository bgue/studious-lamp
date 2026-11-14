# P2-X1-T04 — OpenAPI diff function in `compat.py`

Status: ready (dispatch r1; the provided test and the stub are committed on `p2/x1`)
Tier: haiku
Kind: ticket
Review: full
Labels: core, tests
Depends on: —
Branch: `p2/x1-t04-openapi-diff`
Worktree: `/home/user/wt/x1/t04`

## Goal
`tl_schema.compat.diff_openapi(baseline, current)` returns one line per breaking change between two OpenAPI documents (dicts as in
`docs/reference/openapi.json`); an empty list means additive. It reuses the existing `_node` and `_object` rules for schemas. It is not
wired into `just check` (T05 does that).

## Brief references (pasted)
Rule (owner, additive only): allowed are a new operation, a new response code, a new optional parameter, a new optional property, a
looser rule. Refused: a removed operation (method + path), a removed response code, a new required parameter, a removed component
schema, and inside a component schema everything `_node` already refuses (removed property, changed type, newly required property,
tightened enum or bound).

## Interfaces (verbatim from the repo; the stub raises `NotImplementedError`)
```python
def diff_openapi(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """One line per breaking change between two OpenAPI documents (P2-X1-T04)."""
# existing, reuse: _node(old, new, where, out) and _object(old, new, where, out) append lines to `out`
```
Line formats (the test checks these parts): `GET /items: operation removed`; `GET /items: response 404 removed`;
`GET /items: parameter 'tenant' added as required` (match parameters by `name` and `in`; a removed parameter is allowed);
`schema Item: removed`; schema lines are the `_node` lines with `where="schema Item"`, for example
`schema Item: property 'kind' removed`, `schema Item: property 'id' became required`.
Operations are the keys `get put post delete patch head options` under each path. Walk every component schema in the baseline
(`components.schemas`); `$ref` inside schemas is left as is (compared as text by `_node`; no resolving).

## Context (read these, nothing else)
- `packages/tl-schema/src/tl_schema/compat.py`
- `packages/tl-schema/tests/test_compat_openapi.py` (provided; do not edit)
- `packages/tl-schema/tests/test_compat.py` (style only)

## Allowed paths
- `packages/tl-schema/src/tl_schema/compat.py` (edit: replace the stub, no other function changes)

## Acceptance
```
just check
uv run pytest packages/tl-schema/tests/test_compat_openapi.py packages/tl-schema/tests/test_compat.py -q
just gate packages/tl-schema/tests
```
Expected: all pass.

## Tests to add
None; the provided test is the spec.

## Report requirements
Standard report (`docs/templates/haiku-report.md`); say that the provided test is byte-identical (phrase 101).

## Escalation triggers
- Stop if a provided test case needs a line format the Interfaces section does not give.
- Stop if the stub signature would have to change.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
