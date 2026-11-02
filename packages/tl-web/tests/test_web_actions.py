"""The action route: only what the server offers on that record now runs (S2, S4 check e).

``POST /web/p/{project}/records/{record_id}/do/{command}`` runs a command only if it is a row of the
terminal's ``ACTION_UI`` and in the ``allowed_actions`` of this record at the moment of the request;
CSRF is checked first; a refusal of ``run_command`` is shown as it is in ``#log-status``.
"""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest
from tl_api.commands import command_spec, run_command
from tl_core.actions import RecordActions
from tl_core.auth.errors import ForbiddenError
from tl_core.confidentiality import use_viewer, viewer_for
from tl_web import present
from tl_web.actions import NOT_OFFERED
from tl_web.reads import WebReadClient

P = "/web/p/P123"


def do(w: Any, web: Any, key: str, command: str, **form: str) -> Any:
    return web.client.post(
        f"{P}/records/{w.ids[key]}/do/{command}", data=form or None, headers=web.headers()
    )


def state_of(w: Any, key: str) -> str:
    return w.api("bob").get(f"/records/{w.ids[key]}").json()["status"]


@pytest.mark.parametrize("key", ["open_rfi", "waiting", "closed", "draft"])
def test_the_bar_lists_exactly_the_offered_actions(
    fresh_world: Any, htmlkit: Any, key: str
) -> None:
    w = fresh_world
    web = w.web("bob")
    api = w.api("bob")
    offered = [a["command"] for a in api.get(f"/records/{w.ids[key]}/actions").json()["actions"]]
    number = w.numbers[key]
    page = htmlkit.parse(web.client.get(f"{P}/rfis?sel={number}").text)
    assert page.commands() == [o for o in offered if o in present.ACTION_UI]
    partial = htmlkit.parse(web.client.get(f"{P}/rfis/panel/{number}").text)
    assert len(partial.buttons()) == len(page.buttons())  # the htmx partial has the same bar


def test_a_closed_rfi_is_offered_nothing(fresh_world: Any, htmlkit: Any) -> None:
    w = fresh_world
    assert w.api("bob").get(f"/records/{w.ids['closed']}/actions").json()["actions"] == []
    page = htmlkit.parse(w.web("bob").client.get(f"{P}/rfis?sel={w.numbers['closed']}").text)
    assert page.buttons() == []


@pytest.mark.parametrize(
    ("key", "command"),
    [("closed", "CloseTechnical"), ("open_rfi", "AnswerTechnical"), ("waiting", "SubmitTechnical")],
)
def test_a_command_in_the_table_but_not_offered_is_refused_and_writes_nothing(
    fresh_world: Any, htmlkit: Any, key: str, command: str
) -> None:
    w = fresh_world
    web = w.web("bob")
    before = w.events()
    response = do(w, web, key, command, answer="x", reason="x")
    assert response.status_code == 409
    assert htmlkit.parse(response.text).status() == f"! {NOT_OFFERED}"
    assert w.events() == before


def test_a_form_field_cannot_make_a_command_offered(fresh_world: Any) -> None:
    w = fresh_world
    before = w.events()
    response = do(
        w,
        w.web("bob"),
        "closed",
        "CloseTechnical",
        offered="CloseTechnical",
        allowed="CloseTechnical",
    )
    assert response.status_code == 409 and w.events() == before


def test_an_offered_command_runs_and_the_state_changes(fresh_world: Any) -> None:
    w = fresh_world
    web = w.web("bob")
    before, draft = w.events(), state_of(w, "draft")
    response = do(w, web, "draft", "SubmitTechnical")
    assert response.status_code == 200 and response.headers.get("HX-Refresh") == "true"
    assert w.events() > before and state_of(w, "draft") != draft


def test_the_question_form_asks_the_fields_and_the_answer_runs(
    fresh_world: Any, htmlkit: Any
) -> None:
    w = fresh_world
    web = w.web("bob")
    form = web.client.get(f"{P}/records/{w.ids['waiting']}/do/AnswerTechnical/form")
    names = htmlkit.parse(form.text).field_names()
    assert form.status_code == 200
    assert {"answer", "cost_impact", "schedule_impact", "csrf"} <= set(names)
    missing = do(w, web, "waiting", "AnswerTechnical", cost_impact="yes", schedule_impact="no")
    assert missing.status_code == 422
    assert "required" in htmlkit.parse(missing.text).status()
    before = state_of(w, "waiting")
    done = do(
        w, web, "waiting", "AnswerTechnical",
        answer="Reroute it.", cost_impact="yes", schedule_impact="no",
    )  # fmt: skip
    assert done.status_code == 200 and state_of(w, "waiting") != before


def test_the_form_of_a_command_that_is_not_offered_is_refused(fresh_world: Any) -> None:
    w = fresh_world
    web = w.web("bob")
    response = web.client.get(f"{P}/records/{w.ids['closed']}/do/CloseTechnical/form")
    assert response.status_code == 409


def test_a_post_without_the_csrf_token_is_refused_before_anything_else(
    fresh_world: Any, k: Any
) -> None:
    w = fresh_world
    web = w.web("bob")
    before = w.events()
    bare = web.client.post(
        f"{P}/records/{w.ids['draft']}/do/SubmitTechnical", headers={"Origin": k.OWN}
    )
    assert bare.status_code == 403 and bare.json()["error"] == "csrf_refused"
    assert w.events() == before


def test_a_refusal_of_run_command_is_shown_as_it_is(fresh_world: Any, htmlkit: Any) -> None:
    """An offer that is stale or too wide: the module role refuses, the text lands in the status."""
    w = fresh_world
    web = w.web("bob")
    principal = w.principal("bob")
    spec = command_spec("EscalateTechnical")
    assert spec is not None
    wide = RecordActions.model_validate(
        {
            "record_id": w.ids["open_rfi"],
            "state": "Answered",
            "actions": [{"command": "EscalateTechnical", "label": "Escalate", "reason": "stale"}],
        }
    )
    with mock.patch.object(WebReadClient, "allowed_actions", lambda self, record_id: wide):
        built = present.ACTION_UI["EscalateTechnical"].build({}, w.ids["open_rfi"], None)
        cmd = present.stamp(built, actor=principal.actor, scope="project:P123")
        with use_viewer(viewer_for(principal)), pytest.raises(ForbiddenError) as caught:
            run_command(w.app.state.ctx, spec, cmd, principal=principal)
        before = w.events()
        refused = do(w, web, "open_rfi", "EscalateTechnical")
    assert refused.status_code == 403
    assert htmlkit.parse(refused.text).status() == f"! {caught.value}"
    assert w.events() == before


@pytest.mark.parametrize("command", ["SetPsetValues", "NoSuchCommand"])
def test_a_command_outside_the_action_table_is_the_404_page(fresh_world: Any, command: str) -> None:
    w = fresh_world
    assert do(w, w.web("bob"), "open_rfi", command).status_code == 404


def test_hidden_unknown_and_other_project_are_one_404(fresh_world: Any, k: Any) -> None:
    w = fresh_world
    web = w.web("bob")
    hidden = web.client.post(
        f"{P}/records/{w.ids['secret_rfi']}/do/CloseTechnical", headers=web.headers()
    )
    unknown = web.client.post(f"{P}/records/{k.NEVER}/do/CloseTechnical", headers=web.headers())
    elsewhere = web.client.post(
        f"/web/p/OTHER/records/{w.ids['open_rfi']}/do/ReviewTechnicalAnswer", headers=web.headers()
    )
    assert hidden.status_code == unknown.status_code == elsewhere.status_code == 404
    assert hidden.content == unknown.content == elsewhere.content
