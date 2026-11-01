"""The action route: run a command only if it is in ``ACTION_UI`` and offered on that record now.

``POST /web/p/{project}/records/{record_id}/do/{command}`` and its question form
``GET .../do/{command}/form`` (spec web-client-i1, section 7). The command must be a row of the
terminal's ``ACTION_UI`` **and** in the ``allowed_actions`` the server gives this principal for this
record at the moment of the request: never a form field, never an earlier page. A refusal is the
status line ``! <message>``; no command runs and no event is written. The command is built with
``ActionUi.build``, stamped with the actor and the project scope, and run by
``tl_api.commands.run_command`` (the one access check: module role, state guard, version,
validation). CSRF is S1's ``csrf.verify`` as a router dependency.

The command's ``source`` is ``web`` (the terminal's ``stamp`` writes ``tui``); the actor and scope
are the stamped ones.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from tl_api.auth import PRINCIPAL_KEY
from tl_api.commands import command_spec, run_command
from tl_core.auth.types import Principal

from tl_web import csrf, present
from tl_web.app import PROJECT_ID, render
from tl_web.reads import WebReadClient
from tl_web.webroute import not_found_page, status_fragment, web_router

router = web_router()

NOT_OFFERED = "That action is not available on this record now."
PATH = "/p/{project}/records/{record_id}/do/{command}"


def _gate(
    request: Request, project: str, record_id: str, command: str
) -> tuple[Response | None, str]:
    """``(refusal, label)``: a response to send instead of acting, or ``None`` and the label.

    404 page: not in ``ACTION_UI``, no such command, an unknown project, or a record that is hidden,
    missing or in another project (the record is read as this viewer, so hidden is missing).
    Otherwise the offer is read now; a command not offered is the status line.
    """
    if (
        command not in present.ACTION_UI
        or command_spec(command) is None
        or not PROJECT_ID.fullmatch(project)
    ):
        return not_found_page(request), ""
    principal: Principal = request.scope[PRINCIPAL_KEY]
    client = WebReadClient(request.app.state.ctx, principal, path=request.url.path)
    record = client.get_record_by_id(record_id)
    if record is None or record["scope"] != f"project:{project}":
        return not_found_page(request), ""
    offers = {o.command: o.label for o in client.allowed_actions(record_id).actions}
    if command not in offers:
        return status_fragment(request, NOT_OFFERED, 409), ""
    return None, offers[command]


def _answers(entry: present.ActionUi, values: dict[str, str]) -> tuple[dict[str, str], str | None]:
    """The form's answers by field name, and a message when one is missing or not a choice."""
    answers: dict[str, str] = {}
    for field in entry.fields:
        value = values.get(field.name, "").strip()
        if field.kind == "choice":
            value = value or field.default
            if value not in field.choices:
                return answers, f"{field.label}: choose {', '.join(field.choices)}"
        elif field.required and not value:
            return answers, f"{field.label} is required"
        answers[field.name] = value
    return answers, None


def _run(
    request: Request, project: str, record_id: str, command: str, values: dict[str, str]
) -> Response:
    refusal, label = _gate(request, project, record_id, command)
    if refusal is not None:
        return refusal
    entry = present.ACTION_UI[command]
    spec = command_spec(command)
    assert spec is not None  # _gate checked it
    answers, problem = _answers(entry, values)
    if problem is not None:
        return status_fragment(request, problem, 422)
    principal: Principal = request.scope[PRINCIPAL_KEY]
    built = entry.build(answers, record_id, None)
    stamped = present.stamp(built, actor=principal.actor, scope=f"project:{project}")
    run_command(
        request.app.state.ctx,
        spec,
        stamped.model_copy(update={"source": "web"}),
        principal=principal,
        path=request.url.path,
    )
    done = status_fragment(request, f"{label}: done", error=False)
    done.headers["HX-Refresh"] = "true"  # the rows and the bar follow what the command changed
    return done


@router.post(PATH, dependencies=[Depends(csrf.verify)])
async def do_command(request: Request, project: str, record_id: str, command: str) -> Response:
    form = await request.form()
    values = {k: v for k, v in form.items() if isinstance(v, str)}
    return await run_in_threadpool(_run, request, project, record_id, command, values)


@router.get(PATH + "/form")
def action_form(request: Request, project: str, record_id: str, command: str) -> Response:
    """The questions of an action as a form for the panel (the POST route asks them again)."""
    refusal, label = _gate(request, project, record_id, command)
    if refusal is not None:
        return refusal
    entry = present.ACTION_UI[command]
    fields: list[dict[str, Any]] = [
        {
            "name": f.name,
            "label": f.label,
            "kind": f.kind,
            "choices": f.choices,
            "required": f.required,
            "default": f.default,
        }
        for f in entry.fields
    ]
    return render(
        request,
        "action_form.html",
        label=label,
        confirm=entry.confirm,
        fields=fields,
        url=f"/web/p/{project}/records/{record_id}/do/{command}",
    )
