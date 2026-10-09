"""The `tl schema` group: hash, lint and validate schema packages (brief 27.8).

Each subcommand loads the package directory (``--dir``, env ``TL_SCHEMA_DIR``, default
``schema/fixtures``), makes one call into ``tl_schema`` and prints. No rules live here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from tl_schema.compile import SchemaCompileError
from tl_schema.compose import compose
from tl_schema.linkml_render import build_view
from tl_schema.lint import lint_documents
from tl_schema.packages import PackageDoc
from tl_schema.registry import PackageError, PackageRegistry, default_schema_dir

app = typer.Typer(help="Inspect and check schema packages.", no_args_is_help=True)

DirOption = Annotated[
    Path | None,
    typer.Option(
        "--dir", envvar="TL_SCHEMA_DIR", help="Package directory (default schema/fixtures)."
    ),
]


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _schema_errors() -> Iterator[None]:
    try:
        yield
    except (PackageError, SchemaCompileError) as exc:
        _fail(str(exc))


def _registry(directory: Path | None) -> PackageRegistry:
    return PackageRegistry.from_directory(
        directory if directory is not None else default_schema_dir()
    )


def _scope(target: str) -> str:
    if target == "company" or target.startswith("project:"):
        return target
    return f"project:{target}"


@app.command("hash")
def hash_command(
    target: Annotated[
        str, typer.Argument(help="`company`, a project id such as P123, or project:P123.")
    ],
    directory: DirOption = None,
) -> None:
    """Print the content hash of the effective schema of a scope."""
    with _schema_errors():
        registry = _registry(directory)
        scope = _scope(target)
        if scope.startswith("project:"):
            project = scope.removeprefix("project:")
            if project not in registry.projects():
                _fail(f"unknown project {project!r}")
        typer.echo(compose(registry.adopted(scope), scope).hash)


@app.command("lint")
def lint(directory: DirOption = None) -> None:
    """Lint every package version; exit 1 when there is an error."""
    with _schema_errors():
        registry = _registry(directory)
        docs: list[PackageDoc] = [
            registry.get(name, version)
            for name in registry.names()
            for version in registry.versions(name)
        ]
        issues = lint_documents(docs)
    for issue in issues:
        typer.echo(f"{issue.severity} {issue.rule} {issue.package} {issue.path} {issue.message}")
    errors = sum(1 for issue in issues if issue.severity == "error")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    typer.echo(f"{errors} errors, {warnings} warnings")
    if errors > 0:
        raise typer.Exit(code=1)


@app.command("validate")
def validate(
    targets: Annotated[
        list[str] | None, typer.Argument(help="Scopes to check (default: all).")
    ] = None,
    directory: DirOption = None,
) -> None:
    """Check cross-package references, compile each scope and render it as LinkML."""
    with _schema_errors():
        registry = _registry(directory)
        registry.check()
        if targets:
            scopes = [_scope(target) for target in targets]
        else:
            scopes = ["company", *(f"project:{project}" for project in registry.projects())]
    failed = False
    for scope in scopes:
        try:
            schema = compose(registry.adopted(scope), scope)
            build_view(schema)
        except (PackageError, SchemaCompileError) as exc:
            typer.echo(f"error: {scope}: {exc}", err=True)
            failed = True
            continue
        typer.echo(f"ok {scope} {schema.hash[:12]}")
    if failed:
        raise typer.Exit(code=1)
