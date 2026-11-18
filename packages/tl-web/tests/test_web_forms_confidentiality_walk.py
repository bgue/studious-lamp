"""Walk of ``/web/forms`` as five kinds of reader (V3-F3; ADR-0016: hidden looks like missing).

Readers are those of the web walk: ``boss`` (admin), ``ctl`` (document controller, reads restricted
and privileged), ``bob`` (plain user), ``amy`` (named on the privileged items) and ``bot`` (an
agent, who has no web session). The hidden things: an inspection about a privileged correspondence
item (read by ``ctl`` and ``amy``), a submission of a ``restricted`` template (read by ``ctl`` and
``boss``), and another person's draft. For a reader who may not read one, the answer is
byte-for-byte the answer for a key that never existed (status, headers that matter and body), on
every route that takes a key, and no response holds the words only the hidden record has.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

PROJECT = "P123"
HIDDEN_TITLE = "Inspection hidden"
REST_MARK = "restmark-8841"
MISSING_INSP = "P123-INS-9999"
MISSING_FRM = "P123-FRM-9999"
NEVER = "01J000000000000000000000"
READERS = ("boss", "ctl", "bob", "amy", "bot")
IGNORED_HEADERS = {"date", "set-cookie"}
INSP_READERS = {"ctl", "amy"}
SUBMISSION_READERS = {"ctl", "boss"}


@pytest.fixture(scope="module")
def walk_ids(forms_world_ro: Any) -> dict[str, str]:
    fw = forms_world_ro
    made = fw.run(
        "boss", "DraftFormTemplate", scope="company", title="Restricted talk",
        answer_class="restricted",
        fields=[{
            "id": "topic", "text": "Topic", "kind": "text", "required": True, "unit": None,
            "min": None, "max": None, "choices": None, "fails_when": None, "section": None,
            "help": None, "visible_when": None,
        }],
    )  # fmt: skip
    fw.run("boss", "PublishFormTemplate", scope="company", template_id=made.stream_id)
    sub = fw.run(
        "ctl", "SubmitForm", template_id=str(made.stream_id),
        answers=[{"q": "topic", "value": REST_MARK}],
    )  # fmt: skip
    draft = fw.run(
        "ctl", "SaveFormDraft", template_id=fw.ids["talk"],
        answers=[{"q": "topic", "value": "ctl-draft-answer"}],
    )  # fmt: skip
    return {"submission": str(sub.key), "draft": str(draft.stream_id), "tpl": str(made.stream_id)}


def same(hidden: Any, never: Any) -> None:
    assert hidden.status_code == never.status_code
    a = {k: v for k, v in hidden.headers.items() if k not in IGNORED_HEADERS}
    b = {k: v for k, v in never.headers.items() if k not in IGNORED_HEADERS}
    assert a == b, "the headers of a hidden thing differ from those of a missing one"
    assert hidden.content == never.content


def get(web: Any, path: str, **params: str) -> Any:
    return web.client.get(path, params={"project": PROJECT, **params})


def post(web: Any, path: str, answers: Any) -> Any:
    return web.client.post(
        path,
        params={"project": PROJECT},
        headers=web.headers(),
        data={"csrf": web.csrf, "answers_json": json.dumps(answers), "draft_id": ""},
    )


@pytest.mark.parametrize("who", READERS)
def test_the_bound_page_of_a_hidden_record_is_the_page_of_a_missing_key(
    forms_world_ro: Any, walk_ids: dict[str, str], who: str
) -> None:
    fw = forms_world_ro
    web = fw.world.web(who)
    hidden = get(web, f"/web/forms/for/{fw.keys['insp_hidden']}")
    never = get(web, f"/web/forms/for/{MISSING_INSP}")
    if who == "bot":
        assert hidden.status_code == never.status_code == 401
        return
    if who in INSP_READERS:  # the positive control: a reader sees the form
        assert hidden.status_code == 200 and HIDDEN_TITLE in hidden.text
        assert never.status_code == 404
    else:
        same(hidden, never)
        assert HIDDEN_TITLE not in hidden.text and fw.keys["insp_hidden"] not in hidden.text


@pytest.mark.parametrize("who", READERS)
def test_the_bound_submit_for_a_hidden_record_is_the_submit_for_a_missing_key(
    forms_world_ro: Any, who: str
) -> None:
    fw = forms_world_ro
    web = fw.world.web(who)
    body = [{"q": "q1", "value": "yes", "note": None}]
    never = post(web, f"/web/forms/for/{MISSING_INSP}/submit", body)
    if who == "bot":
        assert never.status_code == 401
        return
    assert never.status_code == 404
    if who in INSP_READERS:
        return  # their own commands are walked in test_web_forms_write.py
    hidden = post(web, f"/web/forms/for/{fw.keys['insp_hidden']}/submit", body)
    same(hidden, never)


@pytest.mark.parametrize("who", READERS)
def test_the_done_page_of_a_hidden_submission_is_the_page_of_a_missing_key(
    forms_world_ro: Any, walk_ids: dict[str, str], who: str
) -> None:
    fw = forms_world_ro
    web = fw.world.web(who)
    hidden = get(web, f"/web/forms/done/{walk_ids['submission']}")
    never = get(web, f"/web/forms/done/{MISSING_FRM}")
    if who == "bot":
        assert hidden.status_code == never.status_code == 401
        return
    if who in SUBMISSION_READERS:
        assert hidden.status_code == 200 and walk_ids["submission"] in hidden.text
        assert REST_MARK not in hidden.text  # the key and nothing else
    else:
        same(hidden, never)


@pytest.mark.parametrize("who", ["boss", "ctl", "bob", "amy"])
def test_another_persons_draft_is_a_missing_id_on_the_fill_page(
    forms_world_ro: Any, walk_ids: dict[str, str], who: str
) -> None:
    fw = forms_world_ro
    web = fw.world.web(who)
    path = f"/web/forms/t/{fw.ids['talk']}"
    theirs = get(web, path, draft=walk_ids["draft"])
    never = get(web, path, draft=NEVER)
    if who == "ctl":  # the author reads it
        assert theirs.status_code == 200 and "ctl-draft-answer" in theirs.text
    else:
        same(theirs, never)
        assert "ctl-draft-answer" not in theirs.text


@pytest.mark.parametrize("who", ["boss", "ctl", "bob", "amy"])
def test_the_list_holds_the_same_rows_for_every_reader_and_no_hidden_word(
    forms_world_ro: Any, walk_ids: dict[str, str], who: str, htmlkit: Any
) -> None:
    fw = forms_world_ro
    got = get(fw.world.web(who), "/web/forms")
    assert got.status_code == 200
    rows = [h for h, _ in htmlkit.parse(got.text).links() if h.startswith("/web/forms/t/")]
    own_draft = who == "ctl"
    templates = [h for h in rows if "draft=" not in h]
    assert len(templates) == 3  # talk, plant and the restricted template: no row is hidden
    assert len(rows) - len(templates) == (1 if own_draft else 0)
    for word in (REST_MARK, HIDDEN_TITLE, fw.keys["insp_hidden"], walk_ids["submission"]):
        assert word not in got.text
    assert ("ctl-draft-answer" in got.text) is False
    assert (walk_ids["draft"] in got.text) is own_draft


def test_every_forms_route_with_a_path_key_is_in_this_walk(forms_world_ro: Any, k: Any) -> None:
    routes = {
        p for m, p in k.web_routes(forms_world_ro.world.app, {"GET", "POST"}) if "/forms" in p
    }
    assert routes == {
        "/web/forms",
        "/web/forms/t/{template_id}",
        "/web/forms/t/{template_id}/draft",
        "/web/forms/t/{template_id}/submit",
        "/web/forms/for/{key}",
        "/web/forms/for/{key}/submit",
        "/web/forms/done/{key}",
    }
