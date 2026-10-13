"""`tl doc import`: preview and apply a legacy document register (brief 9 M1, 29.6; P1-I2-T12d).

The command reads a CSV export of the incumbent DMS with a mapping template, compares it with the
project's register and prints what would happen; with `--apply` it registers the new documents.
Reading, comparing and writing are the module's (`tl_mod_documents.imports`); this command parses
options and prints. It registers documents only: the old register's revision, status and date are a
note in the description, and the revisions come with the P1-I8 legacy loaders. It is registered by
`tl_cli.main` as `tl doc import`.

STUB (P1-I2-T12e): the bodies of _preview and import_documents raise NotImplementedError; their
signatures, options, docstrings and the helpers are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_documents.imports.apply import apply_plan
from tl_mod_documents.imports.diff import plan_import
from tl_mod_documents.imports.mapping import (
    MappingError,
    load_mapping,
    read_file_text,
    read_rows,
)
from tl_mod_documents.imports.model import ImportPlan

from tl_cli.doc import _DEFAULT_ACTOR, _Actor, _fail, _Project, _service_errors
from tl_cli.session import require_admin


def _preview(plan: ImportPlan) -> None:
    """The counts line, then one line per new, existing and invalid row.

    ``new=9  exists=1  invalid=7`` and then, in this order: ``+ <number>  <type or ->  <title>``
    for each new row, ``= <number>`` for each number the project already has, and ``! line <n>:
    <problems joined by "; ">`` for each invalid row.
    """
    # STEPS
    # 1. counts = plan.counts(); print "  ".join(f"{name}={counts[name]}" for name in counts).
    # 2. For each row of plan.new print f"+ {row.number}  {row.doc_type or '-'}  {row.title}".
    # 3. For each number of plan.exists print f"= {number}".
    # 4. For each row of plan.invalid print f"! line {row.line}: {'; '.join(row.problems)}".
    raise NotImplementedError


def import_documents(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="The CSV file to import.")],
    project: _Project,
    mapping: Annotated[
        Path, typer.Option("--mapping", help="The mapping template (YAML) for this file.")
    ],
    apply: Annotated[
        bool, typer.Option("--apply", help="Register the new documents (admin). Default: preview.")
    ] = False,
    skip_invalid: Annotated[
        bool, typer.Option("--skip-invalid", help="Import the valid rows and leave the others out.")
    ] = False,
    job: Annotated[
        str | None, typer.Option("--job", help="Names the import in the history (default: file).")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Compare a DMS register export with the project's documents; with --apply, register them."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; job = job or file.stem. When apply
    #    is true call require_admin(db) first (a bulk registration is an admin's decision).
    # 2. `with _service_errors():` `try:` template = load_mapping(mapping); text =
    #    read_file_text(file); rows = read_rows(text, template); `except MappingError as exc:`
    #    _fail(str(exc)). read_file_text refuses a file over 5 MiB and words a read error as
    #    "<name>: cannot read file: ..."; read_rows refuses more than 1000 rows. Both come before
    #    any unit of work is opened.
    # 3. Print f"import {template.name} {file.name} into project {project}".
    # 4. `with open_uow(db, readonly=not apply) as uow:` plan = plan_import(uow.conn(), scope,
    #    rows); _preview(plan). When not apply: print "dry run: nothing written; add --apply to
    #    write" and return. Otherwise results = apply_plan(uow, scope, plan, actor=actor, job=job,
    #    skip_invalid=skip_invalid).
    # 5. Print f"applied {job}: registered={len(results)}  skipped={len(plan.exists) +
    #    len(plan.invalid)}".
    raise NotImplementedError
