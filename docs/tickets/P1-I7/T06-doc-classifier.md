# P1-I7-T06 — The `doc_classifier` enricher and its golden set

Status: ready
Tier: haiku
Labels: core
Depends on: — (the frozen contract `tl_core/integration/contract.py` and its conformance helper `tests/contract/test_integration_contract.py` are in the tree)
Branch: `p1/i7a-t06-doc-classifier`

## Goal
The first enricher exists, and it is deterministic. `packages/tl-core/src/tl_core/integration/enrichers/doc_classifier.py` has the keyword tables and constants (final); the bodies of `words`, `_phrase`, `best_code`, `number_prefix`, `DocClassifier.accepts` and `DocClassifier.enrich` raise `NotImplementedError`. You implement them. One provided test file must pass; it runs the shared enricher contract checks, an evaluation over the 26 golden cases in `tests/golden/enrichment/doc_classifier.json` (final, read only) that fails below 0.8 accuracy on `doc_type`, and hostile-input cases. The test needs no database.

## Brief references (pasted)
> **Brief 18.9 Enrichment.** "Enrichers write back only into their own namespaced psets (`enrich.<enricher>.*`), proposed links, classifications and derived files. Each enrichment value carries provenance: enricher, version, model/prompt hash for AI, confidence, inputs (record version + file hash), and timestamp. Acceptance policy is set per property: `auto` (above a confidence threshold), `propose` (a person accepts it in a review queue), or `shadow`. Enrichment never overwrites authoritative fields."
>
> **ADR-0008 decision 8 (owner).** "Extraction uses stubs only ... No LLM call and no spend." So this enricher is a fixed keyword table: `model_ref` is `None`, there is no network and no model, and every result says so in its notes.
>
> **FANOUT D6.** "First enricher `doc_classifier`: deterministic. It reads the file facts (name, type, page count, title and author metadata) and the document title, proposes `doc_type` and `discipline` from a fixed keyword table checked against the sample company's code lists, and gives the confidence of the rule that matched. Golden set: at least 20 cases and an evaluation test that reports accuracy per property and fails below 0.8 on `doc_type`."
>
> **Hostile input.** A title and a file name come from people and from files. Read at most `MAX_TEXT_CHARS` characters of any text, match with plain comparisons of whole words (no regular expression on the text but the one word pattern), and never raise: a subject nothing matches is `unsupported`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-core/src/tl_core/integration/contract.py` (read only; abridged to what you use):
```python
ENRICH_MAX_VALUE_CHARS = 4_000

class RecordRef(BaseModel):
    id: str
    key: str | None = None
    record_type: str
    version: int | None = None
    seq: int | None = None

class EnrichmentFile(BaseModel):
    file_id: str
    filename: str
    content_type: str
    size: int
    sha256: str
    page_count: int | None = None
    title: str | None = None
    author: str | None = None

class EnrichmentSubject(BaseModel):
    record: RecordRef
    title: str
    status: str | None = None
    psets: dict[str, Any] = ...
    file: EnrichmentFile | None = None

class ProposedValue(BaseModel):
    property: str   # ^[a-z][a-z0-9_]{0,62}$
    value: EnrichedValue
    confidence: float   # 0.0 to 1.0

class EnrichmentResult(BaseModel):
    enricher: str
    enricher_version: str
    status: Literal["ok", "unsupported", "failed"]
    values: list[ProposedValue] = ...
    links: list[ProposedLink] = ...
    problems: list[Problem] = ...
    notes: list[str] = ...   # the shared check wants one note that says "ADR-0008"

@runtime_checkable
class Enricher(Protocol):
    name: str
    version: str
    model_ref: str | None
    def accepts(self, subject: EnrichmentSubject) -> bool: ...
    def enrich(self, subject: EnrichmentSubject) -> EnrichmentResult: ...
```
The stub you complete is `packages/tl-core/src/tl_core/integration/enrichers/doc_classifier.py`; each body has a STEPS comment.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/integration/enrichers/doc_classifier.py` (the file you edit)
- `packages/tl-core/src/tl_core/integration/contract.py` (the models above)
- `docs/tickets/P1-I7/provided/t06-test_doc_classifier.py.txt` (the test)
- `tests/golden/enrichment/doc_classifier.json` (the golden cases; read only)
- `tests/contract/test_integration_contract.py` (`check_enricher_contract`; read only)
- `docs/templates/haiku-report.md`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages, and again after the branch gains an entry point (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `packages/tl-core` (L-P1-I3-3: the stub's two lint-silencing header lines come out when you implement it).
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean (L-P1-I3-12).
- Commit your report at `docs/reports/P1-I7/P1-I7-T06.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7). `docs/templates/haiku-report.md` is the template (L-P1-I3B-6).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. **Known red on this branch:** `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails until workstream B adds its `Thread.*` catalog classes; it is not yours and not in any command below. Two job-action tests in `tests/integration/test_int_actions.py` are red until T02a lands; they are not yours and not in any command below.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line when you implement the stub.
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never change `schema/**`, `pyproject.toml`, anything under `generated/`, or `tl_core/integration/contract.py` (frozen).
- Do not run `just test` or `just test-parity` (they take an hour); run the scoped commands in *Acceptance*. The test uses no database fixture, so it runs once whatever `--adapters` says: this ticket has no Postgres variant (L-P1-I1-6).
- The test count below was counted from the provided file (`grep -c "^def test_"`); a parametrized test counts once per case (L-P0-I8A-8).

## Allowed paths
- `packages/tl-core/src/tl_core/integration/enrichers/doc_classifier.py` (edit)
- `packages/tl-core/tests/test_doc_classifier.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I7/P1-I7-T06.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t06-test_doc_classifier.py.txt` to `packages/tl-core/tests/test_doc_classifier.py`.
3. Implement the six bodies by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-core/tests/test_doc_classifier.py -q
uv run pytest tests/contract -q
```
Expected: `just check` clean; the 26 test functions of the provided file pass (accuracy on the golden set is printed: `doc_type` above 0.8); the contract tests pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Say the accuracy per property that the evaluation test printed.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if the test needs a change in `contract.py`, in the golden file or in any file outside *Allowed paths*.
- Do not change the keyword tables or the confidence constants: they are final. If you believe a table is wrong, say so under *Blocked*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
