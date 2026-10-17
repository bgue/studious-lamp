"""`tl derive open|start|content|ls|jobs|cancel|worker`: run the pipeline (P1-I3-T14b).

A derived document is the data of one revision of a document checked against a schema. `open`
makes it, `content` attaches a CSV or XLSX a person prepared, `start` queues the extraction job,
`worker` runs the queue, and `ls` and `jobs` show where things stand. Starting, cancelling and
opening are open to any signed-in person; nothing here publishes. The rules are the module's
(`tl_mod_documents.derivation`); these commands parse options and print.
"""

from __future__ import annotations

import hashlib
import mimetypes
import time
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.files.service import CompleteUpload, RegisterUpload
from tl_mod_documents import registry
from tl_mod_documents.derivation import views
from tl_mod_documents.derivation.derived import (
    CancelJob,
    OpenDerivedDocument,
    StartExtraction,
    handle_cancel_job,
    handle_open_derived_document,
    handle_start_extraction,
)
from tl_mod_documents.derivation.worker import build_worker, requeue_orphans
from tl_mod_documents.names import SLOT_CONTENT

from tl_cli.derive_support import (
    SOURCE,
    Actor,
    Project,
    acting,
    cell,
    configure_files,
    fail,
    service_errors,
)

app = typer.Typer(help="Open, feed, start and run derived documents.", no_args_is_help=True)

_Ref = Annotated[str, typer.Argument(help="A derived document's key or id.")]
_CHUNK = 1024 * 1024


def _revision_id(db: DbTarget, scope: str, number: str, code: str) -> str:
    with open_uow(db, readonly=True) as uow:
        document = registry.find_document(uow.conn(), scope, number)
        found = (
            registry.find_revision(uow.conn(), document.id, code) if document is not None else None
        )
    if found is None:
        fail(f"no revision {code!r} of document {number!r} in {scope}")
    return found.id


@app.command("open")
def open_derived(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    revision: Annotated[str, typer.Argument(help="The revision code.")],
    schema: Annotated[str, typer.Option("--schema", help="Schema code, or code@version.")],
    project: Project,
    actor: Actor = None,
) -> None:
    """Open the derived document of a revision for a schema. Prints `opened <key> <id>`.

    Opening twice is harmless: the second call finds the first.
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    code, _, semver = schema.partition("@")
    revision_id = _revision_id(db, scope, number, revision)
    with service_errors(), open_uow(db) as uow:
        made = handle_open_derived_document(
            uow,
            OpenDerivedDocument(
                actor=acting(db, actor),
                source=SOURCE,
                scope=scope,
                revision_id=revision_id,
                schema_code=code,
                schema_semver=semver or None,
            ),
        )
    typer.echo(f"opened {made.key} {made.stream_id}")


@app.command("content")
def content(
    ctx: typer.Context,
    ref: _Ref,
    path: Annotated[
        Path, typer.Argument(help="The CSV or XLSX to attach.", exists=True, dir_okay=False)
    ],
    project: Project,
    actor: Actor = None,
) -> None:
    """Attach a CSV or XLSX as the data of a derived document. Prints `attached <name> <file id>`.

    Each file you attach is kept; `start` reads the newest one.
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    service = configure_files()
    who = acting(db, actor)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with service_errors(), open_uow(db) as uow:
        derived = views.find_derived(uow.conn(), scope, ref)
        ticket = service.register_upload(
            uow,
            RegisterUpload(
                actor=who,
                source=SOURCE,
                scope=scope,
                record_id=derived.id,
                slot=SLOT_CONTENT,
                filename=path.name,
                content_type=media,
                size=path.stat().st_size,
                sha256=digest.hexdigest(),
            ),
        )
        complete = CompleteUpload(actor=who, source=SOURCE, scope=scope, upload_id=ticket.upload_id)
        if ticket.exists:
            done = service.complete_upload(uow, complete)
        else:
            with path.open("rb") as source_file:
                done = service.complete_upload(uow, complete, source_file)
    typer.echo(f"attached {path.name} {done.file_id}")


@app.command("start")
def start(
    ctx: typer.Context,
    project: Project,
    ref: Annotated[str | None, typer.Argument(help="A derived document's key or id.")] = None,
    doc: Annotated[
        str | None, typer.Option("--doc", help="With --rev and --schema: open it.")
    ] = None,
    rev: Annotated[str | None, typer.Option("--rev", help="The revision code.")] = None,
    schema: Annotated[str | None, typer.Option("--schema", help="The schema code.")] = None,
    extractor: Annotated[str | None, typer.Option("--extractor", help="Extractor name.")] = None,
    file_id: Annotated[
        str | None, typer.Option("--file-id", help="A content file to read.")
    ] = None,
    actor: Actor = None,
) -> None:
    """Queue an extraction job. Prints `queued <job key> for <derived key>`.

    Name the derived document (REF), or a revision and a schema (--doc, --rev, --schema). The file
    read is the newest content file, else the revision's PDF, else its native file. A worker
    (`tl derive worker`) runs the job.
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    by_revision = doc is not None and rev is not None and schema is not None
    if (ref is None) == (not by_revision):
        fail("give a derived document, or --doc with --rev and --schema, and not both")
    configure_files()
    revision_id: str | None = None
    if by_revision:
        assert doc is not None and rev is not None
        revision_id = _revision_id(db, scope, doc, rev)
    with service_errors(), open_uow(db) as uow:
        derived_id = views.find_derived(uow.conn(), scope, ref).id if ref is not None else None
        made = handle_start_extraction(
            uow,
            StartExtraction(
                actor=acting(db, actor),
                source=SOURCE,
                scope=scope,
                derived_id=derived_id,
                revision_id=revision_id,
                schema_code=schema if by_revision else None,
                extractor=extractor,
                file_id=file_id,
            ),
        )
        derived_key = views.job_view(uow.conn(), scope, made.stream_id).derived_key
    typer.echo(f"queued {made.key} for {derived_key}")


@app.command("ls")
def list_derived(
    ctx: typer.Context,
    project: Project,
    state: Annotated[str | None, typer.Option("--state", help="For example Valid.")] = None,
    doc: Annotated[str | None, typer.Option("--doc", help="A source document number.")] = None,
) -> None:
    """List derived documents, newest first.

    One line each: `<key>  <state>  pass <n>  rows <n or ->  errors <n or ->  <schema>@<version>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.derived_summaries(uow.conn(), f"project:{project}", state=state, document=doc)
    for d in found:
        typer.echo(
            f"{d.key}  {d.state}  pass {d.content_rev}  rows {cell(d.row_count)}  "
            f"errors {cell(d.error_count)}  {d.schema_code}@{d.schema_version}"
        )


@app.command("jobs")
def jobs(
    ctx: typer.Context,
    project: Project,
    state: Annotated[
        str | None, typer.Option("--state", help="queued, running, failed, ...")
    ] = None,
    derived: Annotated[str | None, typer.Option("--derived", help="Key or id.")] = None,
) -> None:
    """List processing jobs, newest first.

    One line each: `<job key>  <kind>  <state>  attempt <n>/<max>  <derived key>  <error or ->`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.job_views(uow.conn(), f"project:{project}", state=state, derived=derived)
    for j in found:
        typer.echo(
            f"{j.key}  {j.kind}  {j.state}  attempt {j.attempt}/{j.max_attempts}  "
            f"{j.derived_key}  {cell(j.error_message, 60)}"
        )


@app.command("cancel")
def cancel(
    ctx: typer.Context,
    job: Annotated[str, typer.Argument(help="The job's id.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why.")] = "cancelled",
    actor: Actor = None,
) -> None:
    """Cancel a queued job. Prints `cancelled <job key>`. A running job cannot be cancelled."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with service_errors(), open_uow(db) as uow:
        made = handle_cancel_job(
            uow,
            CancelJob(
                actor=acting(db, actor), source=SOURCE, scope=scope, job_id=job, reason=reason
            ),
        )
    typer.echo(f"cancelled {made.key}")


@app.command("worker")
def worker(
    ctx: typer.Context,
    once: Annotated[bool, typer.Option("--once", help="Run what is queued, then exit.")] = False,
    requeue: Annotated[
        bool, typer.Option("--requeue", help="First queue again jobs a restore lost.")
    ] = False,
    idle: Annotated[
        float, typer.Option("--idle", min=0.1, help="Seconds to wait when idle.")
    ] = 2.0,
    timeout: Annotated[
        float, typer.Option("--timeout", min=1, help="Seconds an extractor may run.")
    ] = 60.0,
    factory: Annotated[
        str | None,
        typer.Option("--factory", help="module:function that returns the extractors (tests)."),
    ] = None,
) -> None:
    """Run the job queue.

    Prints `ran <job id> <kind> <outcome>` per job and `worker done: ran=<n>`. The extractors are
    found by entry point; `--factory module:function` names another source (tests).

    Without --once it keeps waiting for jobs until interrupted (Ctrl-C ends it cleanly).
    """
    db: DbTarget = ctx.obj
    service = configure_files()
    with service_errors():
        if requeue:
            typer.echo(f"requeued {requeue_orphans(db)}")
        ran = 0
        with build_worker(db, service, timeout_s=timeout, factory=factory) as made:
            try:
                while True:
                    result = made.runner.run_once()
                    if result is None:
                        if once:
                            break
                        time.sleep(idle)
                        continue
                    typer.echo(f"ran {result.job_id} {result.kind} {result.outcome}")
                    ran += 1
            except KeyboardInterrupt:
                pass
    typer.echo(f"worker done: ran={ran}")
