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
