# P0-I4-T42 — Reference read routes

Status: ready
Tier: haiku
Labels: api
Depends on: — (the services are merged; the app and harness are on the base branch)
Branch: `p0/i4c-t42-reference-routes`

## Goal
`GET /relations`, `GET /relations/default`, `POST /keys/detect`, `GET /records/{record_id}/workflow`, `GET /schema/forms` and
`GET /records/{record_id}/conformance` return real data. They are what a remote client needs, besides records and links, to run the same
screens as an embedded one. `packages/tl-api/src/tl_api/routes/reference.py` exists with final signatures, decorators and models; the six
route bodies raise `NotImplementedError`. Implementing them is the work. A provided test file (9 tests) must pass.

## Brief references (pasted)
> **4** The TUI must work in both embedded and remote modes through a single client interface, so the same screens run against a laptop SQLite file or a production server.
> **7.1** Relation vocabulary: each relation has a label and an inverse label ("raised against" / "has raised"). **8** Workflow engine: declarative state machines (states, transitions, guards, required psets, required links). **6.3** Psets are validated against the scope's effective schema; conformance is reported, not only enforced.

### Specification (the provided test checks it)
Each route makes one `tl_core` call. Routes that need the database use `with ctx.backend(True) as uow:`.
- **`list_relations`** (no database): `vocabulary = get_vocabulary()`; for each `code in vocabulary.codes()`, `r = vocabulary.get(code)` and `RelationOut(code=r.code, label=r.label, inverse_code=r.inverse_code, inverse_label=r.inverse_label)`; return the list in that order.
- **`get_default_relation`** (no database): `DefaultRelationOut(relation=default_relation(from_type, to_type))`.
- **`detect_keys`**: `suggest_chips(uow, body.scope, body.text, linked_to=body.linked_to)`.
- **`get_workflow_status`**: `workflow_status(uow, record_id, roles=tuple(role or ()))`. `NoWorkflowError` and `RecordNotFoundError` propagate to the error table.
- **`get_form_metadata`**: `psets.form_metadata(uow, scope, record_type)`.
- **`get_conformance`**: `psets.conformance(uow, record_id)`.
- Imports to add (the stub omits them so `just check` stays green): `from tl_core.links.provider import get_vocabulary`, `from tl_core.links.vocabulary import default_relation`, `from tl_core.numbering.detect import KeyChip, suggest_chips` (extend the `KeyChip` import), `from tl_core.services import psets`, `from tl_core.services.workflow import WorkflowStatus, workflow_status` (extend the `WorkflowStatus` import).

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt`; you copy them into the test tree and must not edit the copy. A `.py.txt` is outside `ruff format`, so the supervisor formatted it already; `diff` it against the original in the last acceptance step.
- The package `tl-api` has a test harness (`packages/tl-api/tests/conftest.py`, `harness.py`): a real app over a real SQLite file. Tests import it with `from harness import ...`. Do not edit it and do not add `__init__.py` to the test directory.
- `just check` includes an OpenAPI drift check (`uv run python -m tl_api.openapi --check`). The stub's signatures, decorators, parameters and response models are final and already in the committed document. If `just check` reports the document out of date, you changed a signature: put it back. Never regenerate or edit `docs/reference/openapi.json`.
- ruff limits lines to 100 columns; run `uv run ruff format packages/tl-api` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/<ticket-id>.md`); it is inside your Allowed paths.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/links/provider.py:  get_vocabulary() -> RelationVocabulary   # .codes() -> list[str]; .get(code) -> Relation
# Relation: code, label, inverse_code, inverse_label (strings)
# packages/tl-core/src/tl_core/links/vocabulary.py
def default_relation(from_type: str, to_type: str, pairs=None) -> str
# packages/tl-core/src/tl_core/numbering/detect.py
def suggest_chips(uow, scope: str, text_: str, *, linked_to: str | None = None, patterns=None) -> list[KeyChip]
# packages/tl-core/src/tl_core/services/workflow.py
def workflow_status(uow, record_id: str, *, roles: tuple[str, ...] = ()) -> WorkflowStatus
# packages/tl-core/src/tl_core/services/psets.py
def form_metadata(uow, scope: str, record_type: str) -> FormMetadata
def conformance(uow, record_id: str) -> ConformanceReport
# packages/tl-api/src/tl_api/models.py (final)
class RelationOut(BaseModel): code: str; label: str; inverse_code: str; inverse_label: str
class DefaultRelationOut(BaseModel): relation: str
class DetectKeysBody(BaseModel): scope: str; text: str; linked_to: str | None = None
ctx.backend(readonly: bool) -> AbstractContextManager[UnitOfWork]
```
The stub (`packages/tl-api/src/tl_api/routes/reference.py`) is the other interface: keep every name, decorator, parameter and annotation.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-api/src/tl_api/routes/reference.py` (the stub)
- `packages/tl-api/src/tl_api/models.py`
- `packages/tl-api/tests/harness.py`
- `docs/tickets/P0-I4/provided/test_api_reference.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/routes/reference.py` (edit)
- `packages/tl-api/tests/test_api_reference.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T42.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_api_reference.py.txt packages/tl-api/tests/test_api_reference.py`
2. Implement the six routes; delete the `STUB (P0-I4-T42)` paragraph from the module docstring.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-api/tests/test_api_reference.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_api_reference.py.txt packages/tl-api/tests/test_api_reference.py
```
Expected: 9 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification, or if you think a signature must change.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
