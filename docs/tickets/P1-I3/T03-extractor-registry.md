# P1-I3-T03 — Extractor registry and the guarded call of a plugin

Status: ready
Tier: haiku
Labels: core
Depends on: — (the frozen contract `tl_core/derivation/types.py` and the fake extractor `tl_core/derivation/testing.py` are in the tree)
Branch: `p1/i3a-t03-extractor-registry`

## Goal
The pipeline finds extractor plugins through the entry-point group `throughline.extractors`, picks one for a source file, and calls it without trusting it. `packages/tl-core/src/tl_core/derivation/registry.py` has the exception classes, the process-wide state, `use_extractors`, `forget_loaded` and two helpers (final); the bodies of `_discover`, `load_extractors`, `choose`, `contract_problem` and `run_extraction` raise `NotImplementedError`. You implement them. One provided test file must pass. The test needs no database.

## Brief references (pasted)
> **Brief 9 M1.** "Processing jobs are pluggable (extractor plugins) and runnable from TUI, API, or MCP." The extractor packages are written by another team in parallel and are found only by entry point; the pipeline never imports them by name.
>
> **Contract (ADR-0008 decision 8, FANOUT D4).** Extractors are pure: no ledger, no network. A bad file is a result with `status="failed"` and problems, never an exception. Bounds: 50 MiB per source, 20 000 rows, 200 columns, 10 000 characters per cell; bigger is refused, never truncated.
>
> **Fail loud (ADR-0010 decision 3, the same pattern as `tl_core.modules`).** A plugin that is installed and does not load is an error at first use, never a silent gap. A failed load is not cached as an empty registry.
>
> **Do not trust a plugin.** A result that breaks the contract must not reach validation or publication: `run_extraction` replaces it with a `failed` result that names the rule. A plugin's exception text may hold a path or a value from the file, so only the exception *type* goes into a message.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-core/src/tl_core/derivation/types.py` (read only):
```python
EXTRACTOR_ENTRY_POINT = "throughline.extractors"
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_ROWS = 20_000
MAX_COLUMNS = 200
MAX_CELL_CHARS = 10_000
ExtractionStatus = Literal["ok", "metadata_only", "unsupported", "failed"]
Cell = str | None

class SourceFile(BaseModel):
    file_id: str
    filename: str
    content_type: str
    size: int
    sha256: str
    source_ref: str

class FileMetadata(BaseModel):
    content_type: str
    size: int
    sha256: str
    page_count: int | None = None
    sheet_names: list[str] | None = None
    title: str | None = None
    author: str | None = None
    created: str | None = None
    modified: str | None = None
    producer: str | None = None

class ExtractionProblem(BaseModel):
    code: str
    message: str
    row: int | None = None

class ExtractionResult(BaseModel):
    extractor: str
    extractor_version: str
    status: ExtractionStatus
    metadata: FileMetadata | None = None
    sheet: str | None = None
    columns: list[str] = ...
    rows: list[dict[str, Cell]] = ...      # keys are exactly `columns`, in order
    profiles: list[ColumnProfile] = ...
    problems: list[ExtractionProblem] = ...
    notes: list[str] = ...

@runtime_checkable
class Extractor(Protocol):
    name: str
    version: str
    def accepts(self, source: SourceFile) -> bool: ...
    def extract(self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]) -> ExtractionResult: ...
```
The stub you complete is `packages/tl-core/src/tl_core/derivation/registry.py`; each body has a STEPS comment.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/derivation/registry.py` (the file you edit)
- `packages/tl-core/src/tl_core/derivation/types.py`
- `packages/tl-core/src/tl_core/derivation/testing.py` (the fake extractors and the entry-point callables the test uses)
- `packages/tl-core/src/tl_core/modules.py` (the same pattern for modules: `_discover`, `load_modules`, `use_modules`)
- `docs/tickets/P1-I3/provided/t03-test_derivation_registry.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `packages/tl-core`.
- The provided file lives under `docs/tickets/P1-I3/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I3/P1-I3-T03.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line when you implement the stub.
- The test count below was counted from the provided file (`grep -c "^def test_"` gives 24); one test is parametrized over 10 cases, so pytest reports 33 (L-P0-I8A-8). This test uses no database fixture, so it runs once whatever `--adapters` says: this ticket has no Postgres variant (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never change `schema/**` or anything under `generated/`.
- Do not run `just test-parity` or `just test` (they take an hour); run the scoped commands in *Acceptance*.

## Allowed paths
- `packages/tl-core/src/tl_core/derivation/registry.py` (edit)
- `packages/tl-core/tests/test_derivation_registry.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I3/P1-I3-T03.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I3/provided/t03-test_derivation_registry.py.txt` to `packages/tl-core/tests/test_derivation_registry.py`.
3. Implement the five bodies by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-core/tests/test_derivation_registry.py -q
uv run pytest tests/contract -q
```
Expected: `just check` clean; 33 cases pass (24 test functions); the contract tests pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if the test needs a change in `types.py`, `testing.py` or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
