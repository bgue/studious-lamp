# P0-I3-T03b — Link read queries: `links_of`, `link_counts`, `search_linkable`

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I3-T01, P0-I3-T03 (merged into the base of this branch)
Branch: `p0/i3-t03b-link-queries`

## Goal
`tl_core/services/link_queries.py` answers the questions the Links tab, the grid and the link picker ask: all links of a record in both
directions with the label as read from that record, per-record counts, and a search over records that may be linked. The models and
SQL constants exist; the three functions raise `NotImplementedError`. A provided test file (18 tests) must pass.

## Brief references (pasted)
> **7.1** Typed fields and links are unified in the read model (`cur_links`), so both appear together everywhere. Relations have an inverse label (`raised against / has raised`).
> **7.4** Links tab: inbound and outbound links grouped by relation and type. Grid columns: link counts from current-state tables so they sort and filter. Record header badges: "3 open NCRs · 1 stale pin · 2 suggestions".
> **10.6 sketch 4 (link picker):** search across types, filter, preview line "NCR-P123-0042 · Open · 6 linked welds"; the picker lists records of the scope and the company.

### Specification (the provided test checks it)
- `links_of(uow, record_id, *, include_retracted=False) -> list[LinkView]`:
  1. `SELECT 1 FROM cur_core_record WHERE id = :id`; no row raises `RecordNotFoundError(f"no record {record_id!r}")`.
  2. Run `_LINKS_SQL` (already written: joins `cur_links` to the record at the other end; `direction` is `'out'` when the record is `from_id`), bound `id`; append `" AND l.status <> 'retracted'"` unless `include_retracted`.
  3. Build one `LinkView` per row (`row["declined"]` and `row["other_voided"]` become `bool`; `direction` is `"out"` or `"in"`). `label` is `_label(relation, direction)` (below).
  4. Sort: outbound before inbound, then the relation's index in `get_vocabulary().codes()` (codes not in it sort last), then `other_key or ""`, then `link_id`.
- `_label(relation, direction)` (private helper you write): `get_vocabulary().label(relation, direction)`; if that raises (a relation that has left the vocabulary) return `relation.replace("_", " ")`.
- `link_counts(uow, record_ids) -> dict[str, LinkCounts]`: start from `LinkCounts(record_id=id)` (all zero) for every id given; an empty sequence returns `{}` without querying; run `_COUNTS_SQL` with `{"ids": list(found)}` and replace each id's value with `LinkCounts(**dict(row))`.
- `search_linkable(uow, scope, query, *, record_type=None, exclude_id=None, limit=20) -> list[LinkTarget]`: build one SQL string:
  - `FROM cur_core_record r LEFT JOIN cur_link_counts c ON c.record_id = r.id`, select `r.id, r.key, r.type, r.title, r.status, r.scope, COALESCE(c.active_out, 0) + COALESCE(c.active_in, 0) AS link_total`.
  - `WHERE` (joined with `AND`): `r.voided = :no` (bound `False`), `r.scope IN (:scope, 'company')`, `r.type = :record_type` when given, `r.id <> :exclude_id` when given, and for each word of `query.split()` (index `i`): `(LOWER(COALESCE(r.key, '')) LIKE :wi ESCAPE '\' OR LOWER(r.title) LIKE :wi ESCAPE '\')` with `:wi` = `_like(word)`.
  - `ORDER BY CASE WHEN LOWER(COALESCE(r.key, '')) LIKE :prefix ESCAPE '\' THEN 0 ELSE 1 END, r.key, r.id LIMIT :limit`. `:prefix` is `_like(first word)` without its leading `%` (so `ncr` gives `ncr%`), or `"%"` when the query is empty.
  - `_like(word)` (private helper you write): lower-case the word, escape `\`, `%`, `_` with a backslash (do `\` first), and wrap in `%...%`. In the SQL text the escape character is a single backslash: write the Python literal as `"ESCAPE '\\'"`.
  - Return `LinkTarget(**dict(row))` for each row (use `.mappings()`).

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No SQLite- or Postgres-specific SQL; bound parameters only (the word patterns are parameters; only fixed text and numbered parameter names go into the SQL string).
- pyright is `strict` for `packages/tl-core/src`. ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back what you use.
- Remove the `STUB (P0-I3-T03b)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/services/link_queries.py (existing stub; models and SQL are final)
class LinkView(BaseModel): link_id, direction ("out"|"in"), relation, label, other_id, other_key, other_title, other_type, other_status, other_voided,
    status, pin, note, source, confidence, reason, declined, verified_by, verified_at, created_at, version
class LinkCounts(BaseModel): record_id: str; active_out: int = 0; active_in: int = 0; stale: int = 0; broken: int = 0; suggested: int = 0
class LinkTarget(BaseModel): id, key, type, title, status, scope, link_total: int
_LINKS_SQL: str      # SELECT ... FROM cur_links l JOIN cur_core_record r ... WHERE (l.from_id = :id OR l.to_id = :id)   (no ORDER BY)
_COUNTS_SQL          # text("SELECT record_id, active_out, active_in, stale, broken, suggested FROM cur_link_counts WHERE record_id IN :ids") with an expanding bindparam
def links_of(uow: UnitOfWork, record_id: str, *, include_retracted: bool = False) -> list[LinkView]
def link_counts(uow: UnitOfWork, record_ids: Sequence[str]) -> dict[str, LinkCounts]
def search_linkable(uow: UnitOfWork, scope: str, query: str, *, record_type: str | None = None, exclude_id: str | None = None, limit: int = 20) -> list[LinkTarget]
```
```python
from tl_core.links.provider import get_vocabulary   # .codes() -> list[str]; .label(code, "out"|"in") -> str (raises UnknownRelationError)
from tl_core.services.errors import RecordNotFoundError
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/services/link_queries.py`
- `packages/tl-core/src/tl_core/services/queries.py` (style of a query module)
- `docs/tickets/P0-I3/provided/test_link_queries.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/services/link_queries.py` (edit)
- `tests/services/test_link_queries.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T03b.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_link_queries.py.txt tests/services/test_link_queries.py`
2. Implement `_label`, `_like` and the three functions; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest tests/services/test_link_queries.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_link_queries.py.txt tests/services/test_link_queries.py
```
Expected: 18 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
