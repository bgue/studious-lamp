"""The forms pages: ``/web/forms`` (V3-F3; ADR-0031 decisions 11 and 13; spec W2, D27 to D31).

A signed-in person fills a general form, or the form a record offers (an inspection reached from
its scan card), in a browser, and sends it. Every route first passes ``guard("forms.read")`` (an
agent token gets the closed guard's answer) and, for a write, the CSRF check before anything runs.

* **Reads** go through ``WebReadClient`` (the forms routes' own functions, ``forms.view`` first), in
  the request's viewer. A record that is hidden, absent or has no form, a draft of another author
  and a template the person may not fill all answer the one 404 page.
* **Writes** go through the module's commands, never around them: ``SaveFormDraft`` and
  ``SubmitForm`` by ``tl_api.commands.run_command`` (the one access check), and a bound form through
  ``tl_mod_forms.bound.record``, the call ``tl form record`` makes, so the typed command's own
  access word and rules apply. The command is stamped with the actor, the project and source
  ``web``. A refusal is the status line ``! <message>`` and nothing else; no answer value is ever
  put in a status line, a log or a redirect.
* **The page** is the form chrome, a ``<div id="survey">`` and one JSON data block holding the
  SurveyJS model of the questions (``tojson``: ``<``, ``>``, ``&`` and ``'`` are escaped). The
  browser only helps the person; the server validates.

The project is the ``project`` query parameter, else ``TL_PROJECT`` (as ``/web/`` does).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from tl_api.auth import PRINCIPAL_KEY, guard
from tl_api.commands import command_spec, run_command
from tl_core.auth.types import Principal
from tl_core.confidentiality import current_viewer
from tl_core.forms.surveyjs import surveyjs_unsupported, to_surveyjs
from tl_mod_forms import bound
from tl_mod_forms.errors import FormsError, FormStateError, StaleVersionError

from tl_web import csrf
from tl_web.app import PROJECT_ID, render
from tl_web.reads import WebReadClient
from tl_web.webroute import not_found_page, status_fragment, web_router

router = web_router()
Reader = Annotated[str, Depends(guard("forms.read"))]
Project = Annotated[str | None, Query(max_length=64)]

SOURCE = "web"
MAX_ANSWERS_JSON = 200_000
NOT_UNDERSTOOD = "the answers did not come through; reload the page and try again"
SAVED = "Draft saved"
#: A bound form's closed reasons, in words (the fixed words of the sources).
REASONS = {
    "no_checklist": "no checklist is pinned to this record",
    "already_recorded": "this record has its result already",
    "cancelled": "this record was cancelled",
    "not_scheduled": "this record is not scheduled",
    "not_approved": "this permit is not approved",
}


def _refused(request: Request, exc: FormsError) -> Response:
    """The module's refusal as the status line: its fixed text names question ids, never a value.
    (The JSON error table has no row for these classes, so the page answers them itself.)"""
    clash = isinstance(exc, FormStateError | StaleVersionError)
    return status_fragment(request, str(exc), 409 if clash else 422)


def _project(project: str | None) -> str | None:
    """The project of the request, or ``None`` (an unusable name is a miss)."""
    chosen = project if project else os.environ.get("TL_PROJECT", "")
    return chosen if PROJECT_ID.fullmatch(chosen) else None


def _client(request: Request) -> tuple[WebReadClient, Principal]:
    principal: Principal = request.scope[PRINCIPAL_KEY]
    return WebReadClient(request.app.state.ctx, principal, path=request.url.path), principal


def _fillable(template: Any) -> bool:
    """A general template: published, not bound to a record type, not a public intake form."""
    return (
        template.state == "Published"
        and template.bound_record_type is None
        and template.intake is None
    )


def _plain(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ``{q, value}`` pairs of stored answers (the notes stay on the server)."""
    return [{"q": a["q"], "value": a.get("value")} for a in answers if "q" in a]


def _answers_of(raw: str) -> list[dict[str, Any]] | None:
    """The answers a page posts: a JSON list of ``{q, value}``; ``None`` if it is anything else."""
    if len(raw) > MAX_ANSWERS_JSON:
        return None
    try:
        found = json.loads(raw) if raw.strip() else []
    except ValueError:
        return None
    if not isinstance(found, list):
        return None
    out: list[dict[str, Any]] = []
    for item in found:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(item, dict) or not isinstance(item.get("q"), str):  # pyright: ignore[reportUnknownMemberType]
            return None
        entry: dict[str, Any] = {"q": item["q"], "value": item.get("value")}  # pyright: ignore[reportUnknownMemberType]
        if "note" in item:  # a format 1 answer carries its note (the page sends null)
            entry["note"] = item["note"]  # pyright: ignore[reportUnknownMemberType]
        out.append(entry)
    return out


# --- the list ------------------------------------------------------------------------------------


def _list(request: Request, project: str | None) -> Response:
    chosen = _project(project)
    if chosen is None:
        return not_found_page(request)
    client, principal = _client(request)
    templates = client.list_form_templates(limit=500).rows
    mine = client.list_form_submissions(
        chosen, state="Draft", author=principal.actor, limit=100
    ).rows
    by_id = {t.id: t for t in templates}
    drafts = [
        {
            "id": d.id,
            "tid": d.template_id,
            "title": by_id[d.template_id].title,
            "saves": d.draft_saves or 0,
        }
        for d in mine
        if d.template_id in by_id and by_id[d.template_id].bound_record_type is None
    ]
    rows = [
        {"id": t.id, "key": t.key, "title": t.title, "version": t.version}
        for t in templates
        if _fillable(t)
    ]
    return render(request, "forms/list.html", project=chosen, templates=rows, drafts=drafts)


@router.get("/forms")
async def forms_list(request: Request, _actor: Reader, project: Project = None) -> Response:
    return await run_in_threadpool(_list, request, project)


# --- a general form -------------------------------------------------------------------------------


def _fill_page(
    request: Request, template_id: str, project: str | None, draft: str | None
) -> Response:
    chosen = _project(project)
    if chosen is None:
        return not_found_page(request)
    client, principal = _client(request)
    found = next(
        (t for t in client.list_form_templates(limit=500).rows if t.id == template_id), None
    )
    if found is None or not _fillable(found) or found.key is None or found.version is None:
        return not_found_page(request)
    detail = client.get_form_template_version(found.key, found.version)
    projection = client.get_form_template_version(found.key, found.version, "surveyjs")
    saved: list[dict[str, Any]] = []
    if draft:
        got = client.get_form_submission(chosen, draft)  # another author's draft: the route's 404
        row = got.row
        if row.state != "Draft" or row.author != principal.actor or row.template_id != found.id:
            return not_found_page(request)
        saved = _plain(got.answers)
    texts = {f["id"]: f["text"] for f in detail["fields"]}
    return render(
        request,
        "forms/fill.html",
        title=found.title,
        meta=f"{found.key}, version {found.version}",
        model=projection["model"],
        unsupported=[texts[q] for q in projection["unsupported"] if q in texts],
        answers_json=json.dumps(saved),
        draft_id=draft or "",
        fmt=detail["row"]["format_version"] or 2,
        draftable=True,
        submit_url=f"/web/forms/t/{found.id}/submit?project={chosen}",
        draft_url=f"/web/forms/t/{found.id}/draft?project={chosen}",
    )


@router.get("/forms/t/{template_id}")
async def fill_general(
    request: Request,
    template_id: str,
    _actor: Reader,
    project: Project = None,
    draft: Annotated[str | None, Query(max_length=60)] = None,
) -> Response:
    return await run_in_threadpool(_fill_page, request, template_id, project, draft)


def _run_fill(
    request: Request, name: str, template_id: str, project: str | None, form: dict[str, str]
) -> tuple[Response | None, str | None]:
    """Run ``SaveFormDraft`` or ``SubmitForm``: ``(refusal, key or draft id)``."""
    chosen = _project(project)
    if chosen is None:
        return not_found_page(request), None
    answers = _answers_of(form.get("answers_json", ""))
    if answers is None:
        return status_fragment(request, NOT_UNDERSTOOD, 422), None
    spec = command_spec(name)
    assert spec is not None  # the module's commands are in the table
    principal: Principal = request.scope[PRINCIPAL_KEY]
    draft_id = form.get("draft_id", "").strip()
    command = spec.model.model_validate(
        {
            "actor": principal.actor,
            "source": SOURCE,
            "scope": f"project:{chosen}",
            "answers": answers,
            **({"draft_id": draft_id} if draft_id else {"template_id": template_id}),
        }
    )
    try:
        result = run_command(
            request.app.state.ctx, spec, command, principal=principal, path=request.url.path
        )
    except FormsError as exc:
        return _refused(request, exc), None
    return None, result.key or result.stream_id


async def _form(request: Request) -> dict[str, str]:
    values = await request.form()
    return {k: v for k, v in values.items() if isinstance(v, str)}


@router.post("/forms/t/{template_id}/draft", dependencies=[Depends(csrf.verify)])
async def save_draft(
    request: Request, template_id: str, _actor: Reader, project: Project = None
) -> Response:
    values = await _form(request)
    refusal, draft = await run_in_threadpool(
        _run_fill, request, "SaveFormDraft", template_id, project, values
    )
    if refusal is not None:
        return refusal
    done = status_fragment(request, SAVED, error=False)
    done.headers["X-Draft-Id"] = draft or ""
    return done


@router.post("/forms/t/{template_id}/submit", dependencies=[Depends(csrf.verify)])
async def submit(
    request: Request, template_id: str, _actor: Reader, project: Project = None
) -> Response:
    values = await _form(request)
    refusal, key = await run_in_threadpool(
        _run_fill, request, "SubmitForm", template_id, project, values
    )
    if refusal is not None:
        return refusal
    return RedirectResponse(f"/web/forms/done/{key}?project={_project(project)}", status_code=303)


def _done(request: Request, key: str, project: str | None) -> Response:
    chosen = _project(project)
    if chosen is None:
        return not_found_page(request)
    client, _principal = _client(request)
    got = client.get_form_submission(chosen, key)
    if got.row.key != key:  # a draft's id is not a key
        return not_found_page(request)
    return render(request, "forms/done.html", key=key)


@router.get("/forms/done/{key}")
async def done(request: Request, key: str, _actor: Reader, project: Project = None) -> Response:
    return await run_in_threadpool(_done, request, key, project)


# --- the form a record offers ---------------------------------------------------------------------


def _bound_page(request: Request, key: str, project: str | None) -> Response:
    chosen = _project(project)
    if chosen is None:
        return not_found_page(request)
    client, _principal = _client(request)
    binding = client.get_form_for_record(chosen, key)
    record = client.get_record(f"project:{chosen}", key)
    if record is None:
        return not_found_page(request)
    head = {"title": str(record["title"] or ""), "key": key}
    if not binding.available or binding.template is None:
        why = REASONS.get(binding.reason or "", "this record takes no form now")
        return render(request, "forms/closed.html", why=why, title=head["title"], key=key)
    with request.app.state.ctx.backend(True) as uow:
        fields = bound.fields_of(uow.conn(), binding, current_viewer())
    fmt = binding.template.fmt
    return render(
        request,
        "forms/fill.html",
        title=f"{key}: {head['title']}" if head["title"] else key,
        meta=f"form {binding.template.source_type} version {binding.template.version}",
        model=to_surveyjs(fields, fmt),
        unsupported=[str(f["text"]) for f in fields if f["id"] in surveyjs_unsupported(fields)],
        answers_json="[]",
        draft_id="",
        fmt=fmt,
        draftable=False,
        submit_url=f"/web/forms/for/{key}/submit?project={chosen}",
        draft_url="",
    )


@router.get("/forms/for/{key}")
async def fill_bound(
    request: Request, key: str, _actor: Reader, project: Project = None
) -> Response:
    return await run_in_threadpool(_bound_page, request, key, project)


def _bound_submit(
    request: Request, key: str, project: str | None, form: dict[str, str]
) -> Response:
    chosen = _project(project)
    if chosen is None:
        return not_found_page(request)
    client, principal = _client(request)
    binding = client.get_form_for_record(chosen, key)  # a miss is the one 404 page
    record = client.get_record(f"project:{chosen}", key)
    if record is None or binding is None:
        return not_found_page(request)
    answers = _answers_of(form.get("answers_json", ""))
    if answers is None:
        return status_fragment(request, NOT_UNDERSTOOD, 422)
    try:
        with request.app.state.ctx.backend(False) as uow:
            bound.record(
                uow,
                record_id=str(record["id"]),
                answers=answers,
                actor=principal.actor,
                scope=f"project:{chosen}",
                source=SOURCE,
                now=datetime.now(UTC),
                viewer=current_viewer(),
            )
    except FormsError as exc:
        return _refused(request, exc)
    return RedirectResponse(f"/web/p/{chosen}/records/{record['id']}", status_code=303)


@router.post("/forms/for/{key}/submit", dependencies=[Depends(csrf.verify)])
async def submit_bound(
    request: Request, key: str, _actor: Reader, project: Project = None
) -> Response:
    values = await _form(request)
    return await run_in_threadpool(_bound_submit, request, key, project, values)
