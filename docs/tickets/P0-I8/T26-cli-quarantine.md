# P0-I8-T26 — `tl types quarantine ls|recheck`

Status: ready
Tier: haiku
Labels: cli
Depends on: S22/S23 (registry, body store), T20 (the `tl types` group), merged on `p0/i8b`
Branch: `p0/i8b-t26-cli-quarantine`

## Goal
The quarantine report command: `tl types quarantine ls` lists everything the extension type registry refused (package versions that failed validation, registered versions whose files
were edited, records whose stored body failed verification), and `tl types quarantine recheck <record-id>` verifies a damaged body again and lifts the quarantine when the object is
sound. The group is already registered under `tl types` in `main.py`.

## Brief references (pasted)
> §31.4 Bodies are never trusted without validation. Hashes are verified on read, and mismatches are quarantined.
>
> What is quarantined, and how it ends: a package that fails validation is `quarantined` with a report of issues (`kind`, `path`, `detail`); fixing the files and running `tl types sync`
> registers it. An edit to a registered version's files is a `conflict`: the registration stays, the change is reported once; reverting the files clears it. A record whose stored body
> does not match its recorded hash (or whose object is missing) is listed in `tl_body_quarantine` and its body is not served; storing the same body again heals the object, and
> `recheck` lifts the quarantine when the object is already sound again.

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_core/extypes/registry.py
class QuarantineEntry(BaseModel):
    type_ref: str; status: TypeStatus; location_uri: str
    content_hash: str            # of the files as found
    registered_hash: str | None  # the registered version's hash when this is a conflict
    report: list[TypeIssue]; seq: int
def list_quarantined(conn) -> list[QuarantineEntry]: ...
# tl_core/extypes/body.py
class BodyQuarantineEntry(BaseModel):
    record_id: str; scope: str; type_name: str; uri: str; expected_hash: str; actual_hash: str | None
    reason: str          # "hash mismatch" or "object missing"
    detected_at: str
def list_body_quarantine(conn) -> list[BodyQuarantineEntry]: ...
def recheck_body(factory, store, *, stream_id: str) -> bool: ...   # True: sound, quarantine lifted; BodyNotFoundError if no body
# tl_core/extypes/types.py
class TypeIssue(BaseModel): kind: str; path: str | None; detail: str
# tl_adapters.objectstore
def make_object_store() -> ObjectStore: ...    # from the environment; ValueError when unconfigured
```
The stub `packages/tl-cli/src/tl_cli/extypes_quarantine.py` has the group, imports, helpers and docstrings that say exactly what to print. Replace each
`raise NotImplementedError("STUB (P0-I8-T26)")`. Do not change a signature or a printed string.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/extypes_quarantine.py` (the stub)
- `packages/tl-cli/src/tl_cli/extypes.py` (a finished group of the same shape: `_fail`, `_service_errors`, `_factory`)
- `docs/tickets/P0-I8/provided/b-test_cli_extypes_quarantine.py.txt` (the test to make pass)
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/extypes_quarantine.py` (replace the stub bodies)
- `packages/tl-cli/tests/test_cli_extypes_quarantine.py` (create: copy of the provided file, unchanged)
- `docs/reports/P0-I8/P0-I8-T26.md` (create: your report; commit it)

## Steps
1. `uv sync --all-packages`. Run every command from the repository root.
2. `cp docs/tickets/P0-I8/provided/b-test_cli_extypes_quarantine.py.txt packages/tl-cli/tests/test_cli_extypes_quarantine.py`. Do not edit it.
3. Fill in the four functions.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_extypes_quarantine.py -q
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 8 passed in `test_cli_extypes_quarantine.py`; the rest of `packages/tl-cli` still passes.

## Tests to add
- `packages/tl-cli/tests/test_cli_extypes_quarantine.py`: the provided file (empty report, a quarantined version with issues, a conflict with both hashes, a damaged body, recheck failing
  then restoring, a record with no body, no object store).

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Rules to remember (from the project's learnings)
- Ruff's line limit is 100 columns, including docstrings and comments. Write files with the Write or Edit tool, not shell heredocs. Never use `pkill -f`.
- Never name a module `types.py`. Run Python from the repository root.
- Commit as `P0-I8-T26: <summary>` with the report in the same commit. Delete the stub's `# ruff: noqa: F401` first line once ruff has no unused import left.

## Escalation triggers
- Stop and report *Blocked* if a docstring and the provided test disagree, if a function listed under Interfaces is missing or has another signature, or if you would have to touch a
  file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
