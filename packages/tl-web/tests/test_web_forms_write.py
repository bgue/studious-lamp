"""The writes of the fill page (V3-F3, W2): draft, submit and the bound form, as the person.

A write is the module's own command, stamped with the person, the project and source ``web``: a
draft save and a submit run ``tl_api.commands.run_command``; a bound form runs
``tl_mod_forms.bound.record`` (the call ``tl form record`` makes), so the typed command's word and
rules apply. A refusal is the status line and nothing else; no answer value is ever echoed.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest
from sqlalchemy import text
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.password import prepare_password
from tl_core.auth.queries import find_account

PROJECT = "P123"
MARK = "zq-marker-5519"
NEVER = "01J000000000000000000000"
GOOD = [{"q": "topic", "value": "Ladders"}, {"q": "count", "value": 5}]


def events(fw: Any, *types: str) -> list[dict[str, Any]]:
    sql = "SELECT event_type, actor, source, stream_id, payload FROM events"
    if types:
        sql += " WHERE event_type IN (" + ",".join(f"'{t}'" for t in types) + ")"
    with fw.world.backend(True) as uow:
        return [dict(r._mapping) for r in uow.conn().execute(text(sql + " ORDER BY rowid"))]


def count(fw: Any) -> int:
    return len(events(fw))


def post(web: Any, path: str, answers: Any, draft: str = "", **more: Any) -> Any:
    raw = answers if isinstance(answers, str) else json.dumps(answers)
    return web.client.post(
        path,
        params={"project": PROJECT},
        headers=web.headers(),
        data={"csrf": web.csrf, "answers_json": raw, "draft_id": draft, **more},
    )


def draft_of(fw: Any, web: Any, answers: Any = None) -> str:
    got = post(web, f"/web/forms/t/{fw.ids['talk']}/draft", answers or [GOOD[0]])
    assert got.status_code == 200, got.text
    return str(got.headers["x-draft-id"])


def person(fw: Any, name: str, roles: list[Any], module_role: str | None = None) -> None:
    with fw.world.backend(False) as uow:
        accounts.create_account(
            uow, username=name, display_name=name.title(), kind="person", roles=roles,
            password=prepare_password("correct horse battery", username=name), by="svc:test",
        )  # fmt: skip
        if module_role:
            found = find_account(uow.conn(), username=name)
            assert found is not None
            for module in ("forms", "quality"):
                grant_module_role(
                    uow,
                    GrantModuleRole(
                        actor="user:boss", source="test", account_id=found.account_id,
                        project=f"project:{PROJECT}", module=module, role=module_role,
                        reason="test",
                    ),
                )  # fmt: skip


# --- a general form ------------------------------------------------------------------------------


def test_a_draft_and_a_submit_are_the_persons_own_commands_from_the_web(forms_world: Any) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    talk = fw.ids["talk"]
    saved = post(web, f"/web/forms/t/{talk}/draft", [GOOD[0]])
    assert saved.status_code == 200 and "Draft saved" in saved.text
    draft = saved.headers["x-draft-id"]
    again = post(web, f"/web/forms/t/{talk}/draft", GOOD, draft)
    assert again.status_code == 200 and again.headers["x-draft-id"] == draft
    sent = post(web, f"/web/forms/t/{talk}/submit", GOOD, draft)
    assert sent.status_code == 303
    assert sent.headers["location"] == f"/web/forms/done/P123-FRM-0001?project={PROJECT}"
    got = events(fw, "Submission.DraftSaved", "Submission.Submitted")
    assert [(e["event_type"], e["actor"], e["source"]) for e in got] == [
        ("Submission.DraftSaved", "user:bob", "web"),
        ("Submission.DraftSaved", "user:bob", "web"),
        ("Submission.Submitted", "user:bob", "web"),
    ]
    assert {e["stream_id"] for e in got} == {draft}
    done = web.client.get(sent.headers["location"])
    assert done.status_code == 200 and "P123-FRM-0001" in done.text


def test_a_submit_with_no_draft_takes_the_number_at_once(forms_world: Any) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    sent = post(web, f"/web/forms/t/{fw.ids['talk']}/submit", GOOD)
    assert sent.status_code == 303 and "P123-FRM-0001" in sent.headers["location"]
    assert [e["source"] for e in events(fw, "Submission.Submitted")] == ["web"]


def test_the_done_page_shows_the_key_and_a_draft_id_is_no_key(
    forms_world: Any, htmlkit: Any
) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    sent = post(web, f"/web/forms/t/{fw.ids['talk']}/submit", GOOD)
    done = web.client.get(sent.headers["location"])
    doc = htmlkit.parse(done.text)
    assert [n.text() for n in doc.all() if n.tag == "h1"] == ["Received"]
    assert "Ladders" not in done.text  # the key and nothing else
    draft = draft_of(fw, web)
    miss = web.client.get(f"/web/forms/done/{draft}", params={"project": PROJECT})
    never = web.client.get(f"/web/forms/done/{NEVER}", params={"project": PROJECT})
    assert miss.status_code == never.status_code == 404 and miss.content == never.content


@pytest.mark.parametrize("what", ["draft", "submit", "bound"])
def test_a_missing_or_wrong_csrf_token_is_refused_before_anything_runs(
    forms_world: Any, what: str, k: Any
) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    other = fw.world.web("ctl")
    path = {
        "draft": f"/web/forms/t/{fw.ids['talk']}/draft",
        "submit": f"/web/forms/t/{fw.ids['talk']}/submit",
        "bound": f"/web/forms/for/{fw.keys['insp_open']}/submit",
    }[what]
    body = {"answers_json": json.dumps([{"q": "topic", "value": MARK}])}
    before = count(fw)
    attempts = {
        "no token": ({"Origin": k.OWN}, body),
        "wrong token": ({"Origin": k.OWN}, {**body, "csrf": "nope"}),
        "another session": ({"Origin": k.OWN}, {**body, "csrf": other.csrf}),
        "wrong header": ({"Origin": k.OWN, "X-CSRF-Token": "nope"}, body),
        "foreign origin": ({"Origin": "http://evil.example"}, {**body, "csrf": web.csrf}),
    }
    for name, (headers, data) in attempts.items():
        got = web.client.post(path, params={"project": PROJECT}, headers=headers, data=data)
        assert got.status_code == 403, name
        assert got.json()["error"] == "csrf_refused", name
    assert count(fw) == before


def test_a_person_without_forms_submit_gets_the_status_line_and_no_event(forms_world: Any) -> None:
    fw = forms_world
    person(fw, "vic", ["user"], "viewer")
    web = fw.world.web("vic")
    for suffix in ("draft", "submit"):
        before = count(fw)
        got = post(web, f"/web/forms/t/{fw.ids['talk']}/{suffix}", GOOD)
        assert got.status_code == 403, got.text
        assert got.text.count("! ") == 1 and "access word" in got.text
        assert "Ladders" not in got.text
        assert count(fw) == before


def test_an_agent_token_gets_the_closed_guards_answer_on_every_forms_route(
    forms_world: Any,
) -> None:
    fw = forms_world
    bot = fw.world.web("bot")
    before = count(fw)
    answers = {
        bot.client.get("/web/forms", params={"project": PROJECT}).status_code,
        bot.client.get(f"/web/forms/t/{fw.ids['talk']}", params={"project": PROJECT}).status_code,
        post(bot, f"/web/forms/t/{fw.ids['talk']}/submit", GOOD).status_code,
        post(bot, f"/web/forms/t/{fw.ids['talk']}/draft", GOOD).status_code,
        post(bot, f"/web/forms/for/{fw.keys['insp_open']}/submit", GOOD).status_code,
        bot.client.get(
            f"/web/forms/for/{fw.keys['insp_open']}", params={"project": PROJECT}
        ).status_code,
        bot.client.get("/web/forms/done/P123-FRM-0001", params={"project": PROJECT}).status_code,
    }
    assert answers == {401}
    assert count(fw) == before


# --- drafts: only the author's own ---------------------------------------------------------------


def test_another_authors_draft_id_answers_like_an_absent_one(forms_world: Any) -> None:
    fw = forms_world
    bob, ctl = fw.world.web("bob"), fw.world.web("amy")
    draft = draft_of(fw, bob, [{"q": "topic", "value": MARK}])
    before = count(fw)
    path = f"/web/forms/t/{fw.ids['talk']}"
    for verb in ("submit", "draft"):
        theirs = post(ctl, f"{path}/{verb}", GOOD, draft)
        absent = post(ctl, f"{path}/{verb}", GOOD, NEVER)
        assert theirs.status_code == absent.status_code == 404, verb
        assert theirs.content == absent.content, verb
    read = ctl.client.get(path, params={"project": PROJECT, "draft": draft})
    none = ctl.client.get(path, params={"project": PROJECT, "draft": NEVER})
    assert read.status_code == none.status_code == 404 and read.content == none.content
    assert MARK not in read.text
    assert count(fw) == before


def test_a_draft_of_another_template_is_not_resumed_on_this_page(forms_world: Any) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    draft = draft_of(fw, web)
    got = web.client.get(
        f"/web/forms/t/{fw.ids['plant']}", params={"project": PROJECT, "draft": draft}
    )
    assert got.status_code == 404


def test_the_page_resumes_the_persons_own_draft_in_answers_json(
    forms_world: Any, htmlkit: Any
) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    draft = draft_of(fw, web, [{"q": "topic", "value": MARK}])
    got = web.client.get(
        f"/web/forms/t/{fw.ids['talk']}", params={"project": PROJECT, "draft": draft}
    )
    doc = htmlkit.parse(got.text)
    field = doc.by_id("answers_json")
    assert field is not None and json.loads(field.attrs["value"]) == [{"q": "topic", "value": MARK}]
    ident = doc.by_id("draft_id")
    assert ident is not None and ident.attrs["value"] == draft
    listed = web.client.get("/web/forms", params={"project": PROJECT})
    assert "Your drafts" in listed.text and f"draft={draft}" in listed.text
    assert MARK not in listed.text  # the list names the draft, not its answers
    other = fw.world.web("amy").client.get("/web/forms", params={"project": PROJECT})
    assert "Your drafts" not in other.text and draft not in other.text


# --- what the page never echoes -----------------------------------------------------------------


def test_a_refusal_is_the_status_line_and_echoes_no_answer(forms_world: Any) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    before = count(fw)
    path = f"/web/forms/t/{fw.ids['talk']}"
    for body in (
        [{"q": "topic", "value": MARK}, {"q": "nope", "value": MARK}],  # an unknown question
        [{"q": "count", "value": MARK}],  # not a number, and topic is missing
        [{"q": "topic", "value": 12 * MARK * 100}],  # too long
    ):
        for verb in ("submit", "draft"):
            got = post(web, f"{path}/{verb}", body)
            assert got.status_code == 422, (verb, got.text)
            assert got.text.count("<") <= 2 and MARK not in got.text and "! " in got.text
            assert got.headers.get("x-draft-id") is None
    assert count(fw) == before


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("not json", id="not-json"),
        pytest.param("{}", id="object"),
        pytest.param('[{"value": 1}]', id="no-q"),
        pytest.param('[["q"]]', id="nested"),
        pytest.param("[1]", id="number"),
        pytest.param("x" * 300_000, id="too-long"),
        pytest.param("[" * 20_000, id="nested"),
    ],
)
def test_an_answers_block_that_is_not_a_list_of_answers_is_refused(
    forms_world: Any, raw: str
) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    before = count(fw)
    got = post(web, f"/web/forms/t/{fw.ids['talk']}/submit", raw)
    assert got.status_code in (413, 422)  # 413: the app's own body limit comes first
    assert got.status_code == 413 or "did not come through" in got.text
    assert count(fw) == before


def test_a_success_redirect_and_the_done_page_hold_no_answer(forms_world: Any) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    sent = post(web, f"/web/forms/t/{fw.ids['talk']}/submit", [{"q": "topic", "value": MARK}])
    assert sent.status_code == 303 and MARK not in sent.headers["location"]
    assert MARK not in sent.text
    assert MARK not in web.client.get(sent.headers["location"]).text
    assert MARK not in json.dumps(dict(sent.headers))


# --- the form of a record ------------------------------------------------------------------------


def test_a_bound_form_is_the_records_typed_command_as_the_person_from_the_web(
    forms_world: Any,
) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    key = fw.keys["insp_open"]
    got = post(web, f"/web/forms/for/{key}/submit", [{"q": "q1", "value": "yes", "note": None}])
    assert got.status_code == 303, got.text
    assert got.headers["location"] == f"/web/p/{PROJECT}/records/{fw.ids['insp_open']}"
    recorded = events(fw, "Inspection.ResultRecorded", "Inspection.Recorded")
    assert recorded == [] or all(
        e["source"] == "web" and e["actor"] == "user:bob" for e in recorded
    )
    web_events = [e for e in events(fw) if e["source"] == "web"]
    assert web_events and {e["actor"] for e in web_events} == {"user:bob"}
    with fw.world.backend(True) as uow:
        state = (
            uow.conn()
            .execute(
                text("SELECT state FROM cur_workflow_state WHERE record_id = :i"),
                {"i": fw.ids["insp_open"]},
            )
            .scalar_one()
        )
    assert state == "Done"
    again = post(web, f"/web/forms/for/{key}/submit", [{"q": "q1", "value": "yes", "note": None}])
    assert again.status_code in (409, 422) and "! " in again.text  # the form is closed now


def test_a_bound_form_goes_through_bound_record_and_never_around_it(forms_world: Any) -> None:
    from tl_mod_forms import bound

    fw = forms_world
    web = fw.world.web("bob")
    with mock.patch.object(bound, "record", wraps=bound.record) as spy:
        got = post(
            web,
            f"/web/forms/for/{fw.keys['insp_open']}/submit",
            [{"q": "q1", "value": "yes", "note": None}],
        )
    assert got.status_code == 303
    assert spy.call_count == 1
    assert spy.call_args.kwargs["source"] == "web" and spy.call_args.kwargs["actor"] == "user:bob"
    assert spy.call_args.kwargs["record_id"] == fw.ids["insp_open"]


def test_a_bound_form_with_failing_answers_writes_nothing(forms_world: Any) -> None:
    fw = forms_world
    web = fw.world.web("bob")
    before = count(fw)
    key = fw.keys["insp_open"]
    for body in (
        [{"q": "q2", "value": 3, "note": None}],  # q1 is required
        [{"q": "q1", "value": MARK, "note": None}],  # not a yes, no or na
        [{"q": "zz", "value": MARK, "note": None}],  # not a question
    ):
        got = post(web, f"/web/forms/for/{key}/submit", body)
        assert got.status_code == 422 and MARK not in got.text and "! " in got.text
    assert count(fw) == before


def test_a_person_without_the_typed_commands_word_is_refused_with_its_own_text(
    forms_world: Any,
) -> None:
    fw = forms_world
    person(fw, "vic", ["user"], "viewer")
    web = fw.world.web("vic")
    before = count(fw)
    got = post(
        web,
        f"/web/forms/for/{fw.keys['insp_open']}/submit",
        [{"q": "q1", "value": "yes", "note": None}],
    )
    assert got.status_code == 403
    assert "RecordInspectionResult" in got.text and "quality" in got.text
    assert count(fw) == before


@pytest.mark.parametrize("who", ["bob", "boss", "amy", "ctl"])
def test_a_hidden_a_missing_and_a_typeless_key_are_one_404_on_the_bound_routes(
    forms_world: Any, who: str
) -> None:
    fw = forms_world
    web = fw.world.web(who)
    hidden = fw.keys["insp_hidden"]
    may = who in ("amy", "ctl")  # the readers of the privileged item the inspection is about
    answers: dict[str, Any] = {}
    for name, key in (
        ("hidden", hidden),
        ("missing", "P123-INS-9999"),
        ("typeless", "P123-COR-0001"),
    ):
        get = web.client.get(f"/web/forms/for/{key}", params={"project": PROJECT})
        put = post(web, f"/web/forms/for/{key}/submit", [{"q": "q1", "value": "yes", "note": None}])
        answers[name] = (get, put)
    for verb in (0, 1):
        missing = answers["missing"][verb]
        assert missing.status_code == 404
        assert answers["typeless"][verb].status_code == 404
        assert answers["typeless"][verb].content == missing.content
        if not may:
            hid = answers["hidden"][verb]
            assert (hid.status_code, hid.content) == (missing.status_code, missing.content)
    if not may:
        assert not [e for e in events(fw) if e["source"] == "web"]
