# P0-I1-T04a — DDL type mapping

Status: draft (ready when T01 merges)
Tier: haiku
Labels: schema-tooling
Depends on: P0-I1-T01
Branch: `p0/i1/t04a-ddl-types`

## Goal
A pure, table-driven module that maps a LinkML built-in type to a SQL column type for SQLite and Postgres, and renders
a Python value as a SQL literal for a column `DEFAULT`. The DDL generator core (supervisor-built, P0-I1-T04b) calls it.
No LinkML or SQLAlchemy import is needed.

## Brief references (pasted)
> The same generated DDL targets SQLite and Postgres; promoted columns get indexes per the LinkML `indexed` annotation. (§5.4)
> Database: SQLite (WAL, JSON1, FTS5) | PostgreSQL 16+ (JSONB, GIN, `pg_trgm`, LISTEN/NOTIFY, partitioning on events). (§14)

From `docs/build-spec/03-repo-and-toolchain.md` §9 (the table this module's output must reproduce):
`psets_json TEXT NOT NULL DEFAULT '{}'  -- JSONB on Postgres`, `voided INTEGER NOT NULL DEFAULT 0  -- BOOLEAN on Postgres`,
`created_at TEXT NOT NULL  -- TIMESTAMPTZ on Postgres`, `version INTEGER NOT NULL`, `conformance TEXT NOT NULL DEFAULT 'ok'`.

## Interfaces
Create `packages/tl-schema/src/tl_schema/generators/ddl_types.py` with exactly this public surface:
```python
Dialect = Literal["sqlite", "postgres"]

def column_type(linkml_type: str, dialect: Dialect, *, json: bool = False) -> str:
    """SQL type for a LinkML built-in type name (lower case, as in linkml:types). json=True returns the JSON column
    type for the dialect whatever linkml_type is: TEXT on sqlite, JSONB on postgres.
    Raise ValueError(f"unsupported LinkML type: {linkml_type}") for a name not in the table."""

def sql_literal(linkml_type: str, value: object, dialect: Dialect, *, json: bool = False) -> str:
    """Render value as a SQL literal for a DEFAULT clause. See the rules below."""
```
Mapping table (the `TYPE_TABLE` constant in the module; one row per name, both dialects):

| LinkML type | sqlite | postgres |
|---|---|---|
| `string`, `uri`, `uriorcurie`, `curie`, `ncname`, `objectidentifier`, `nodeidentifier`, `jsonpointer`, `jsonpath`, `sparqlpath` | `TEXT` | `TEXT` |
| `enum` (pseudo-type used for any LinkML enum range) | `TEXT` | `TEXT` |
| `integer` | `INTEGER` | `BIGINT` |
| `boolean` | `INTEGER` | `BOOLEAN` |
| `float` | `REAL` | `REAL` |
| `double` | `REAL` | `DOUBLE PRECISION` |
| `decimal` | `NUMERIC` | `NUMERIC` |
| `date` | `TEXT` | `DATE` |
| `datetime` | `TEXT` | `TIMESTAMPTZ` |
| `time` | `TEXT` | `TIME` |
| `date_or_datetime` | `TEXT` | `TEXT` |

`sql_literal` rules, applied in this order:
1. `value is None` returns `NULL`.
2. `json=True`: serialise with `json.dumps(value, sort_keys=True, separators=(",", ":"))`, double any `'`, wrap in single quotes (`{}` becomes `'{}'`).
3. A `linkml_type` that is not in the table raises `ValueError` as `column_type` does.
4. `boolean`: the value must be a `bool` (else `TypeError`); sqlite returns `1`/`0`, postgres returns `TRUE`/`FALSE`.
5. `integer`: the value must be an `int` and not a `bool` (else `TypeError`); return `str(value)`.
6. `float`, `double`: the value must be an `int` or `float` and not a `bool` (else `TypeError`); return `repr(float(value))`.
7. `decimal`: the value must be `int`, `float` or `decimal.Decimal`, not `bool` (else `TypeError`); return `str(value)`.
8. Every other known type (text-like, date, datetime, time, enum): the value must be a `str` (else `TypeError`); double any `'` and wrap in single quotes.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-schema/src/tl_schema/generators/__init__.py` (exists, empty)

## Allowed paths
- `packages/tl-schema/src/tl_schema/generators/ddl_types.py` (create)
- `packages/tl-schema/tests/test_ddl_types.py` (create)

## Acceptance
```
just check
uv run pytest packages/tl-schema/tests/test_ddl_types.py -q
```
Expected: all pass; `just check` shows pyright `0 errors` (the module is checked in strict mode: annotate everything).

## Tests to add
`packages/tl-schema/tests/test_ddl_types.py`, parametrised:
- Every row of the table above, for both dialects, via `column_type` (one parametrised case per name per dialect, 2 x 20 cases).
- `column_type("integer", d, json=True)` returns `TEXT` for sqlite and `JSONB` for postgres, and so does `json=True` with `string`.
- `column_type("nonsense", "sqlite")` and `sql_literal("nonsense", "x", "sqlite")` raise `ValueError` whose message contains `nonsense`.
- `sql_literal`: `("string", "ok", d)` gives `'ok'`; `("string", "it's", d)` gives `'it''s'`; `("integer", 0, d)` gives `0`; `("boolean", False, "sqlite")` gives `0`, `("boolean", False, "postgres")` gives `FALSE`, `("boolean", True, "sqlite")` gives `1`; `("string", {}, d, json=True)` gives `'{}'` (any linkml_type); `("string", {"b": 1, "a": "x'y"}, d, json=True)` gives `'{"a":"x''y","b":1}'`; `("string", None, d)` gives `NULL`; `("integer", True, d)` raises `TypeError`; `("boolean", 1, d)` raises `TypeError`; `("double", 1.5, d)` gives `1.5`; `("enum", "ok", d)` gives `'ok'`.

## Report requirements
Standard report. State the number of parametrised cases that ran.

## Escalation triggers
- Stop if you believe a type is missing from the table; list it under *Open questions*, do not add it.

## Blocked

## Decision
