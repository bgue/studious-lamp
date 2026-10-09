# P0-I2-T08a — Lint rules for package documents

Status: merged
Tier: haiku
Labels: core
Depends on: P0-I2-T03 (merged into the base of this branch)
Branch: `p0/i2a-t08a-lint-rules`

## Goal
`tl_schema.lint.lint_documents(docs)` checks a set of package documents against seven naming, definition and consistency rules and returns
sorted `LintIssue`s. The module is a stub; after this ticket it works and a provided test file passes. (`tl schema lint` in ticket T08 prints these.)

## Brief references (pasted)
> **27.6 Semantic integrity.** Definition: description mandatory; label + optional alternative labels. Units: quantities declare a unit (UCUM codes). External alignment: `exact_mappings` ... required for `materialize: true` properties where a counterpart exists (company policy). Value lists: values are LinkML enums with meanings. **Lint:** naming conventions, missing definitions or units, orphan code lists, unmapped source properties, conflicting mappings. **Duplicate detection:** lexical + embedding similarity across all company and project properties; the workbench warns when a "new" property resembles an existing one (e.g. `seat_leak_cls` vs `seat_leakage`).

### Rules (the specification; the provided test checks it)
Severity is `warning` unless stated. All text below is exact where quoted.
| Rule | Where it applies | Condition | `message` |
|---|---|---|---|
| L001 | code list, pset, property (including extension custom properties) | `len(description.strip()) < 10` | `description is shorter than 10 characters` |
| L002 | property with `range == "decimal"` | `unit is None` | `decimal property has no unit` |
| L003 | code list | its name is not the `range` of any property in any document of the set | `code list <Name> is not used by any property` |
| L004 | property | `materialize` is true and `exact_mappings` is empty | `promoted property has no exact_mappings` |
| L005 | pair of properties | two properties with different names whose normalised names are equal or similar (below) | `<later name> resembles <earlier name> (<earlier package> <earlier path>)` |
| L006 | code list | fewer than 2 values | `code list <Name> has fewer than 2 values` |
| L007 | pset (severity `error`) | an `applies_to` entry does not fully match `[a-z][a-z0-9_]*\.[A-Z][A-Za-z0-9]*` | `applies_to <entry!r> is not <module>.<Class>` (use `f"applies_to {record_type!r} is not <module>.<Class>"`) |

Properties of the set: for each document `doc`, every `doc.psets[<pset>].properties[<name>]` (path `psets.<pset>.properties.<name>`) and every
`entry.custom[<name>]` of each `entry` in `doc.extends` (path `extends.<pset>.custom.<name>` where `<pset>` is `entry.target()[2]`).
Other paths: code list `code_lists.<Name>`; pset `psets.<pset>`. `package` is `doc.key()`.

Similarity (L005): `normal(name) = name.replace("_", "").lower()`. Two properties are similar when `normal` of both names is equal, or
`difflib.SequenceMatcher(None, a, b).ratio() >= 0.85` for the normalised names. Equal names never pair (the same name in two psets is
deliberate consistency). Sort all properties by `(package, path)`; for each property compare it with every earlier one in that order;
the issue is reported on the later property (its `package` and `path`) and the message names the earlier one.

`lint_documents` returns all issues sorted by `(package, path, rule)`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I2/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copied test.
- pyright is strict for `packages/tl-schema/src`; `ruff` enforces 100 columns including docstrings, comments and long call lines (wrap them).
- `uv` prints "UV_NATIVE_TLS is deprecated" on every call. Ignore it. If imports fail in a fresh worktree run `uv sync --all-packages` once. Do not pipe `just check` into `tail` (it hides the exit code).

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-schema/src/tl_schema/lint.py (stub; keep LintIssue exactly, replace the body of lint_documents, add helpers)
@dataclass(frozen=True)
class LintIssue:
    severity: Literal["error", "warning"]
    rule: str  # "L001" ... "L007"
    package: str  # "name@version"
    path: str  # "psets.valve_data.properties.size_in", "code_lists.MaterialCode"
    message: str

def lint_documents(docs: Sequence[PackageDoc]) -> list[LintIssue]: ...
```
```python
# packages/tl-schema/src/tl_schema/packages.py (read-only; the parts you use)
class PropertyDef(BaseModel):
    description: str; range: str   # a kind ("decimal", "string", ...) or a code list name
    unit: UnitDef | None; materialize: bool; exact_mappings: list[str]
class CodeList(BaseModel): description: str; values: list[CodeValue]
class PsetDef(BaseModel): description: str; applies_to: list[str]; properties: dict[str, PropertyDef]
class ExtendsDef(BaseModel):
    ref: str; custom: dict[str, PropertyDef]
    def target(self) -> tuple[str, str, str]: ...      # (package, version, pset)
class PackageDoc(BaseModel):
    code_lists: dict[str, CodeList]; psets: dict[str, PsetDef]; extends: list[ExtendsDef]
    def key(self) -> str: ...                          # "name@version"
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-schema/src/tl_schema/lint.py`
- `packages/tl-schema/src/tl_schema/packages.py`
- `packages/tl-schema/tests/conftest.py`
- `docs/tickets/P0-I2/provided/test_lint.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-schema/src/tl_schema/lint.py` (edit: implement the stub)
- `packages/tl-schema/tests/test_lint.py` (create: `cp` of the provided file, byte for byte)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_lint.py.txt packages/tl-schema/tests/test_lint.py`
2. Implement the rules.
3. Run the acceptance commands.

## Acceptance
```
uv run pytest packages/tl-schema/tests/test_lint.py -q
just check
just test
diff docs/tickets/P0-I2/provided/test_lint.py.txt packages/tl-schema/tests/test_lint.py
```
Expected: all tests pass (11 in the provided file), `just check` and `just test` exit 0, `diff` prints nothing. The fixtures produce exactly one warning (L004 on `body_material`).

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands and the test count.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the rule table above.
- Stop rather than change `packages.py` or `conftest.py`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
