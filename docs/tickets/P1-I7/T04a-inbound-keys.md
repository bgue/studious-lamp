# P1-I7-T04a — Key resolution for inbound mappings

Status: ready
Tier: haiku
Labels: core
Depends on: — (the frozen contract is in the tree)
Branch: `p1/i7a-t04a-inbound-keys`

## Goal
A mapped command can name a record by its human key. `packages/tl-core/src/tl_core/integration/keys.py` has the constants, the fixed problems, the `KeyLookup` protocol and `_Refused` (final); `shown`, `parse_ref` and `resolve_keys` raise `NotImplementedError`. You implement them. One provided test file must pass. The test needs no database: the lookup is a fake.

## Brief references (pasted)
> **Brief 18.5 Inbound integration.** "Each endpoint has signature verification, a declarative mapping (JSONata) from the foreign payload to one or more commands, key resolution (external ID -> record via `external_ids` or number patterns), dry-run mode, an error queue with manual fix-and-retry."
>
> **FANOUT D4 (worker).** "The worker resolves `{"$key": ...}` by record key and type within the endpoint's scope (not found or ambiguous: `key_not_found`; `external_ids` is not built in Phase 1), sets the server fields, and runs all commands in one unit of work through the runner as the service actor."
>
> **Why the details matter.** The payload comes from outside. A mapping can name any key the payload holds, so: the lookup is the caller's and is already limited to the endpoint's scope; no record and several records give the same answer (so a sender cannot probe which keys exist); a key shown in a message is cut and printable; and the walk over the arguments is bounded in values, depth and distinct keys, and refused (never cut) beyond them.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-core/src/tl_core/integration/contract.py` (read only; abridged to what you use):
```python
INBOUND_MAX_JSON_DEPTH = 32
#: In a mapped command's ``args``: ``{"$key": "47-1234-W012"}`` or ``{"$key": {"type":
#: "core.Record", "key": "47-1234-W012"}}`` is replaced by that record's id.
KEY_REF_MARKER = "$key"

class Problem(BaseModel):
    code: str      # ^[a-z][a-z0-9_]{0,63}$
    message: str   # at most 500 characters

class RecordRef(BaseModel):
    id: str
    key: str | None = None
    record_type: str
    version: int | None = None
    seq: int | None = None
```
The stub you complete is `packages/tl-core/src/tl_core/integration/keys.py`; each body has a STEPS comment.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/integration/keys.py` (the file you edit)
- `packages/tl-core/src/tl_core/integration/contract.py` (the models above)
- `docs/tickets/P1-I7/provided/t04a-test_keys.py.txt` (the test)
- `docs/templates/haiku-report.md`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages, and again after the branch gains an entry point (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `packages/tl-core` (L-P1-I3-3: the stub's two lint-silencing header lines come out when you implement it).
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean (L-P1-I3-12).
- Commit your report at `docs/reports/P1-I7/P1-I7-T04a.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7). `docs/templates/haiku-report.md` is the template (L-P1-I3B-6).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. **Known red on this branch:** `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails until workstream B adds its `Thread.*` catalog classes; it is not yours and not in any command below.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line when you implement the stub.
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never change `schema/**`, `pyproject.toml`, anything under `generated/`, or `tl_core/integration/contract.py` (frozen).
- Do not run `just test` or `just test-parity` (they take an hour); run the scoped commands in *Acceptance*. The test uses no database fixture, so it runs once whatever `--adapters` says: this ticket has no Postgres variant (L-P1-I1-6).
- The test count below was counted from the provided file (`grep -c "^def test_"`); a parametrized test counts once per case (L-P0-I8A-8).

## Allowed paths
- `packages/tl-core/src/tl_core/integration/keys.py` (edit)
- `packages/tl-core/tests/test_inbound_keys.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I7/P1-I7-T04a.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t04a-test_keys.py.txt` to `packages/tl-core/tests/test_inbound_keys.py`.
3. Implement the three bodies by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-core/tests/test_inbound_keys.py -q
```
Expected: `just check` clean; the provided test file passes (32 cases from 19 test functions).

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if the test needs a change in `contract.py` or any file outside *Allowed paths*.
- This code sits on the inbound security path: do not add a convenience (a looser key form, a fallback lookup, a retry) that the STEPS do not say.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
