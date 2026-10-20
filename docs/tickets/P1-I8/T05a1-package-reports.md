# P1-I8-T05a1 — `tl schema package diff|classify|impact|test`: the reports of a package version

Status: ready
Tier: haiku
Labels: cli, schema-registry
Depends on: P1-I8-S2, P1-I8-S5 and P1-I8-T03 on `p1/i8` (the registry, its views and the impact report are merged); no other ticket
Branch: `p1/i8-t05a1-package-reports`

## Goal
A schema steward who has drafted a package version reads, from the command line, what the version changes. `packages/tl-cli/src/tl_cli/schema_pkg_read.py` holds four commands of the group `tl schema package`: `diff` (the text diff against the version below), `classify` (the classification report: what kind of change each difference is), `impact` (what the change touches, for the package or, with `--project`, for a project that pins it) and `test` (a sample of the records you may read, re-checked against the schema the draft makes). `register` already adds the four to the group; the four functions raise `NotImplementedError` today. You write their bodies by the STEPS comments and the output formats in their docstrings, so the one provided test file passes. The reads are the registry module's (`tl_mod_schemareg.views`, `tl_mod_schemareg.analysis`); the commands call them and print. T05a2 adds publish and adopt, which take the digest that `impact --project` prints.

## Brief references (pasted)
> **Brief 27.8 (workbench and CLI).** *`tl schema` CLI:* `lint`, `diff`, `classify`, `impact --project P123`, `test --sample 1000`, `publish`, `adopt`, `crosswalk`, `promote`, `export-git` / `import-git`.
>
> **Brief 27.4.** A `SchemaPackage` is itself a ledgered record: name, namespace, semver, owner, dependencies, content (LinkML YAML), changelog, **classification report, impact report**, approvals. *Adoption is per project: constraining or renaming versions need the project data manager to adopt after reviewing their project-specific impact report.*
>
> **Increment 8 decisions (FANOUT D1, D4).** The classes of change are `additive`, `deprecation`, `renaming`, `promotion`, `constraining`, `breaking` and `forbidden`; `breaking` and `forbidden` cannot be submitted. Adoption of anything but an additive version needs the SHA-256 of the project impact report the caller read; `impact --project` prints it.

### Specification
- Every command needs a signed-in person (`require_session(db)`); none writes anything. Open a unit of work with `open_uow(db, readonly=True)` inside `service_errors()`, so a package that does not exist is `error: no schema package '<ref>'` on stderr and exit code 1 (the module raises it; you add nothing).
- A `ref` is a package id or `name@version`; `views.package_detail(conn, ref)` takes either.
- The base of a diff is fixed by `tl schema package analyse`: before it, `detail.diff` is empty and `detail.classification` is `None`. After it, an empty diff means a first version.
- Fields are separated by two spaces. The exact lines of each command are in its docstring in the stub; the provided test checks them.
- `--json` prints the whole report with `model_dump_json(indent=2)` and nothing else.

### Learnings that apply
> **L-P1-I3-3.** A stub also fails pyright on unused imports, so the stub file carries `# ruff: noqa: F401` and a `# pyright: reportUnusedImport=false` line. Remove both with the STEPS comments when the body is written, and remove every import the finished file does not use.
>
> **L-P1-I4-9.** A first `just check` in a fresh worktree takes over two minutes: run it with a 600 000 ms timeout (or in the background and wait). Run `uv run ruff format <file>` first, because the format check rewrites a hand-wrapped line.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns.
>
> **L-P0-I6C-8.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`.
>
> **L-P1-I8-5.** Never delete anything under `/tmp/pytest-of-root`: other agents use it. Give each pytest run `--basetemp=/tmp/pt-<ticket>` and remove only that directory after you have read the exit code.
>
> **L-P1-I4-16.** A read command is easy to get wrong in the part the test does not touch (a fixed value, the other half of a condition, the order of fields). Print exactly the fields and the order in the docstring; the provided test checks them with values that differ from each other.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/schema_pkg_read.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""`tl schema package diff|classify|impact|test`: the reports of a package version (P1-I8-T05a1).

STUB: this file is the interface P1-I8-T05a1 implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it. `register` is complete.

None of these writes anything. The reads are the module's (`tl_mod_schemareg.views` and
`analysis`); these commands parse options and print one line per fact, with two spaces between
fields. A package that does not exist is the module's error (`error: no schema package ...` on
stderr, exit 1). Every command needs a signed-in person; the reports are the ones stored by
`tl schema package analyse`, except `impact --project` and `test`, which are made now.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schemareg import analysis, views

from tl_cli.derive_support import cell, service_errors
from tl_cli.session import require_session

_Ref = Annotated[str, typer.Argument(help="A package id or name@version, for example acme@1.1.0.")]
_Json = Annotated[bool, typer.Option("--json", help="The whole report as JSON.")]
_CLASS_ORDER = (
    "additive",
    "deprecation",
    "renaming",
    "promotion",
    "constraining",
    "breaking",
    "forbidden",
)


def diff(ctx: typer.Context, ref: _Ref) -> None:
    """Print the unified text diff of the package against the version below it.

    The base is the version `analyse` compared with, so before `analyse` it prints
    `not analysed: run tl schema package analyse <ref>`; a first version prints
    `no base to compare with (first version)`. A diff that was cut ends with the line
    `(diff cut)`.
    """
    # STEPS
    # 1. db = ctx.obj; call require_session(db).
    # 2. Inside `with service_errors(), open_uow(db, readonly=True) as uow:` read
    #    views.package_detail(uow.conn(), ref).
    # 3. No diff text: print the `not analysed` line when detail.classification is None, else
    #    `no base to compare with (first version)`; return.
    # 4. Otherwise print the diff without its trailing newline; when detail.diff_truncated is
    #    true print `(diff cut)` after it.
    raise NotImplementedError("STEPS: see the comments")


def classify(ctx: typer.Context, ref: _Ref, as_json: _Json = False) -> None:
    """Print the classification report that `analyse` stored.

    Lines: `classification <name@version>`, `base <name@version or ->`, `worst <class>`,
    `auto-adoptable yes|no`, `blocks submit yes|no`, `counts <class> <n>, ...` (classes that
    occur, in the order additive, deprecation, renaming, promotion, constraining, breaking,
    forbidden), then one line per change: `<class>  <path>  <detail>`. With no report:
    `not analysed: run tl schema package analyse <ref>`.
    """
    # STEPS
    # 1. Same opening as diff: require_session, then views.package_detail(...).
    # 2. report = detail.classification; when None print the `not analysed` line and return.
    # 3. With --json print report.model_dump_json(indent=2) and return.
    # 4. Otherwise print the six header lines in the order of the docstring, then one line per
    #    change. `counts` lists only classes with a non-zero count, in _CLASS_ORDER, joined by
    #    ", " as `<class> <n>`; with none it is `counts -`. Use cell() for a value that may be
    #    None (the base).
    raise NotImplementedError("STEPS: see the comments")


def impact(
    ctx: typer.Context,
    ref: _Ref,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Make the report for adopting this version in a project."),
    ] = None,
    as_json: _Json = False,
) -> None:
    """Print an impact report: what the change touches.

    Without `--project` it is the report `analyse` stored (`not analysed: ...` when none). With
    `--project P` it is made now for pinning this version in project P; its digest is the value
    `tl schema adopt --impact-sha256` takes. Lines: `impact <scope>`, `digest <sha256>`,
    `counts <section> <n>, ...`, then one line per entry:
    `<section>  <target>  <change>  <count or ->  <detail>`, and `(cut at 500 entries)` last when
    the report was cut.
    """
    # STEPS
    # 1. Same opening as diff: require_session, then views.package_detail(...).
    # 2. Without --project the report is detail.impact. With --project it is the first item of
    #    analysis.project_impact(uow.conn(), project, detail.package, detail.version), called
    #    inside the same unit of work (it returns a tuple of three; take the first).
    # 3. No report: print the `not analysed` line and return. With --json print
    #    report.model_dump_json(indent=2) and return.
    # 4. Otherwise print `impact <scope>`, `digest <digest>`, `counts <section> <n>, ...`
    #    (`counts -` when empty; report.counts is a dict in section order), one line per entry in
    #    the format of the docstring (cell() for the count), and `(cut at 500 entries)` last
    #    when report.truncated.
    raise NotImplementedError("STEPS: see the comments")


def test(
    ctx: typer.Context,
    ref: _Ref,
    sample: Annotated[
        int, typer.Option("--sample", min=1, max=views.MAX_SAMPLE, help="Records to re-check.")
    ] = views.DEFAULT_SAMPLE,
    as_json: _Json = False,
) -> None:
    """Re-check a sample of the records you may read against the schema the draft makes.

    Lines: `tested <name@version>  scope <scope>  sample <n>  checked <n>`,
    `newly nonconformant <n>`, `newly warning <n>`, `fixed <n>`, then one line per example:
    `<key>  <path>  <rule>  <message>`.
    """
    # STEPS
    # 1. Same opening as diff: require_session; then result = views.sample_test(uow.conn(), ref,
    #    sample) inside the unit of work.
    # 2. With --json print result.model_dump_json(indent=2) and return.
    # 3. Otherwise print the four header lines in the order of the docstring and one line per
    #    result.examples item.
    raise NotImplementedError("STEPS: see the comments")


def register(app: typer.Typer) -> None:
    """Add the four commands to `tl schema package`."""
    app.command("diff")(diff)
    app.command("classify")(classify)
    app.command("impact")(impact)
    app.command("test")(test)
```

From `tl_mod_schemareg.views` (read-only):
```python
MAX_SAMPLE = 5000
DEFAULT_SAMPLE = 1000

class PackageSummary(BaseModel):  # frozen
    id: str
    key: str
    scope: str
    package: str
    version: str
    kind: str
    project: str | None
    title: str | None
    state: str
    worst_class: str | None
    analysed: bool
    drafted_by: str
    submitted_by: str | None
    approved_by: str | None
    published_at: str | None
    changelog: str | None

class PackageDetail(PackageSummary):
    content: str
    content_sha256: str
    base_ref: str | None
    classification: ClassificationReport | None   # None until `analyse` has run
    impact: ImpactReport | None                   # None until `analyse` has run
    impact_sha256: str | None
    lint: list[LintIssueView]
    diff: str            # unified diff against the base ("" for a first version or before analyse)
    diff_truncated: bool

class SampleExample(BaseModel):  # frozen
    key: str
    path: str
    rule: str
    message: str

class SampleTestView(BaseModel):  # frozen
    package: str
    scope: str
    sample: int          # the size asked for
    checked: int
    newly_nonconformant: int
    newly_warning: int
    fixed: int
    examples: list[SampleExample]

def package_detail(conn: Connection, ref: str) -> PackageDetail: ...
def sample_test(conn: Connection, ref: str, sample: int = DEFAULT_SAMPLE) -> SampleTestView: ...
```

From `tl_mod_schemareg.analysis` (read-only):
```python
def project_impact(
    conn: Connection, project: str, package: str, version: str
) -> tuple[ImpactReport, EffectiveSchema, EffectiveSchema]:
    """What pinning ``package@version`` does to ``project``'s schema and records.

    Returns the report and the two schemas (before, after). Raises ``InvalidSchemaPackageError``
    when the pin does not compose.
    """
```

From `tl_mod_schemareg.impact_types` and `tl_schema.classify` (read-only):
```python
class ImpactEntry(BaseModel):  # frozen
    section: Section      # records, columns, views, mappings, reports or mcp_schemas
    target: str
    change: str
    count: int | None = None
    detail: str

class ImpactReport(BaseModel):  # frozen
    scope: str
    old_hash: str | None
    new_hash: str
    changed_paths: tuple[str, ...]
    entries: tuple[ImpactEntry, ...]
    counts: dict[str, int]      # entries per section that has any, in section order
    truncated: bool             # entries were cut at 500
    @property
    def digest(self) -> str: ...   # SHA-256 of the canonical JSON of the report

class Change(BaseModel):  # frozen
    cls: ChangeClass      # additive, deprecation, renaming, promotion, constraining, breaking, forbidden
    code: str
    path: str
    detail: str
    relaxing: bool = False
    review: bool = False

class ClassificationReport(BaseModel):  # frozen
    base: str | None      # name@version of the older version; None for a new package
    target: str
    changes: tuple[Change, ...]
    counts: dict[str, int]
    worst: ChangeClass
    auto_adoptable: bool
    blocks_submit: bool
    handling: dict[str, str]
    digest: str
```

From `tl_cli.derive_support` and `tl_cli.session` (read-only): `service_errors()` is a context manager that turns a service failure into `error: <message>` on stderr and exit code 1; `cell(value, width=40)` is `-` for `None` or an empty value and the text cut to `width` characters otherwise; `require_session(db)` exits with `error: not signed in` when nobody is.
```text

```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/schema_pkg_read.py` (the stub)
- `docs/tickets/P1-I8/provided/t05a1-test_cli_schema_pkg_read.py.txt`
- `packages/tl-cli/src/tl_cli/schema_pkg.py` (the group these commands join; `show` there prints the same reports in short)
- `packages/tl-modules/schemareg/src/tl_mod_schemareg/views.py`
- `packages/tl-cli/src/tl_cli/xer_read.py` (another read module in the same style)
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/schema_pkg_read.py` (modify: the four function bodies, the stub paragraph and directives, the unused imports)
- `packages/tl-cli/tests/test_cli_schema_pkg_read.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I8/P1-I8-T05a1.md` (create: your report; commit it)

## Steps
1. Copy the provided test to `packages/tl-cli/tests/test_cli_schema_pkg_read.py`. Do not edit the copy (it is ruff-clean and pyright-clean as provided).
2. Run it once; all eleven cases fail against the stub.
3. Write the four bodies by their STEPS and docstrings. Remove the STUB paragraph, the two directive lines at the top, every STEPS comment and every `raise NotImplementedError` line. Remove imports the finished file does not use. Leave `register` and the helper names as they are.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-cli
uv run pytest packages/tl-cli/tests/test_cli_schema_pkg_read.py packages/tl-cli/tests/test_cli_schema_package.py -q --adapters sqlite,postgres --basetemp=/tmp/pt-t05a1
just check
```
Expected: `27 passed, 1 skipped` for the first two files on both adapters (eleven cases in the provided file and three in the base test file, each once per adapter; the base file skips its sign-in case on Postgres); `just check` is clean (run it with a 600 000 ms timeout). Remove `/tmp/pt-t05a1` after you have read the exit code.

## Tests to add
None beyond the provided file. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T05a1.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
