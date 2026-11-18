"""The forms pages (V3-F3, W2): the list, the fill page of a general template, the bound page.

A page of a general template holds the form model as one JSON data block, the three vendored
files and ``forms.js``, the hidden fields and a ``<noscript>`` line; no inline script other than
the data block, no ``on*`` attribute, no ``style=``, the standard ``/web`` headers.
"""

from __future__ import annotations

import json
from types import ModuleType
from typing import Any

import pytest

PROJECT = "P123"
Q = f"?project={PROJECT}"
VENDOR = "/web/static/vendor/surveyjs"


def page(fw: Any, who: str, path: str, **params: str) -> Any:
    return fw.world.web(who).client.get(path, params={"project": PROJECT, **params})


def links(htmlkit: ModuleType, response: Any) -> list[tuple[str, str]]:
    return htmlkit.parse(response.text).links()


def test_the_list_holds_the_published_general_templates_and_nothing_else(
    forms_world_ro: Any, htmlkit: ModuleType
) -> None:
    fw = forms_world_ro
    got = page(fw, "bob", "/web/forms")
    assert got.status_code == 200
    found = links(htmlkit, got)
    hrefs = [h for h, _ in found if h.startswith("/web/forms/t/")]
    assert sorted(hrefs) == sorted(
        f"/web/forms/t/{fw.ids[n]}?project={PROJECT}" for n in ("talk", "plant")
    )
    assert "Toolbox talk" in got.text and "TPL-0001" in got.text
    assert "Not yet" not in got.text  # a draft template
    assert "Pre-check" not in got.text and "Inspection" not in got.text  # bound forms are not here
    assert "Your drafts" not in got.text  # bob has none


def test_the_list_needs_a_project(forms_world_ro: Any) -> None:
    web = forms_world_ro.world.web("bob")
    assert web.client.get("/web/forms").status_code == 404
    assert web.client.get("/web/forms", params={"project": "../x"}).status_code == 404


def test_the_fill_page_of_a_general_template(
    forms_world_ro: Any, htmlkit: ModuleType, k: Any
) -> None:
    fw = forms_world_ro
    got = page(fw, "bob", f"/web/forms/t/{fw.ids['talk']}")
    assert got.status_code == 200
    doc = htmlkit.parse(got.text)
    block = doc.by_id("form-model")
    assert block is not None and block.attrs["type"] == "application/json"
    model = json.loads(block.text())
    assert [e["name"] for e in model["pages"][0]["elements"]] == ["topic", "count"]
    assert model["clearInvisibleValues"] == "onHidden"
    scripts = [n.attrs.get("src") for n in doc.all() if n.tag == "script" and n.attrs.get("src")]
    assert scripts == [
        f"{VENDOR}/survey.core.min.js",
        f"{VENDOR}/survey-js-ui.min.js",
        "/web/static/forms.js",
    ]
    sheets = [n.attrs["href"] for n in doc.all() if n.tag == "link"]
    assert f"{VENDOR}/survey-core.min.css" in sheets and "/web/static/forms.css" in sheets
    names = {
        n.attrs.get("name")
        for n in doc.all()
        if n.tag == "input" and n.attrs.get("type") == "hidden"
    }
    assert {"csrf", "draft_id", "answers_json"} <= names
    assert doc.by_id("survey") is not None
    assert any(n.tag == "noscript" and "needs a script" in n.text() for n in doc.all())
    inline = [p for p in doc.inline_problems() if p != "script without src"]
    assert inline == ["script with a body"]  # the JSON data block, and nothing else
    assert [n for n in doc.all() if n.tag == "script" and "src" not in n.attrs] == [block]
    assert "Toolbox talk" in got.text and "TPL-0001" in got.text and "version 1" in got.text
    assert "Question pic" in got.text  # the photo field is named, in the line about the terminal
    assert [n for n in doc.all() if n.tag == "p" and "need the terminal" in n.text()]
    for header, value in (
        ("content-security-policy", k.CSP),
        ("x-content-type-options", "nosniff"),
        ("referrer-policy", "same-origin"),
        ("cache-control", "no-store"),
    ):
        assert got.headers[header] == value


def test_an_unpublished_a_bound_and_an_unknown_template_are_the_one_404(
    forms_world_ro: Any,
) -> None:
    fw = forms_world_ro
    web = fw.world.web("bob")
    answers = {
        name: web.client.get(f"/web/forms/t/{tid}", params={"project": PROJECT})
        for name, tid in (
            ("draft", fw.ids["unpublished"]),
            ("checklist", fw.ids["checklist"]),
            ("unknown", "01J000000000000000000000"),
        )
    }
    assert {a.status_code for a in answers.values()} == {404}
    assert len({a.content for a in answers.values()}) == 1


def test_the_bound_page_shows_the_record_key_and_the_form(
    forms_world_ro: Any, htmlkit: ModuleType
) -> None:
    fw = forms_world_ro
    key = fw.keys["insp_open"]
    got = page(fw, "bob", f"/web/forms/for/{key}")
    assert got.status_code == 200
    doc = htmlkit.parse(got.text)
    assert key in got.text and "Inspection open" in got.text
    block = doc.by_id("form-model")
    assert block is not None
    assert [e["name"] for e in json.loads(block.text())["pages"][0]["elements"]] == ["q1", "q2"]
    form = doc.by_id("fill-form")
    assert (
        form is not None
        and form.attrs["action"] == f"/web/forms/for/{key}/submit?project={PROJECT}"
    )
    assert doc.by_id("save-draft") is None  # a bound form has no draft


def test_a_bound_record_with_no_open_form_says_why_and_offers_no_form(
    forms_world: Any, htmlkit: ModuleType
) -> None:
    fw = forms_world
    fw.run("bob", "RecordInspectionResult", inspection=fw.ids["insp_done"],
           answers=[{"q": "q1", "value": "yes", "note": None}])  # fmt: skip
    got = page(fw, "bob", f"/web/forms/for/{fw.keys['insp_done']}")
    assert got.status_code == 200
    doc = htmlkit.parse(got.text)
    assert "takes no form now" in got.text and "already" in got.text
    assert doc.by_id("form-model") is None and doc.by_id("fill-form") is None


@pytest.mark.parametrize("who", ["bob", "boss", "amy"])
def test_a_bound_page_is_not_offered_for_a_key_that_is_not_a_record(
    forms_world_ro: Any, who: str
) -> None:
    got = page(forms_world_ro, who, "/web/forms/for/P123-INS-9999")
    assert got.status_code == 404
