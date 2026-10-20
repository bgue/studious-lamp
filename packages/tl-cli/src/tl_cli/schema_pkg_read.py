"""`tl schema package diff|classify|impact|test`: the reports of a package version (P1-I8-T05a1).

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
    `no base to compare with (first version)`. A later version always differs from its base (the
    version line at least), so an empty diff after `analyse` can only be a first version. A diff
    that was cut ends with the line `(diff cut)`.
    """
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        detail = views.package_detail(uow.conn(), ref)
    if not detail.diff:
        if detail.classification is None:
            typer.echo(f"not analysed: run tl schema package analyse {ref}")
        else:
            typer.echo("no base to compare with (first version)")
        return
    typer.echo(detail.diff.rstrip("\n"))
    if detail.diff_truncated:
        typer.echo("(diff cut)")


def classify(ctx: typer.Context, ref: _Ref, as_json: _Json = False) -> None:
    """Print the classification report that `analyse` stored.

    Lines: `classification <name@version>`, `base <name@version or ->`, `worst <class>`,
    `auto-adoptable yes|no`, `blocks submit yes|no`, `counts <class> <n>, ...` (classes that
    occur, in the order additive, deprecation, renaming, promotion, constraining, breaking,
    forbidden), then one line per change: `<class>  <path>  <detail>`. With no report:
    `not analysed: run tl schema package analyse <ref>`.
    """
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        detail = views.package_detail(uow.conn(), ref)
    report = detail.classification
    if report is None:
        typer.echo(f"not analysed: run tl schema package analyse {ref}")
        return
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
        return
    counts = [f"{cls} {report.counts[cls]}" for cls in _CLASS_ORDER if report.counts.get(cls)]
    typer.echo(f"classification {detail.key}")
    typer.echo(f"base {cell(report.base, 200)}")
    typer.echo(f"worst {report.worst}")
    typer.echo(f"auto-adoptable {'yes' if report.auto_adoptable else 'no'}")
    typer.echo(f"blocks submit {'yes' if report.blocks_submit else 'no'}")
    typer.echo(f"counts {', '.join(counts) or '-'}")
    for change in report.changes:
        typer.echo(f"{change.cls}  {change.path}  {change.detail}")


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
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        detail = views.package_detail(uow.conn(), ref)
        if project is None:
            report = detail.impact
        else:
            report, _, _ = analysis.project_impact(
                uow.conn(), project, detail.package, detail.version
            )
    if report is None:
        typer.echo(f"not analysed: run tl schema package analyse {ref}")
        return
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
        return
    counts = [f"{section} {n}" for section, n in report.counts.items()]
    typer.echo(f"impact {report.scope}")
    typer.echo(f"digest {report.digest}")
    typer.echo(f"counts {', '.join(counts) or '-'}")
    for entry in report.entries:
        typer.echo(
            f"{entry.section}  {entry.target}  {entry.change}  {cell(entry.count)}  {entry.detail}"
        )
    if report.truncated:
        typer.echo("(cut at 500 entries)")


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
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        result = views.sample_test(uow.conn(), ref, sample)
    if as_json:
        typer.echo(result.model_dump_json(indent=2))
        return
    typer.echo(
        f"tested {result.package}  scope {result.scope}  sample {result.sample}  "
        f"checked {result.checked}"
    )
    typer.echo(f"newly nonconformant {result.newly_nonconformant}")
    typer.echo(f"newly warning {result.newly_warning}")
    typer.echo(f"fixed {result.fixed}")
    for example in result.examples:
        typer.echo(f"{example.key}  {example.path}  {example.rule}  {example.message}")


def register(app: typer.Typer) -> None:
    """Add the four commands to `tl schema package`."""
    app.command("diff")(diff)
    app.command("classify")(classify)
    app.command("impact")(impact)
    app.command("test")(test)
