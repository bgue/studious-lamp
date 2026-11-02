"""The log standard (``tl_web.log.WebLog``) on a log of its own (P2-WEB1-S4 checks d, f; D17).

The real pages (RFIs, correspondence, documents) have their own test files. This file builds one
fake ``WebLog`` page, ``/web/p/{project}/weblogfake``, in a module that exists only for the test
(the recipe of ``tl_web.log``), and checks what every log shares: the seven regions, the columns
rule, the selection, the filter, the technical mode, the htmx partial, the actions bar and the
404 page.
"""

from __future__ import annotations

import importlib.machinery
import sys
import types
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from tl_web import present, routers
from tl_web.log import LOGS, WebAction, WebLog, action_views, offered_actions, register

FAKE = "tl_web_tests_fake_log"
SOURCE = """
from types import SimpleNamespace as Row

from fastapi import Request, Response
from tl_web.log import WebAction, WebLog, register
from tl_web.webroute import web_router

router = web_router()
ROWS = [
    Row(id="id-1", number="WL-1", subject="Alpha <b>bold</b>", state="Open", flag="a"),
    Row(id="id-2", number="WL-2", subject="Beta", state="Open", flag="b"),
    Row(id="id-3", number="WL/3", subject="Gamma", state="Closed", flag="b"),
]


class FakeLog(WebLog):
    LOG_NAME = "Fake log"
    KEY_HINTS = "hints here"

    def columns(self):
        return ("Number", "Subject", "State", "Kind", "Flag", "Extra")

    def drop_order(self):
        return ("Extra",)

    def load_rows(self):
        return ROWS

    def row_key(self, row):
        return row.id

    def row_record(self, row):
        return (row.number, row.subject)

    def row_cells(self, row):
        extra = "tech-" + row.id if self.technical else row.id
        return (row.number, row.subject, row.state, "same", row.flag, extra)

    def panel_text(self, row):
        return [f"panel of {row.number}", "<i>raw</i> & more"] if row else ["Nothing here."]

    def actions_for(self, row):
        if row.number == "WL-1":
            return [
                WebAction("a", "Do it", "SubmitTechnical"),
                WebAction("b", "Ask", "AnswerTechnical", asks=True),
            ]
        return []

    def summary_text(self):
        return "3 fake rows"


register("weblogfake", FakeLog)


@router.get("/p/{project}/weblogfake")
def fake_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return FakeLog.page(request, project, q=q, sel=sel, mode=mode)
"""


@pytest.fixture(scope="module")
def fake(world: Any, monkeypatch_module: pytest.MonkeyPatch) -> Iterator[Any]:
    """The world's app rebuilt with the fake page mounted; ``fake.client(name)`` signs in."""
    module = types.ModuleType(FAKE)
    module.__spec__ = importlib.machinery.ModuleSpec(FAKE, None)
    sys.modules[FAKE] = module
    exec(compile(SOURCE, FAKE, "exec"), module.__dict__)  # noqa: S102
    monkeypatch_module.setattr(routers, "PAGE_MODULES", (*routers.PAGE_MODULES, FAKE))
    app = world.make_app()

    def client(name: str) -> Any:
        return world.client(world.web(name).token, app=app)

    try:
        yield SimpleNamespace(client=client, world=world)
    finally:
        LOGS.pop("weblogfake", None)
        sys.modules.pop(FAKE, None)


PAGE = "/web/p/P123/weblogfake"


def test_the_page_has_the_seven_regions_in_order(fake: Any, htmlkit: Any) -> None:
    page = htmlkit.parse(fake.client("bob").get(PAGE).text)
    assert page.regions() == list(htmlkit.LOG_REGIONS)
    assert page.region_text("log-keys").strip() == "hints here"
    assert page.status() == "3 fake rows"
    assert page.region_text("log-crumb").strip() == "P123 › Fake log › WL-1: Alpha <b>bold</b>"


def test_a_column_that_is_the_same_in_every_row_is_dropped(fake: Any, htmlkit: Any) -> None:
    page = htmlkit.parse(fake.client("bob").get(PAGE).text)
    assert page.headers("log-table") == ["Number", "Subject", "State", "Flag", "Extra"]
    rows = page.rows("log-table")
    assert rows[0] == ["WL-1", "Alpha <b>bold</b>", "Open", "a", "id-1"]
    assert len(rows) == 3


def test_one_row_hides_no_column(fake: Any, htmlkit: Any) -> None:
    page = htmlkit.parse(fake.client("bob").get(PAGE, params={"q": "alpha"}).text)
    assert page.headers("log-table") == ["Number", "Subject", "State", "Kind", "Flag", "Extra"]
    assert [r[0] for r in page.rows("log-table")] == ["WL-1"]


def test_the_columns_carry_their_classes(fake: Any, htmlkit: Any) -> None:
    page = htmlkit.parse(fake.client("bob").get(PAGE).text)
    classes = {th.text(): th.get("class") for th in page.by_id("log-table").find_all("th")}
    assert classes["Subject"] == "tl-flex"
    assert classes["State"] == "tl-state"
    assert classes["Extra"] == "tl-drop"
    assert classes["Number"] == ""


def test_the_first_row_is_selected_unless_sel_names_another(fake: Any, htmlkit: Any) -> None:
    bob = fake.client("bob")
    first = htmlkit.parse(bob.get(PAGE).text)
    assert [r.get("aria-selected") for r in first.log_rows()] == ["true", "false", "false"]
    second = htmlkit.parse(bob.get(PAGE, params={"sel": "WL-2"}).text)
    assert [r.get("aria-selected") for r in second.log_rows()] == ["false", "true", "false"]
    assert "panel of WL-2" in second.pre("log-panel")
    unknown = htmlkit.parse(bob.get(PAGE, params={"sel": "NOPE"}).text)
    assert unknown.log_rows()[0].get("aria-selected") == "true"  # falls back to the first


def test_the_panel_text_is_escaped_not_markup(fake: Any, htmlkit: Any) -> None:
    raw = fake.client("bob").get(PAGE).text
    assert "<i>raw</i>" not in raw and "&lt;i&gt;raw&lt;/i&gt; &amp; more" in raw
    assert "<b>bold</b>" not in raw


def test_the_filter_narrows_the_rows_and_echoes_escaped(fake: Any, htmlkit: Any) -> None:
    bob = fake.client("bob")
    found = htmlkit.parse(bob.get(PAGE, params={"q": "closed"}).text)
    assert [r[0] for r in found.rows("log-table")] == ["WL/3"]
    nothing = htmlkit.parse(bob.get(PAGE, params={"q": "zzz"}).text)
    assert nothing.log_rows() == [] and "No items." in nothing.region_text("log-table")
    hostile = bob.get(PAGE, params={"q": '"><script>alert(1)</script>'})
    assert "<script>alert(1)" not in hostile.text
    assert htmlkit.parse(hostile.text).inline_problems() == []


def test_a_number_with_a_slash_has_a_working_panel_url(fake: Any, htmlkit: Any) -> None:
    bob = fake.client("bob")
    page = htmlkit.parse(bob.get(PAGE).text)
    url = [r.get("hx-get") for r in page.log_rows()][2]
    assert url == "/web/p/P123/weblogfake/panel/WL/3"  # `{number:path}` keeps the slash
    assert bob.get(url).status_code == 200


def test_the_actions_bar_lists_the_offers_of_the_selected_row(fake: Any, htmlkit: Any) -> None:
    page = htmlkit.parse(fake.client("bob").get(PAGE).text)
    plain, asking = page.buttons()
    assert plain.get("data-command") == "SubmitTechnical"
    assert plain.get("hx-post") == "/web/p/P123/records/id-1/do/SubmitTechnical"
    assert plain.get("hx-target") == "#log-status"
    assert asking.get("hx-get") == "/web/p/P123/records/id-1/do/AnswerTechnical/form"
    assert asking.get("hx-target") == "#log-panel"
    assert "hx-post" not in asking.attrs
    assert plain.text().startswith("[a] Do it")
    other = htmlkit.parse(fake.client("bob").get(PAGE, params={"sel": "WL-2"}).text)
    assert other.buttons() == []
    link = other.by_id("log-open")
    assert link is not None and link.get("href") == "/web/p/P123/records/id-2"


def test_the_partial_swaps_crumb_actions_and_status_out_of_band(fake: Any, htmlkit: Any) -> None:
    response = fake.client("bob").get("/web/p/P123/weblogfake/panel/WL-1")
    assert response.status_code == 200
    part = htmlkit.parse(response.text)
    for region in ("log-crumb", "log-actions", "log-status"):
        node = part.by_id(region)
        assert node is not None and node.get("hx-swap-oob") == "true", region
    assert part.pre() == "panel of WL-1\n<i>raw</i> & more"
    assert "<html" not in response.text  # a fragment, not a page


def test_an_unknown_number_log_or_project_is_the_one_404_page(fake: Any) -> None:
    bob = fake.client("bob")
    reference = bob.get("/web/nowhere")
    answers = [
        bob.get("/web/p/P123/weblogfake/panel/NOPE"),
        bob.get("/web/p/P123/nolog/panel/WL-1"),
        bob.get("/web/p/bad%20project/weblogfake"),
        bob.get("/web/p/bad%20project/weblogfake/panel/WL-1"),
    ]
    assert {a.status_code for a in answers} == {404}
    assert {a.content for a in answers} == {reference.content}


def test_technical_mode_is_for_an_admin_only_and_never_stored(fake: Any, htmlkit: Any) -> None:
    bob, boss = fake.client("bob"), fake.client("boss")
    refused = htmlkit.parse(bob.get(PAGE, params={"mode": "technical"}).text)
    assert refused.status() == present.REFUSAL  # the notice replaces the summary
    assert refused.rows("log-table")[0][-1] == "id-1"  # plain cells
    assert "mode=technical" not in bob.get(PAGE, params={"mode": "technical"}).text
    page = htmlkit.parse(boss.get(PAGE, params={"mode": "technical"}).text)
    assert page.status() == "3 fake rows"
    assert page.rows("log-table")[0][-1] == "tech-id-1"
    assert all("mode=technical" in r.get("hx-get") for r in page.log_rows())
    assert all(r.get("data-open").endswith("?mode=technical") for r in page.log_rows())
    hidden = [n for n in page.all() if n.tag == "input" and n.get("name") == "mode"]
    assert [n.get("value") for n in hidden] == ["technical"]
    again = boss.get(PAGE)  # a second request without the query is plain
    assert "mode=technical" not in again.text and "tech-id-1" not in again.text


def test_no_cookie_is_a_redirect_to_sign_in(fake: Any) -> None:
    anon = fake.world.client()
    response = anon.get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


# --- the registry and the helpers ---------------------------------------------------------------


def test_register_refuses_a_bad_slug_and_a_second_class_for_a_slug() -> None:
    class One(WebLog[Any]):
        pass

    class Two(WebLog[Any]):
        pass

    for bad in ("Rfis", "1abc", "has space", "", "x" * 40):
        with pytest.raises(ValueError):
            register(bad, One)
    register("tmp-log-a", One)
    try:
        register("tmp-log-a", One)  # the same class again is fine
        with pytest.raises(ValueError):
            register("tmp-log-a", Two)
        assert One.SLUG == "tmp-log-a"
    finally:
        LOGS.pop("tmp-log-a", None)


def test_offered_actions_follow_the_servers_order_and_the_tables_keys() -> None:
    def offers(*commands: str) -> Any:
        return SimpleNamespace(
            actions=[SimpleNamespace(command=c, label=c.upper()) for c in commands]
        )

    found = offered_actions(
        offers(
            "SubmitTechnical", "VoidDraft", "VoidCorrespondence", "NoSuchCommand", "AnswerTechnical"
        )
    )
    assert [a.command for a in found] == ["SubmitTechnical", "VoidDraft", "AnswerTechnical"]
    assert found[0].label == "SUBMITTECHNICAL"  # the server's label, not the table's
    assert [a.asks for a in found] == [False, True, True]  # a confirmation or a question asks
    own = frozenset({present.ACTION_UI["SubmitTechnical"].key})
    assert "SubmitTechnical" not in [
        a.command for a in offered_actions(offers("SubmitTechnical"), own)
    ]


def test_action_views_build_the_urls_of_the_post_route_and_its_form() -> None:
    views = action_views("P123", "id/with space", [WebAction("a", "Do", "SubmitTechnical")])
    assert views[0]["url"] == "/web/p/P123/records/id%2Fwith%20space/do/SubmitTechnical"
    assert views[0]["form_url"] == views[0]["url"] + "/form"
    assert views[0]["key_label"] == "a"
