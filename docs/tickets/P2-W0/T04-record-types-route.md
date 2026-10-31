# P2-W0-OC-T1 — `GET /record-types` and `record_types()` on every client

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: api, core, tui
Depends on: OC-S2 (merged)
Branch: `p2/w0-t04-record-types-route`

## Goal
One read answers, for every record type, its label, module, offline class and drafting commands. The same table is on
the API (`GET /record-types`), the HTTP client (`RecordsApi.record_types()`), the TUI `ClientInterface` (embedded, remote,
fake). OC-T2 (the record screen row) reads it. No record data is read: the table is code and generated data only.

## Brief references (pasted)
> offline-classes spec 5.6: `GET /record-types` (action `reference.read`, supervisor decision D18: the action exists and is
> already in the agent allow list; a new action would be an auth change) answers `[{record_type, label, module, offline,
> drafting_commands}]` for every type (no record data). `ClientInterface.record_types()` (embedded, remote, fake).
> Supervisor decisions (this ticket only): the row model and its builder live in `tl_core/offline.py` so the route and the
> embedded client share one function (no second copy); extension types are not listed (their class is known only after a
> ledger read); the remote client needs no code (`RemoteClient.__getattr__` delegates to `RecordsApi`).

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-core/src/tl_core/offline.py (existing; add at the end of the file)
def _drafting_commands(record_type: str) -> frozenset[str]:   # existing, line ~114
    ...
# packages/tl-schema/src/tl_schema/generated/type_labels.py
TYPE_LABELS: Final[dict[str, str]] = {...}                     # record type -> label
# packages/tl-schema/src/tl_schema/generated/offline_classes.py
OFFLINE_CLASSES: Final[dict[str, OfflineClass]] = {...}        # record type -> full | draft_only | none
# packages/tl-api/src/tl_api/routes/reference.py (existing)
Reader = Annotated[str, Depends(guard("reference.read"))]
@router.get("/relations", operation_id="list_relations")
def list_relations(ctx: Ctx, actor: Reader) -> list[RelationOut]: ...
# packages/tl-api/src/tl_api/client/links.py (house style for a list read)
def relations(self) -> list[RelationOut]:
    return self._models(RelationOut, self._get_json("/relations"))
```
New, to write:
```python
class RecordTypeRow(BaseModel):            # tl_core.offline
    record_type: str                       # "engineering.Tag"
    label: str                             # TYPE_LABELS, else the record type itself
    module: str                            # the part before the first "."
    offline: OfflineClass
    drafting_commands: list[str]           # sorted; [] unless the class is draft_only
def record_type_rows() -> list[RecordTypeRow]   # one row per OFFLINE_CLASSES key, sorted by record_type
```
Route: `@router.get("/record-types", operation_id="list_record_types") def list_record_types(ctx: Ctx, actor: Reader) -> list[RecordTypeRow]: return record_type_rows()`.
Client: `RecordsApi.record_types(self) -> list[RecordTypeRow]` = `self._models(RecordTypeRow, self._get_json("/record-types"))`.
`ClientInterface.record_types(self) -> list[RecordTypeRow]` with a one-line docstring (`...` body, as its neighbours).

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `packages/tl-core/src/tl_core/offline.py` (lines 1-125)
- `packages/tl-api/src/tl_api/routes/reference.py` (lines 1-45)
- `packages/tl-api/src/tl_api/client/links.py` (`relations`, lines ~95-105)
- `packages/tl-tui/src/tl_tui/client.py` (`list_types`, lines ~189-195)
- `packages/tl-tui/src/tl_tui/embedded.py` (`list_types`, line ~567)
- `packages/tl-tui/tests/fakes_types.py` (`list_types`, line ~101)
- `dev/accept/P2-W0/RM-S3.py` (lines 1-110: the `World` class that builds an app and a client)
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/offline.py` (modify: the model and `record_type_rows` only)
- `packages/tl-api/src/tl_api/routes/reference.py` (modify)
- `packages/tl-api/src/tl_api/client/records.py` (modify)
- `packages/tl-tui/src/tl_tui/client.py` (modify)
- `packages/tl-tui/src/tl_tui/embedded.py` (modify)
- `packages/tl-tui/src/tl_tui/remote.py` (modify only if `just check` (pyright) requires it)
- `packages/tl-tui/tests/fakes_types.py` (modify: a fake, not a test)
- `docs/reference/openapi.json` (generated: `uv run python -m tl_api.openapi`)
- `dev/accept/P2-W0/OC-T1.py` (create)
- `docs/reports/P2-W0/OC-T1.md` (create)

## Steps
1. Add `RecordTypeRow` and `record_type_rows()` to `tl_core/offline.py`. Use `_drafting_commands(record_type)` for the commands (sorted list).
2. Add the route, the client method, the Protocol method, the embedded method (`return record_type_rows()`), the fake method (append `"record_types"` to `self.calls` as its neighbour does, then return `record_type_rows()`).
3. `uv run python -m tl_api.openapi` once to write the document.
4. Write `dev/accept/P2-W0/OC-T1.py` (exit 0, one `PASS <check>` line per check; style of `RM-S3.py`; SQLite temp ledger; `TL_ENV=test`). Checks: (a) `GET /record-types` as a viewer-level person answers 200 and a row for every key of `OFFLINE_CLASSES`; (b) `engineering.Tag` row is `full`, module `engineering`, `drafting_commands == []`; (c) `documents.Document` is `draft_only` and its `drafting_commands` is not empty; (d) `documents.ReviewCycle` is `none`; (e) no row has a key outside the five fields; (f) the JSON of the response equals `[r.model_dump() for r in record_type_rows()]`; (g) an unauthenticated call is 401 or 403.

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
just check
uv run python dev/accept/P2-W0/OC-T1.py
```
Expected: `just check` clean (openapi up to date); every check prints `PASS`, exit 0. Paste the last 10 lines of each in the report.

## Tests to add
None here. The end run (TB) writes `packages/tl-api/tests/test_api_record_types.py` and `packages/tl-tui/tests/test_client_record_types.py`. List in the report: the walking test `packages/tl-api/tests/test_confidentiality_walk.py` walks every GET route with no path parameter; say whether `/record-types` needs any entry there (read it, do not edit it).

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus the two pasted outputs and a line saying no pytest was run (deferred).

## Escalation triggers
- Stop and report *Blocked* if `tl_core.offline` cannot import `TYPE_LABELS` without an import cycle, or `just check` demands a change outside Allowed paths other than a consequential pin (rule 12: update it and list it).
- Stop if `reference.read` is refused for an agent token in the acceptance run; do not edit the allow list (`tl_core/auth/provider.py` line ~62).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
