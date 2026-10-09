# P0-I2-T01 — Package loader and registry

Status: merged
Tier: haiku
Labels: core
Depends on: —
Branch: `p0/i2a-t01-package-registry`

## Goal
`tl_schema.registry` reads schema package files (`schema/fixtures/*.yaml`) into `PackageDoc` objects, stores them in a
`PackageRegistry`, and answers which packages a scope adopts: the company set, or a project's pinned set. Today the module
exists as a stub whose bodies raise `NotImplementedError`; after this ticket every function works and a provided test file passes.

## Brief references (pasted)
> **27.2 Schema layers.** Company packages: standard psets, code lists, enforcement ... authored in the schema registry (YAML), weekly-ish. Project packages: extensions of standard psets, project psets, project value lists, crosswalks, tightened rules; any time.
> **27.4 Adoption** is per project: additive versions can auto-adopt; constraining versions need the project data manager to adopt. **Projects pin versions**; drift from the latest is visible in the conformance dashboard.
> **27.3 Effective schema.** For each project: core + modules + company packages (pinned versions adopted by the project) + project packages (pinned versions) = effective schema.

Package file shape (see the three fixtures in `schema/fixtures/`): `package`, `version`, `kind` (`company`, `extension`, `project`),
`project` (for the last two), `depends` (company package name to exact version), `code_lists`, `psets`, `extends` (list of
`ref: "co.acme.engineering@3.2.0#valve_data"` entries). The pydantic models are already written (`tl_schema/packages.py`); you do not change them.

Adoption rules (these are the specification of `adopted`):
- `company`: the latest version of every company package (kind `company`).
- `project:<id>`: (1) for each package name that has documents whose `project == <id>`, the highest version of that name;
  (2) every company package named in `depends` of those documents, at exactly the pinned version; (3) the latest version of every other company package.
  Two pins of one company package at different versions raise `PackageError`. A project with no documents gets the company set.
- Result order: company documents, then extension documents, then project documents, each group sorted by package name.
- Versions compare as numbers (`3.10.0` is higher than `3.9.1`); use `version_tuple` from `tl_schema.packages`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I2/provided/*.py.txt` and are copied into the test tree by you (a failing test file on the base would break `just check` on every other branch). Do not edit the copied test.
- `ruff` enforces 100 columns in code, docstrings and comments; pyright is strict for `packages/tl-schema/src`. `just check` also type-checks tests.
- `uv` prints "UV_NATIVE_TLS is deprecated" on every call. Ignore it. If imports fail in a fresh worktree run `uv sync --all-packages` once.
- Piping `just check` into `tail` hides its exit code; read the last lines and the exit status separately (`just check > /tmp/check.out 2>&1; echo $?`).

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-schema/src/tl_schema/registry.py  (stub: replace each `raise NotImplementedError` body; keep names, signatures, docstrings)
SCHEMA_DIR_ENV = "TL_SCHEMA_DIR"
DEFAULT_SCHEMA_DIR: Path = Path(__file__).resolve().parents[4] / "schema" / "fixtures"

class PackageError(ValueError): ...

def default_schema_dir() -> Path: ...          # ALREADY IMPLEMENTED; leave as is
def parse_package(text: str, *, source: str = "<string>") -> PackageDoc: ...
    # YAML text -> PackageDoc. PackageError whose message STARTS WITH `source` for: invalid YAML (yaml.YAMLError),
    # a document that is not a mapping, or a pydantic ValidationError (one entry per error: "<dotted loc>: <message>", joined by "; ").
def load_package(path: Path) -> PackageDoc: ...    # read UTF-8, parse with source=str(path); file name must be "<package>@<version>.yaml" else PackageError
class PackageRegistry:
    def __init__(self, docs: Iterable[PackageDoc] = ()) -> None: ...
    @classmethod
    def from_directory(cls, directory: Path) -> PackageRegistry: ...   # sorted *.yaml via load_package; missing directory -> PackageError; empty -> empty registry
    def add(self, doc: PackageDoc) -> None: ...        # same package@version twice -> PackageError
    def names(self) -> list[str]: ...                  # sorted
    def versions(self, name: str) -> list[str]: ...    # ascending by version_tuple; [] when unknown
    def get(self, name: str, version: str) -> PackageDoc: ...    # PackageError when absent
    def latest(self, name: str) -> PackageDoc: ...               # PackageError when the name is unknown
    def projects(self) -> list[str]: ...               # sorted distinct `project` values of the stored documents
    def adopted(self, scope: str) -> list[PackageDoc]: ...       # rules above; scope not "company"/"project:<id>" -> ValueError
    def check(self) -> None: ...                       # one PackageError listing every problem, joined by "; "
    def fingerprint(self) -> str: ...                  # sha256 hex of the sorted documents (see below)
```
`check()` problems (each one string naming the document by `doc.key()`):
- a `depends` entry whose `name@version` is not stored: `"<doc>: depends on <name>@<version>, not found"`;
- a `depends` entry that is stored but not of kind `company`: `"<doc>: depends on <dep>, which is not a company package"`;
- an `extends` entry (`entry.target()` gives `(package, version, pset)`) whose package version is not a stored company document: `"<doc>: extends <ref>, but no such company package"`; or whose document has no such pset: `"<doc>: extends <ref>, but <base> has no pset <pset>"`.

`fingerprint()`: for every stored document sorted by `doc.key()`, the text `f"{doc.key()}\n{canonical_dump(doc.model_dump(mode='json'))}"`; join all with `"\n"`; return `hashlib.sha256(text.encode("utf-8")).hexdigest()`. `canonical_dump` is in `tl_schema.effective`.

Models you read (already in `tl_schema/packages.py`): `PackageDoc` has `package`, `version`, `kind`, `project`, `depends: dict[str, str]`,
`psets`, `extends: list[ExtendsDef]`, `.key()` returning `"name@version"`; `ExtendsDef.ref` and `.target() -> (package, version, pset)`; `version_tuple(str) -> tuple[int, int, int]`.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-schema/src/tl_schema/registry.py`
- `packages/tl-schema/src/tl_schema/packages.py`
- `packages/tl-schema/tests/conftest.py`
- `docs/tickets/P0-I2/provided/test_registry.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-schema/src/tl_schema/registry.py` (edit: implement the stub)
- `packages/tl-schema/tests/test_registry.py` (create: `cp` of the provided file, byte for byte)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_registry.py.txt packages/tl-schema/tests/test_registry.py`
2. Implement the stub bodies. Parse with `yaml.safe_load`; catch `yaml.YAMLError` and `pydantic.ValidationError`. Keep `default_schema_dir` as is. Store documents in a `dict[tuple[str, str], PackageDoc]`.
3. Run the acceptance commands.

## Acceptance
```
uv run pytest packages/tl-schema/tests/test_registry.py -q
just check
just test
diff docs/tickets/P0-I2/provided/test_registry.py.txt packages/tl-schema/tests/test_registry.py
```
Expected: all tests pass (28 in the provided file), `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file. Do not add, change or skip tests in it.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus the output of the four acceptance commands (decisive lines) and the test count.

## Escalation triggers
- Stop and report *Blocked* if a provided test cannot pass without changing `packages.py`, `conftest.py` or the test itself.
- Stop if `pyright` strict needs a `type: ignore` you cannot avoid by annotating the YAML result as `Any`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
