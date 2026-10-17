"""`tl derive schema register|ls|show|retire`: document schemas for derived data (P1-I3-T14a).

A document schema says what one row of derived data must look like (a JSON Schema), which column
is the key, and optionally how rows become tags or documents (the publish mapping). Registering
and retiring are admin acts. The rules are the module's
(`tl_mod_documents.derivation.schemas`); these commands parse options and print.

STUB (P1-I3-T14a): the bodies of list_schemas, register, retire, show raise NotImplementedError;
their signatures, options, docstrings and the helpers are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the lint-silencing lines.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
# pyright: reportUnusedImport=false, reportUnusedVariable=false

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from tl_adapters.db import DbTarget, open_uow
from tl_mod_documents.derivation import rows, views
from tl_mod_documents.derivation.schemas import (
    RegisterDocumentSchema,
    RetireDocumentSchema,
    handle_register_document_schema,
    handle_retire_document_schema,
)
from tl_mod_documents.errors import SchemaNotFoundError

from tl_cli.derive_support import (
    SOURCE,
    Actor,
    OptProject,
    acting,
    cell,
    fail,
    scope_of,
    service_errors,
)
from tl_cli.session import require_admin

app = typer.Typer(help="Register, list, show and retire document schemas.", no_args_is_help=True)

_Company = Annotated[bool, typer.Option("--company", help="The company's schema (all projects).")]
_Ref = Annotated[str, typer.Argument(help="A schema code, or code@version.")]


def _load(path: Path) -> dict[str, Any]:
    """The YAML or JSON file as a mapping, or `error:` for anything else."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        fail(f"cannot read {path.name}: {type(exc).__name__}")
    if not isinstance(data, dict):
        fail(f"{path.name} must hold one mapping (code, semver, title, json_schema, ...)")
    return {str(k): v for k, v in data.items()}  # pyright: ignore[reportUnknownVariableType]


@app.command("register")
def register(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="YAML or JSON with the schema.", exists=True)],
    project: OptProject = None,
    company: _Company = False,
    actor: Actor = None,
) -> None:
    """Register a schema version from FILE (admin).

    The file holds `code`, `semver`, `title`, `json_schema` and optionally `key_column`,
    `target_kind` (tags or documents), `mapping`, `sample`, `doc_types`, `description` and
    `mapping_notes`. Prints `registered <code>@<semver> <scope>`; every problem of a refused
    schema is listed on stderr.
    """
    # STEPS (P1-I3-T14a)
    # 1. db = ctx.obj; scope = scope_of(project, company) (the helper exits with the message when
    #    both or neither is given).
    # 2. require_admin(db), then fields = _load(file).
    # 3. Inside `with service_errors(), open_uow(db) as uow:` call
    #    handle_register_document_schema(uow, RegisterDocumentSchema(actor=acting(db, actor),
    #    source=SOURCE, scope=scope, **fields)).
    # 4. Print `registered <result.key> <scope>`.
    raise NotImplementedError


@app.command("ls")
def list_schemas(
    ctx: typer.Context,
    project: OptProject = None,
    all_versions: Annotated[bool, typer.Option("--all", help="Include retired.")] = False,
) -> None:
    """List the schemas a project sees (the company's, plus its own with --project).

    One line per version: `<code>@<semver>  <scope>  <target or ->  <key column or ->
    <active|retired>  <title>`.
    """
    # STEPS (P1-I3-T14a)
    # 1. db = ctx.obj; scope = f"project:{project}" if project else "company".
    # 2. Inside `with service_errors(), open_uow(db, readonly=True) as uow:` found =
    #    views.schema_summaries(uow.conn(), scope, active_only=not all_versions).
    # 3. Print one line per item exactly as the docstring says; state is `active` or `retired`;
    #    title through cell(item.title, 60).
    raise NotImplementedError


@app.command("show")
def show(
    ctx: typer.Context,
    ref: _Ref,
    project: OptProject = None,
    json_out: Annotated[
        bool, typer.Option("--json", help="Print the full schema as JSON.")
    ] = False,
) -> None:
    """Show one schema: its fields, its columns and whether it can be published.

    Prints `schema <key>`, `scope`, `title`, `target`, `key column`, `status`, `content hash`
    lines, then `column <name> <type> required|optional` for each property.
    """
    # STEPS (P1-I3-T14a)
    # 1. Read found = views.schema_view(uow.conn(), scope, ref) as in list_schemas (readonly,
    #    service_errors).
    # 2. With --json print json.dumps(found.model_dump(mode="json"), indent=2, sort_keys=True)
    #    and return.
    # 3. Otherwise print the lines `schema <key>`, `scope`, `title`, `target`, `key column`,
    #    `status`, `content hash` (first 12 characters); `-` for none; status is `active` or
    #    `retired: <reason or ->`.
    # 4. Then one `column <name> <type> required|optional` line per property of
    #    found.json_schema["properties"] (type is the property's `type`, or `any`).
    raise NotImplementedError


@app.command("retire")
def retire(
    ctx: typer.Context,
    ref: Annotated[str, typer.Argument(help="code@version of the version to retire.")],
    reason: Annotated[str, typer.Option("--reason", help="Why (kept in the history).")],
    project: OptProject = None,
    company: _Company = False,
    actor: Actor = None,
) -> None:
    """Retire a schema version (admin). Documents that named it keep it; new work cannot pick it."""
    # STEPS (P1-I3-T14a)
    # 1. db = ctx.obj; scope = scope_of(project, company); require_admin(db).
    # 2. Split ref at `@`; with no version call fail("name the version: code@version").
    # 3. Inside `with service_errors(), open_uow(db) as uow:` found =
    #    rows.find_schema(uow.conn(), scope, code, semver); if None raise
    #    SchemaNotFoundError(f"no document schema {ref!r} in {scope}").
    # 4. Call handle_retire_document_schema(uow, RetireDocumentSchema(actor=acting(db, actor),
    #    source=SOURCE, scope=scope, stream_id=found.id, reason=reason)); print `retired
    #    <found.key> <scope>`.
    raise NotImplementedError
