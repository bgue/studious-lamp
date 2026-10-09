# P0-I3-T14a — Trace query: the n-hop tree over links

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I3-T01, P0-I3-T03 (merged into the base of this branch)
Branch: `p0/i3-t14a-trace-query`

## Goal
`tl_core/services/link_trace.py` builds the tree of records reachable from a record through links, for the Trace tab, `GET /trace` (P0-I4) and the
MCP `trace` tool. The model (`TraceNode`), the SQL constant and the signature exist; `trace` raises `NotImplementedError`. A provided test file
(13 tests) must pass.

## Brief references (pasted)
> **7.5 Trace view (`t`):** n-hop tree or graph, e.g. deficiency → inspection → weld → spool → line → test package → subsystem → system. **API / MCP:** `GET /records/{id}/links?relation=…&depth=…`, `/trace`; MCP `get_links`, `trace`, `follow`.
> **Sketch 12:** a Trace tab next to Links; a record that is reached through several paths is shown once.

### Specification (the provided test checks it)
`trace(uow, record_id, *, depth=2, direction="both", statuses=DEFAULT_STATUSES, max_nodes=200) -> TraceNode`:
1. Read the root with `_RECORD_SQL` (bound `id`) using `uow.conn().execute(...).mappings().first()`; none raises `RecordNotFoundError(f"no record {record_id!r}")`.
2. `vocabulary = get_vocabulary()`; `order = {code: index}` over `vocabulary.codes()`.
3. A helper `neighbours(rid)` runs `_NEIGHBOURS_SQL` with parameters `{"id": rid, "want_out": direction in ("out", "both"), "want_in": direction in ("in", "both"), "yes": True, "statuses": list(statuses)}` (rows via `.mappings()`, as dicts) and sorts them by `(row["direction"] != "out", order.get(relation, len(order)), str(row["key"] or ""), str(row["link_id"]))`. Row columns: `link_id, relation, link_status, direction ('out'|'in'), id, key, title, type, status, voided`.
4. The root is `TraceNode(record_id=..., key=..., title=..., type=..., status=..., voided=bool(...), depth=0)`. Keep `nodes: dict[record_id, TraceNode]` (the root first) and `frontier = [root]`.
5. For `level` from 1 to `depth`: for each `parent` in `frontier` (in order) and each neighbour row of `parent.record_id`: skip it if its record id is already in `nodes` **or** `len(nodes) >= max_nodes`; otherwise build a child `TraceNode(record_id, key, title, type, status, voided=bool(...), depth=level, link_id, link_status=row["link_status"], relation, direction=<"out" or "in">, label=<label>)`, append it to `parent.children`, add it to `nodes` and to the next frontier. `label` is `vocabulary.label(relation, direction)`; if that raises (a relation that left the vocabulary) use `relation.replace("_", " ")`. After the level, the next frontier replaces the current one. So the tree is breadth-first and each record appears once, at the depth where it is first reached.
6. Finally, for every node in `nodes`: `node.more = len({row["id"] for row in neighbours(node.record_id)} - set(nodes))`, the number of linked records that are not in the tree.
7. Return the root.
(`pyright` strict: the row values are `object`; wrap with `str(...)` / `bool(...)`, and use `typing.cast` or a `# type: ignore[arg-type]` only where the ticket's reference had it: `key=row["key"]` and `status=row["status"]` are `str | None`.)

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No SQLite- or Postgres-specific SQL; the SQL is already written with bound parameters.
- pyright is `strict` for `packages/tl-core/src`. ruff limits lines to 100 columns; run `uv run ruff format` and `uv run ruff check --fix` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back what you use (`get_vocabulary`, `RecordNotFoundError`, ...).
- Remove the `STUB (P0-I3-T14a)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/services/link_trace.py (existing stub; models and SQL are final)
TraceDirection = Literal["out", "in", "both"]
DEFAULT_STATUSES: tuple[str, ...] = ("active", "stale", "broken")
class TraceNode(BaseModel): record_id: str; key: str | None; title: str; type: str; status: str | None; voided: bool; depth: int
    link_id: str | None = None; link_status: str | None = None; relation: str | None = None; direction: Literal["out", "in"] | None = None
    label: str | None = None; children: list[TraceNode] = []; more: int = 0
_RECORD_SQL        # SELECT id, key, title, type, status, voided FROM cur_core_record WHERE id = :id
_NEIGHBOURS_SQL    # text(...) with an expanding bindparam "statuses": links of :id (outbound if :want_out = :yes, inbound if :want_in = :yes) joined to the record at the other end
def trace(uow: UnitOfWork, record_id: str, *, depth: int = 2, direction: TraceDirection = "both",
          statuses: Sequence[str] = DEFAULT_STATUSES, max_nodes: int = 200) -> TraceNode
```
```python
from tl_core.links.provider import get_vocabulary   # .codes() -> list[str]; .label(code, "out"|"in") -> str (raises UnknownRelationError)
from tl_core.services.errors import RecordNotFoundError
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/services/link_trace.py`
- `packages/tl-core/src/tl_core/services/link_queries.py` (a sibling query module with the same sort rule)
- `docs/tickets/P0-I3/provided/test_link_trace.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/services/link_trace.py` (edit)
- `tests/services/test_link_trace.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T14a.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_link_trace.py.txt tests/services/test_link_trace.py`
2. Implement `trace`; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest tests/services/test_link_trace.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_link_trace.py.txt tests/services/test_link_trace.py
```
Expected: 13 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

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
