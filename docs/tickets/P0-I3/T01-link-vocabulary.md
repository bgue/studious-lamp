# P0-I3-T01 — Link relation vocabulary

Status: ready
Tier: haiku
Labels: core
Depends on: — (the stub is on the base branch)
Branch: `p0/i3-t01-link-vocabulary`

## Goal
`tl_core.links.vocabulary` implements the relation vocabulary of brief 7.1: a `RelationVocabulary` that holds relations with forward and
inverse codes and labels, can be extended, resolves either code, and a `default_relation` lookup per record-type pair. The data tables
(`DEFAULT_RELATIONS`, `DEFAULT_PAIR_RELATIONS`, `LinkSource`) and all signatures already exist in the stub; the six method bodies marked
`raise NotImplementedError` and `default_relation` are the work. A provided test file (24 tests) must pass.

## Brief references (pasted)
> **7.1 Relation vocabulary** (extensible, each with an inverse label): `references / referenced by`, `derived from / source of`, `supersedes / superseded by`, `responds to / responded by`, `raised against / has raised`, `resolves / resolved by`, `belongs to / contains`, `requires / required by`, `blocks / blocked by`, `verifies / verified by`, `dispatched from / dispatched`, `attached to`, `same as`. Each type pair has a default relation (weld → NCR defaults to `raised against`), so most links need no choice at all.

### Specification (the provided test checks it)
- A relation has a *forward code* (`raised_against`) and an *inverse code* (`has_raised`). A link is always stored forward; the inverse code and label only describe the same link as seen from the other record. `same_as` is symmetric: its inverse code equals its code.
- `add(relation)`: both codes must match `[a-z][a-z0-9_]*`, else `ValueError(f"relation code {code!r} must match [a-z][a-z0-9_]*")`. If any of the relation's codes (forward or inverse, of any relation already added) is already taken, raise `ValueError(f"relation code already in the vocabulary: {', '.join(sorted_clashing_codes)}")`. A symmetric relation counts its single code once. On success store it in `_relations[code]` and `_inverses[inverse_code]`.
- `codes()`: forward codes in insertion order. `__contains__(code)`: true only for forward codes (an inverse code, a non-string, or an unknown value is false).
- `get(code)`: the relation with that forward code. For an inverse code raise `UnknownRelationError(f"{code!r} is the inverse of {forward!r}; use {forward!r} with the two records swapped")`. For anything else raise `UnknownRelationError(f"unknown relation {code!r}")`.
- `resolve(code)`: `(relation, False)` for a forward code (including `same_as`), `(relation, True)` for an inverse code, `UnknownRelationError(f"unknown relation {code!r}")` otherwise.
- `label(code, direction)`: `code` must be forward (use `get`); `"out"` gives `label`, `"in"` gives `inverse_label`.
- `default_relation(from_type, to_type, pairs=None)`: look in `pairs` (default `DEFAULT_PAIR_RELATIONS`) for `(from_type, to_type)`, then `(from_type, "*")`, then `("*", to_type)`; return the first found, else `DEFAULT_RELATION`.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/links/vocabulary.py (existing stub; keep every name and signature)
@dataclass(frozen=True)
class Relation:
    code: str; label: str; inverse_code: str; inverse_label: str
    @property
    def symmetric(self) -> bool: ...          # already implemented

class RelationVocabulary:
    def __init__(self, relations: Iterable[Relation] = ()) -> None: ...   # already implemented; fills self._relations / self._inverses
    def add(self, relation: Relation) -> None: ...
    def codes(self) -> list[str]: ...
    def __contains__(self, code: object) -> bool: ...
    def get(self, code: str) -> Relation: ...
    def resolve(self, code: str) -> tuple[Relation, bool]: ...
    def label(self, code: str, direction: Direction) -> str: ...
def default_relation(from_type: str, to_type: str, pairs: Mapping[tuple[str, str], str] | None = None) -> str: ...
# already in the file: _CODE = re.compile(r"[a-z][a-z0-9_]*"), DEFAULT_RELATION = "references", Direction = Literal["out", "in"]
```
```python
# packages/tl-core/src/tl_core/services/errors.py (existing)
class UnknownRelationError(ServiceError): ...
```

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- pyright is `strict` for `packages/tl-core/src`; ruff limits lines to 100 columns. Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Remove the `STUB (P0-I3-T01)` paragraph from the module docstring when you are done.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/links/vocabulary.py`
- `docs/tickets/P0-I3/provided/test_link_vocabulary.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/links/vocabulary.py` (edit)
- `packages/tl-core/tests/test_link_vocabulary.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T01.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_link_vocabulary.py.txt packages/tl-core/tests/test_link_vocabulary.py`
2. Implement the methods and `default_relation`; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_link_vocabulary.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_link_vocabulary.py.txt packages/tl-core/tests/test_link_vocabulary.py
```
Expected: 24 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
