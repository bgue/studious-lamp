"""`tl form` (V3-F1a): the general-form verbs, one call into the module each.

The hook ref ``tl_mod_forms.cli:form_app`` names the group ``form``. Verbs: ``ls`` (templates, or
submissions with ``--submissions``), ``show`` (a template version, as JSON Schema or SurveyJS on
request, or one submission), ``publish`` (a template file: draft, then publish), ``fill`` (save a
draft), ``drafts`` (the signed-in person's own), ``submit`` (a draft or a template with answers) and
``review`` (accept, return or void a submission).

Reads use the signed-in viewer (``session_viewer``) after the ``forms.view`` word; writes run the
command as the actor, read through the actor's own viewer, as ``tl qr`` does. A hidden submission,
another person's draft and an unknown key all print the same `error: no submission <ref>`.
Answers are given as ``--answer q1=yes`` (typed by the template's question: a number is a number,
``multi`` and ``photo`` take comma-separated values) or ``--answers-file`` (JSON: a list of
``{q, value, note}`` or an object ``{q: value}``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, open_uow
from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    cell,
    fail,
    scope_of,
    service_errors,
)
from tl_cli.session import require_command, session_viewer
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.confidentiality import Viewer
from tl_core.forms.jsonschema import to_json_schema
from tl_core.forms.surveyjs import surveyjs_unsupported, to_surveyjs
from tl_core.services.commands import Command

from tl_mod_forms import MODULE, views
from tl_mod_forms.commands import (
    AcceptFormSubmission,
    DraftFormTemplate,
    PublishFormTemplate,
    ReturnFormSubmission,
    SaveFormDraft,
    SubmitForm,
    VoidFormSubmission,
)
from tl_mod_forms.handlers.review import (
    handle_accept_form_submission,
    handle_return_form_submission,
    handle_void_form_submission,
)
from tl_mod_forms.handlers.submission import handle_save_form_draft, handle_submit_form
from tl_mod_forms.handlers.template import (
    handle_draft_form_template,
    handle_publish_form_template,
)
from tl_mod_forms.names import (
    DRAFT,
    PUBLISHED,
    SUBMISSION_STATES,
    TEMPLATE_STATES,
    VIEW,
)

form_app = typer.Typer(no_args_is_help=True)

COMPANY = "company"
PROJECTIONS = ("jsonschema", "surveyjs")
ACTIONS = ("accept", "return", "void")
#: One text for a missing, hidden and foreign-draft submission (the ref is the caller's own).
MSG_NO_SUBMISSION = "no submission"
MSG_NO_TEMPLATE = "no template"
LIST_LIMIT = 200
ANSWER = typer.Option("--answer", help="An answer as q=value; repeat for more.")
ANSWERS_FILE = typer.Option("--answers-file", help="A JSON file of answers.")
OptProject = Annotated[
    str | None, typer.Option("--project", help="Project ID; scope project:<ID>.")
]


def _model[C: Command](model: type[C], **fields: Any) -> C:
    """The command model with ``fields``; a value the model refuses is a usage error (exit 2)."""
    try:
        return model(**fields)
    except ValidationError as exc:
        raise typer.BadParameter(str(exc.errors()[0]["msg"])) from None


def _require_view(conn: Connection, actor: str, scope: str) -> None:
    try:
        require_word(
            conn,
            holder_for_actor(conn, actor),
            scope=scope,
            module=MODULE,
            word=normalise_word(VIEW),
            what=VIEW,
        )
    except ForbiddenError as exc:
        fail(f"forbidden: {exc}")


def _read(db: DbTarget, actor: str, scope: str, call: Any) -> Any:
    """Run ``call(conn, viewer)`` read-only as the signed-in viewer, after ``forms.view``."""
    who = acting(db, actor)
    viewer = session_viewer(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        _require_view(uow.conn(), who, scope)
        return call(uow.conn(), viewer)


# --- answers --------------------------------------------------------------------------------


def _typed(field: dict[str, Any], raw: str) -> Any:
    """``raw`` as the value its question takes; a value that does not fit stays text (the rules
    then refuse it with their own message)."""
    kind = field.get("kind")
    if kind == "number":
        try:
            number = float(raw)
        except ValueError:
            return raw
        return int(number) if number.is_integer() and "." not in raw else number
    if kind in ("multi", "photo"):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return raw


def _parse_answers(
    fields: list[dict[str, Any]], pairs: list[str], file: Path | None
) -> dict[str, dict[str, Any]]:
    """The answers by question id, from the file first, then the ``q=value`` options."""
    by_id = {str(f["id"]): f for f in fields}
    found: dict[str, dict[str, Any]] = {}
    if file is not None:
        try:
            loaded = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            fail(f"cannot read answers from {file}")
        if isinstance(loaded, dict):
            for q, value in loaded.items():  # pyright: ignore[reportUnknownVariableType]
                found[str(q)] = {"q": str(q), "value": value, "note": None}  # pyright: ignore[reportUnknownArgumentType]
        elif isinstance(loaded, list):
            for item in loaded:  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(item, dict) or "q" not in item:
                    fail("an answers file holds {q, value, note} objects or one {q: value} object")
                q = str(item["q"])  # pyright: ignore[reportUnknownArgumentType]
                found[q] = {"q": q, "value": item.get("value"), "note": item.get("note")}  # pyright: ignore[reportUnknownMemberType]
        else:
            fail("an answers file holds a list or an object")
    for pair in pairs:
        q, sep, raw = pair.partition("=")
        if not sep or not q:
            raise typer.BadParameter("must be q=value", param_hint="'--answer'")
        found[q] = {"q": q, "value": _typed(by_id.get(q, {}), raw), "note": None}
    return found


# --- lookups --------------------------------------------------------------------------------


def _template_row(
    conn: Connection, key: str, viewer: Viewer, version: int | None
) -> views.TemplateRow:
    """The template ``key`` at ``version`` (default: the latest Published, else the latest)."""
    page = views.template_list(conn, key=key, limit=views.MAX_LIMIT, viewer=viewer)
    rows = sorted(page.rows, key=lambda r: r.version or 0)
    if version is not None:
        rows = [r for r in rows if r.version == version]
    else:
        published = [r for r in rows if r.state == PUBLISHED]
        rows = published or rows
    if not rows:
        fail(f"{MSG_NO_TEMPLATE} {key}")
    return rows[-1]


def _template(
    conn: Connection, ref: str, viewer: Viewer, version: int | None = None
) -> views.TemplateDetail:
    row = _template_row(conn, ref, viewer, version)
    detail = views.template_detail(conn, row.id, viewer=viewer)
    if detail is None:
        fail(f"{MSG_NO_TEMPLATE} {ref}")
    return detail


def _submission(conn: Connection, scope: str, ref: str, viewer: Viewer) -> views.SubmissionDetail:
    detail = views.submission_detail(conn, scope, ref, viewer=viewer)
    if detail is None:
        fail(f"{MSG_NO_SUBMISSION} {ref}")
    return detail


def _titles(conn: Connection, viewer: Viewer) -> dict[str, views.TemplateRow]:
    """Template id to row, for the templates the viewer reads."""
    return {r.id: r for r in views.template_list(conn, limit=views.MAX_LIMIT, viewer=viewer).rows}


def _subject_id(uow_conn: Connection, scope: str, key: str | None, viewer: Viewer) -> str | None:
    if key is None:
        return None
    visible, extra = cf.not_hidden_each("r.id", viewer)
    row = uow_conn.execute(
        text(
            "SELECT r.id FROM cur_core_record r WHERE r.scope = :scope AND r.key = :key "
            f"AND r.voided = :no AND {visible}"
        ),
        {"scope": scope, "key": key, "no": False, **extra},
    ).first()
    if row is None:
        fail(f"no record {key}")
    return str(row.id)


# --- ls, show -------------------------------------------------------------------------------


@form_app.command("ls")
def form_ls(
    ctx: typer.Context,
    project: OptProject = None,
    submissions: Annotated[
        bool, typer.Option("--submissions", help="List the project's submissions, not templates.")
    ] = False,
    state: Annotated[str | None, typer.Option("--state", help="Only this state.")] = None,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most rows (default 200).")
    ] = LIST_LIMIT,
    actor: Actor = DEV_ACTOR,
) -> None:
    """List the templates, or with `--submissions --project ID` the submissions.

    `form templates: <n>`, then `<key>  v<n>  <state>  <fields>  <title>`; or `form submissions:
    <n>`, then `<key>  <state>  <template>  <author>  <submitted>`. Hidden rows are not listed.
    """
    db: DbTarget = ctx.obj
    if not submissions:
        if state is not None and state not in TEMPLATE_STATES:
            raise typer.BadParameter(
                f"must be one of {', '.join(TEMPLATE_STATES)}", param_hint="'--state'"
            )

        def templates(conn: Connection, viewer: Viewer) -> views.Page[views.TemplateRow]:
            return views.template_list(conn, state=state, limit=limit, viewer=viewer)

        page = _read(db, actor, COMPANY, templates)
        typer.echo(f"form templates: {page.total}")
        for t in page.rows:
            typer.echo(
                f"{cell(t.key, 12)}  v{t.version}  {t.state}  {t.field_count}  {cell(t.title, 60)}"
            )
        return
    scope = scope_of(project)
    if state is not None and state not in SUBMISSION_STATES:
        raise typer.BadParameter(
            f"must be one of {', '.join(SUBMISSION_STATES)}", param_hint="'--state'"
        )

    def listed(
        conn: Connection, viewer: Viewer
    ) -> tuple[views.Page[views.SubmissionRow], dict[str, views.TemplateRow]]:
        return (
            views.submission_list(conn, scope, state=state, limit=limit, viewer=viewer),
            _titles(conn, viewer),
        )

    subs, names = _read(db, actor, scope, listed)
    typer.echo(f"form submissions: {subs.total}")
    for s in subs.rows:
        tpl = names.get(s.template_id or "")
        typer.echo(
            f"{cell(s.key or s.id, 26)}  {s.state}  {cell(tpl.key if tpl else None, 12)}  "
            f"{cell(s.author, 30)}  {cell(s.submitted_on, 10)}"
        )


@form_app.command("show")
def form_show(
    ctx: typer.Context,
    ref: Annotated[
        str, typer.Argument(help="A template key (TPL-0001) or a submission key or draft id.")
    ],
    project: OptProject = None,
    version: Annotated[
        int | None, typer.Option("--version", min=1, help="A template version.")
    ] = None,
    projection: Annotated[
        str | None, typer.Option("--as", help="jsonschema or surveyjs: print the form as JSON.")
    ] = None,
    submission: Annotated[
        bool, typer.Option("--submission", help="REF is a submission (needs --project).")
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Show a template version (its questions), or with `--submission` one submission."""
    db: DbTarget = ctx.obj
    if projection is not None and projection not in PROJECTIONS:
        raise typer.BadParameter(f"must be one of {', '.join(PROJECTIONS)}", param_hint="'--as'")
    if submission:
        scope = scope_of(project)

        def one(
            conn: Connection, viewer: Viewer
        ) -> tuple[views.SubmissionDetail, views.TemplateDetail | None]:
            found = _submission(conn, scope, ref, viewer)
            tpl = views.template_detail(conn, found.row.template_id or "", viewer=viewer)
            return found, tpl

        detail, tpl = _read(db, actor, scope, one)
        r = detail.row
        typer.echo(f"{r.key or r.id}  {r.state}  {cell(tpl.row.title if tpl else None, 60)}")
        typer.echo(f"author {cell(r.author, 60)}  submitted {cell(r.submitted_on, 10)}")
        if r.reviewed_by:
            typer.echo(f"reviewed by {r.reviewed_by} on {cell(r.reviewed_on, 10)}")
        if detail.review_note:
            typer.echo(f"note {detail.review_note}")
        if detail.void_reason:
            typer.echo(f"void reason {detail.void_reason}")
        for a in detail.answers:
            typer.echo(f"{a.get('q')}  {json.dumps(a.get('value'), ensure_ascii=False)}")
        return

    def tpl_of(conn: Connection, viewer: Viewer) -> views.TemplateDetail:
        return _template(conn, ref, viewer, version)

    found = _read(db, actor, COMPANY, tpl_of)
    row = found.row
    fmt = row.format_version or 2
    if projection == "jsonschema":
        typer.echo(json.dumps(to_json_schema(found.fields, fmt), indent=2, sort_keys=True))
        return
    if projection == "surveyjs":
        model = {
            "model": to_surveyjs(found.fields, fmt),
            "unsupported": surveyjs_unsupported(found.fields),
        }
        typer.echo(json.dumps(model, indent=2, sort_keys=True))
        return
    typer.echo(f"{row.key}  v{row.version}  {row.state}  {row.title}")
    typer.echo(f"questions: {len(found.fields)}  answer class: {row.answer_class or 'internal'}")
    for f in found.fields:
        need = "required" if f.get("required") else "optional"
        typer.echo(f"{f['id']}  {f['kind']}  {need}  {cell(f.get('text'), 70)}")


# --- publish --------------------------------------------------------------------------------


@form_app.command("publish")
def form_publish(
    ctx: typer.Context,
    path: Annotated[
        Path, typer.Argument(help="A template file (YAML or JSON: title, fields, ...).")
    ],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Draft a template from a file and publish it. Prints `published <key> v<n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        fail(f"cannot read a template from {path}")
    if not isinstance(loaded, dict) or "title" not in loaded or "fields" not in loaded:
        fail("a template file holds a mapping with title and fields")
    body: dict[str, Any] = {
        k: v
        for k, v in loaded.items()  # pyright: ignore[reportUnknownVariableType]
        if k
        in (
            "title",
            "format_version",
            "fields",
            "bound_record_type",
            "answer_class",
            "intake",
            "purpose",
            "accepts_as",
        )
        and v is not None
    }
    with service_errors(), open_uow(db) as uow:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        with cf.use_viewer(viewer):
            draft = _model(DraftFormTemplate, actor=who, source=SOURCE, scope=COMPANY, **body)
            require_command(uow, draft)
            made = handle_draft_form_template(uow, draft)
            publish = _model(
                PublishFormTemplate,
                actor=who,
                source=SOURCE,
                scope=COMPANY,
                template_id=made.stream_id,
            )
            require_command(uow, publish)
            done = handle_publish_form_template(uow, publish)
            row = views.template_detail(uow.conn(), made.stream_id, viewer=viewer)
    number = row.row.version if row is not None else 1
    typer.echo(f"published {done.key} v{number}")


# --- fill, drafts, submit -------------------------------------------------------------------


def _answers_for(
    conn: Connection,
    scope: str,
    target: str,
    viewer: Viewer,
    pairs: list[str],
    file: Path | None,
) -> tuple[str | None, str | None, str | None, int | None, list[dict[str, Any]]]:
    """For a template key or a draft id: (template id, draft id, subject, version, answers)."""
    if target.startswith("TPL-"):
        tpl = _template(conn, target, viewer)
        if tpl.row.state != PUBLISHED:
            fail("that template is not published")
        given = _parse_answers(tpl.fields, pairs, file)
        return tpl.row.id, None, None, None, list(given.values())
    found = _submission(conn, scope, target, viewer)
    if found.row.state not in (DRAFT, "Returned"):
        fail(f"a form that is {found.row.state} cannot be filled")
    tpl = views.template_detail(conn, found.row.template_id or "", viewer=viewer)
    fields = tpl.fields if tpl else []
    merged = {str(a["q"]): a for a in found.answers}
    merged.update(_parse_answers(fields, pairs, file))
    return None, found.row.id, found.row.subject_id, found.row.version, list(merged.values())


def _fill(
    db: DbTarget,
    verb: str,
    target: str,
    project: str | None,
    pairs: list[str],
    file: Path | None,
    subject: str | None,
    actor: str,
) -> None:
    who = acting(db, actor)
    scope = scope_of(project)
    with service_errors(), open_uow(db) as uow:
        conn = uow.conn()
        viewer = cf.viewer_for_actor(conn, who)
        with cf.use_viewer(viewer):
            template_id, draft_id, kept_subject, version, answers = _answers_for(
                conn, scope, target, viewer, pairs, file
            )
            named = _subject_id(conn, scope, subject, viewer) if subject else kept_subject
            model: Any = SaveFormDraft if verb == "fill" else SubmitForm
            handler: Any = handle_save_form_draft if verb == "fill" else handle_submit_form
            cmd = _model(
                model,
                actor=who,
                source=SOURCE,
                scope=scope,
                template_id=template_id,
                draft_id=draft_id,
                subject_id=named,
                answers=answers,
                expected_version=version,
            )
            require_command(uow, cmd)
            result = handler(uow, cmd)
    if verb == "fill":
        typer.echo(f"saved {result.stream_id}")
    else:
        typer.echo(f"submitted {result.key or result.stream_id}")


@form_app.command("fill")
def form_fill(
    ctx: typer.Context,
    target: Annotated[
        str, typer.Argument(help="A published template key (TPL-0001) or a draft id.")
    ],
    project: Project,
    answer: Annotated[list[str] | None, ANSWER] = None,
    answers_file: Annotated[Path | None, ANSWERS_FILE] = None,
    subject: Annotated[
        str | None, typer.Option("--subject", help="The key of the record the form is about.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Save a draft (answers may be incomplete). Prints `saved <draft id>`; give the id again to
    continue it. The draft is yours alone until you submit it."""
    _fill(ctx.obj, "fill", target, project, answer or [], answers_file, subject, actor)


@form_app.command("submit")
def form_submit(
    ctx: typer.Context,
    target: Annotated[
        str, typer.Argument(help="A published template key (TPL-0001) or a draft id.")
    ],
    project: Project,
    answer: Annotated[list[str] | None, ANSWER] = None,
    answers_file: Annotated[Path | None, ANSWERS_FILE] = None,
    subject: Annotated[
        str | None, typer.Option("--subject", help="The key of the record the form is about.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Submit a form: answers must be complete. Prints `submitted <number>`; the number is taken
    now. With a draft id the saved answers are used, and `--answer` changes some of them."""
    _fill(ctx.obj, "submit", target, project, answer or [], answers_file, subject, actor)


@form_app.command("drafts")
def form_drafts(
    ctx: typer.Context,
    project: Project,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most rows (default 200).")
    ] = LIST_LIMIT,
    actor: Actor = DEV_ACTOR,
) -> None:
    """List your own drafts: `form drafts: <n>`, then `<id>  <template>  <saves>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def mine(
        conn: Connection, viewer: Viewer
    ) -> tuple[views.Page[views.SubmissionRow], dict[str, views.TemplateRow]]:
        return (
            views.submission_list(conn, scope, state=DRAFT, author=who, limit=limit, viewer=viewer),
            _titles(conn, viewer),
        )

    page, names = _read(db, actor, scope, mine)
    typer.echo(f"form drafts: {page.total}")
    for s in page.rows:
        tpl = names.get(s.template_id or "")
        typer.echo(
            f"{s.id}  {cell(tpl.key if tpl else None, 12)}  "
            f"{cell(tpl.title if tpl else None, 40)}  saves {s.draft_saves or 0}"
        )


# --- review ---------------------------------------------------------------------------------


@form_app.command("review")
def form_review(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The submission key.")],
    action: Annotated[str, typer.Argument(help="accept, return or void.")],
    project: Project,
    note: Annotated[
        str | None,
        typer.Option("--note", help="The review note (needed to return) or the void reason."),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Accept, return or void a submitted form. The person who filled it may not review it."""
    db: DbTarget = ctx.obj
    if action not in ACTIONS:
        raise typer.BadParameter(f"must be one of {', '.join(ACTIONS)}", param_hint="'ACTION'")
    who = acting(db, actor)
    scope = scope_of(project)
    with service_errors(), open_uow(db) as uow:
        conn = uow.conn()
        viewer = cf.viewer_for_actor(conn, who)
        with cf.use_viewer(viewer):
            found = _submission(conn, scope, key, viewer)
            base: dict[str, Any] = {
                "actor": who,
                "source": SOURCE,
                "scope": scope,
                "submission_id": found.row.id,
            }
            handler: Any
            if action == "accept":
                cmd: Command = _model(AcceptFormSubmission, note=note, **base)
                handler = handle_accept_form_submission
            elif action == "return":
                if note is None:
                    raise typer.BadParameter("returning needs a reason", param_hint="'--note'")
                cmd = _model(ReturnFormSubmission, note=note, **base)
                handler = handle_return_form_submission
            else:
                if note is None:
                    raise typer.BadParameter("voiding needs a reason", param_hint="'--note'")
                cmd = _model(VoidFormSubmission, reason=note, **base)
                handler = handle_void_form_submission
            require_command(uow, cmd)
            handler(uow, cmd)
    typer.echo(f"{action}ed {found.row.key or found.row.id}")
