"""The record screen: the frame, Details, Properties and History (P2-WEB1-S6).

The text of each part is computed here by calling the terminal's pure modules (``record_text``,
``properties_text``, ``details``) on reads from ``world.reads(name)``, so the web and the terminal
share one implementation. A planted ``<`` in a subject must show escaped on every tab.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from tl_api.errors import body_for
from tl_web import present
from tl_web.pages import record as record_page

P = "/web/p/P123"
SCOPE = "project:P123"


def url(w: Any, key: str, query: str = "") -> str:
    return f"{P}/records/{w.ids[key]}{query}"


def labels_of(w: Any, name: str, record: dict[str, Any]) -> Any:
    return present.load_labels(
        present.as_client(w.reads(name)), SCOPE, ("core.Record", str(record["type"]))
    )


def record_of(w: Any, name: str, key: str) -> dict[str, Any]:
    row = w.reads(name).get_record_by_id(w.ids[key])
    assert row is not None, (name, key)
    return row


def expected_details(w: Any, name: str, record: dict[str, Any], *, technical: bool) -> str:
    rows = present.details.details_for(
        present.as_client(w.reads(name)), "P123", record, labels_of(w, name, record),
        record_page.mode_for(technical),
    )  # fmt: skip
    return present.record_text.details_lines(rows)


def expected_properties(w: Any, name: str, record: dict[str, Any], *, technical: bool) -> str:
    reader = w.reads(name)
    try:
        meta = reader.form_metadata(SCOPE, record["type"], record["id"])
        report = reader.conformance(record["id"])
    except Exception as exc:  # noqa: BLE001
        mapped = body_for(exc)
        assert mapped is not None, f"properties read raised {exc!r}"
        return f"Properties unavailable: {mapped[1].message}"
    return present.properties_text.psets_text(meta, record, report, technical=technical)


def expected_header(
    w: Any, name: str, record: dict[str, Any], *, technical: bool
) -> tuple[str, str]:
    reader = w.reads(name)
    badges = present.record_text.badges_text(
        reader.workflow_status(record["id"]).entered_at,
        reader.link_counts([record["id"]]).get(record["id"]),
    )
    parts = present.record_text.header_parts(record, badges, technical=technical)
    return parts.identity, f"{parts.status}{parts.version} · {parts.mark}{parts.rest}"


class Page:
    """The parts of a record page: h1, the state line, the tab links, the body text and table."""

    def __init__(self, htmlkit: Any, text: str) -> None:
        self.doc = htmlkit.parse(text)
        header = self.doc.by_id("rec-header")
        self.h1 = header.find("h1").text() if header and header.find("h1") else ""
        self.state = header.find("p").text() if header and header.find("p") else ""
        self.nav = [
            (a.get("href"), a.text(), a.get("aria-current") == "page")
            for a in (
                self.doc.by_id("rec-tabs").find_all("a") if self.doc.by_id("rec-tabs") else []
            )
        ]
        self.pre = self.doc.pre("rec-body")
        self.headers = self.doc.headers("rec-body")
        self.rows = self.doc.rows("rec-body")

    @property
    def tab_names(self) -> list[str]:
        return [href.split("tab=")[1].split("&")[0] for href, _, _ in self.nav]


@pytest.fixture
def ghost_and_probe() -> Iterator[None]:
    """A fake tab ``probe`` and an invisible tab ``ghost``; both are gone after the test."""
    record_page.load_tab_modules()
    record_page.tab(
        record_page.Tab(
            "probe",
            "Probe",
            "record/details.html",
            lambda ctx: {"lines": f"probe {ctx.project} <b>"},
        )
    )
    record_page.tab(
        record_page.Tab(
            "ghost", "Ghost", "details.html", lambda ctx: {"lines": "ghost"}, lambda ctx: False
        )
    )
    try:
        yield
    finally:
        record_page.TABS.pop("probe", None)
        record_page.TABS.pop("ghost", None)


def test_the_frame_has_its_regions_in_order_and_the_header_of_header_parts(
    world: Any, htmlkit: Any
) -> None:
    response = world.web("bob").client.get(url(world, "open_rfi"))
    assert response.status_code == 200
    page = Page(htmlkit, response.text)
    assert page.doc.regions(htmlkit.RECORD_REGIONS) == list(htmlkit.RECORD_REGIONS)
    record = record_of(world, "bob", "open_rfi")
    identity, state = expected_header(world, "bob", record, technical=False)
    assert (page.h1, page.state) == (identity, state)
    assert f"v{record['version']}" not in state  # the version is for an admin
    assert "<script" not in response.text.split("<main>")[1]


def test_the_nav_lists_the_registered_tabs_with_details_current(world: Any, htmlkit: Any) -> None:
    page = Page(htmlkit, world.web("bob").client.get(url(world, "open_rfi")).text)
    registered = [n for n in record_page.ORDER if n in record_page.TABS]
    assert page.tab_names == registered
    assert [href for href, _, current in page.nav if current] == ["?tab=details"]
    assert [label for _, label, _ in page.nav[:3]] == ["Details", "Properties", "Links"]


@pytest.mark.parametrize("key", ["open_rfi", "waiting"])
def test_details_equal_details_lines(world: Any, htmlkit: Any, key: str) -> None:
    record = record_of(world, "bob", key)
    got = Page(htmlkit, world.web("bob").client.get(url(world, key)).text)
    want = expected_details(world, "bob", record, technical=False)
    assert got.pre == want and want != ""


@pytest.mark.parametrize("key", ["open_rfi", "waiting"])
def test_properties_equal_psets_text(world: Any, htmlkit: Any, key: str) -> None:
    record = record_of(world, "bob", key)
    got = Page(htmlkit, world.web("bob").client.get(url(world, key, "?tab=properties")).text)
    assert got.pre == expected_properties(world, "bob", record, technical=False)


@pytest.mark.parametrize("key", ["open_rfi", "waiting"])
def test_history_rows_equal_history_cells_newest_first(world: Any, htmlkit: Any, key: str) -> None:
    record = record_of(world, "bob", key)
    events = world.reads("bob").history(record["id"])
    labels = labels_of(world, "bob", record)
    got = Page(htmlkit, world.web("bob").client.get(url(world, key, "?tab=history")).text)
    rows = [
        list(present.record_text.history_cells(e, labels, technical=False))
        for e in reversed(events)
    ]
    assert got.headers == ["When", "What", "By", "Summary"]
    assert got.rows == rows and len(rows) > 0


def test_history_in_technical_mode_has_the_raw_columns_for_an_admin(
    world: Any, htmlkit: Any
) -> None:
    record = record_of(world, "boss", "open_rfi")
    labels = labels_of(world, "boss", record)
    got = Page(
        htmlkit,
        world.web("boss").client.get(url(world, "open_rfi", "?tab=history&mode=technical")).text,
    )
    rows = [
        list(present.record_text.history_cells(e, labels, technical=True))
        for e in reversed(world.reads("boss").history(record["id"]))
    ]
    assert got.headers == ["#", "When", "Event", "Actor", "Summary"]
    assert got.rows == rows and len(rows) > 0


@pytest.mark.parametrize("tab", ["details", "properties", "history"])
def test_planted_markup_in_a_subject_shows_escaped_on_every_tab(
    world: Any, htmlkit: Any, k: Any, tab: str
) -> None:
    raw = world.web("bob").client.get(url(world, "planted", f"?tab={tab}")).text
    for tag in ("<i>", "</i>", "<u>", "</u>"):
        assert tag not in raw, f"{tab}: raw {tag} in the page"
    assert "Plant &lt;i&gt;bold&lt;/i&gt;" in raw  # the subject, in the header
    if tab == "details":
        assert "Why &lt;u&gt;this&lt;/u&gt;?" in raw  # the question
    page = Page(htmlkit, raw)
    assert page.h1.endswith(k.PLANTED)  # the parser unescapes: the text is the subject, as text


def test_a_plain_user_asking_for_technical_gets_plain_and_the_notice(
    world: Any, htmlkit: Any
) -> None:
    record = record_of(world, "bob", "open_rfi")
    bob = world.web("bob").client
    response = bob.get(url(world, "open_rfi", "?mode=technical"))
    assert htmlkit.parse(response.text).status() == present.REFUSAL
    page = Page(htmlkit, response.text)
    assert page.pre == expected_details(world, "bob", record, technical=False)
    assert f"v{record['version']}" not in page.state
    assert "mode=technical" not in response.text  # not carried on a link
    assert htmlkit.parse(bob.get(url(world, "open_rfi")).text).status() == ""


def test_an_admin_gets_the_raw_rows_the_version_and_the_mode_on_every_tab_link(
    world: Any, htmlkit: Any
) -> None:
    record = record_of(world, "boss", "open_rfi")
    boss = world.web("boss").client
    response = boss.get(url(world, "open_rfi", "?mode=technical"))
    assert htmlkit.parse(response.text).status() != present.REFUSAL
    page = Page(htmlkit, response.text)
    want = expected_details(world, "boss", record, technical=True)
    assert page.pre == want
    assert want != expected_details(world, "boss", record, technical=False)  # a real difference
    assert page.state == expected_header(world, "boss", record, technical=True)[1]
    assert f" · v{record['version']}" in page.state
    assert all(href.endswith("&mode=technical") for href, _, _ in page.nav)
    assert "mode=technical" not in boss.get(url(world, "open_rfi")).text  # never stored


@pytest.mark.parametrize("key", ["open_rfi", "waiting", "closed"])
def test_the_actions_bar_is_the_log_pages_bar(world: Any, htmlkit: Any, key: str) -> None:
    bob = world.web("bob").client
    mine = htmlkit.parse(bob.get(url(world, key)).text)
    log = htmlkit.parse(bob.get(f"{P}/rfis?sel={world.numbers[key]}").text)
    assert mine.commands() == log.commands()

    def urls(doc: Any) -> list[str]:
        return [b.get("hx-post") or b.get("hx-get") for b in doc.buttons()]

    assert urls(mine) == urls(log)
    assert mine.by_id("log-open") is None  # no "open record" link on the record page itself


def test_the_bars_are_not_empty_for_some_record(world: Any, htmlkit: Any) -> None:
    seen = sum(
        len(htmlkit.parse(world.web("bob").client.get(url(world, key)).text).buttons())
        for key in ("open_rfi", "waiting", "closed", "draft")
    )
    assert seen > 0


def test_no_cookie_is_a_redirect_to_sign_in(world: Any) -> None:
    response = world.client().get(url(world, "open_rfi"))
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_hidden_other_project_unknown_and_invisible_tabs_are_one_404(
    world: Any, htmlkit: Any, k: Any, ghost_and_probe: None
) -> None:
    bob = world.web("bob").client
    start = len(world.answers)
    reference = bob.get(f"{P}/records/{k.NEVER}")
    assert reference.status_code == 404
    for key in ("secret_rfi", "restricted_rfi"):
        for query in ("", "?tab=properties", "?tab=history", "?tab=probe", "?tab=links"):
            hidden = bob.get(url(world, key, query))
            assert hidden.status_code == 404, f"{key}{query}"
            assert hidden.content == reference.content, f"{key}{query}"
    others = [
        bob.get(f"/web/p/OTHER/records/{world.ids['open_rfi']}"),  # url project != scope
        bob.get(url(world, "other")),  # a record of another project scope
        bob.get(url(world, "open_rfi", "?tab=nope")),
        bob.get(url(world, "open_rfi", "?tab=ghost")),  # registered, not visible
        bob.get(f"/web/p/bad%20project/records/{world.ids['open_rfi']}"),
    ]
    for response in others:
        assert response.status_code == 404 and response.content == reference.content, response.url
    page = Page(htmlkit, bob.get(url(world, "open_rfi")).text)
    assert "ghost" not in page.tab_names  # an invisible tab is not in the nav
    secrets = (
        "SECRETRFITOKEN", "RESTSECRET",
        world.numbers["secret_rfi"], world.numbers["restricted_rfi"],
        world.ids["secret_rfi"], world.ids["restricted_rfi"],
    )  # fmt: skip
    for response in world.answers[start:]:
        for secret in secrets:
            assert secret.encode() not in response.content, secret


def test_a_registered_tab_is_in_the_nav_and_at_its_name(
    world: Any, htmlkit: Any, ghost_and_probe: None
) -> None:
    response = world.web("bob").client.get(url(world, "open_rfi", "?tab=probe"))
    assert response.status_code == 200
    page = Page(htmlkit, response.text)
    assert page.pre == "probe P123 <b>"
    assert "<b>" not in response.text.split("rec-body")[1]  # the value is escaped
    assert [current for _, _, current in page.nav].count(True) == 1
    assert page.nav[-1][1:] == ("Probe", True)  # unnamed tabs follow the ordered ones


def test_a_second_tab_of_the_same_name_is_refused(ghost_and_probe: None) -> None:
    with pytest.raises(ValueError):
        record_page.tab(record_page.Tab("probe", "Again", "details.html", lambda ctx: {}))


def test_a_tab_may_not_return_a_name_of_the_frame(world: Any, ghost_and_probe: None) -> None:
    record_page.tab(record_page.Tab("clash", "Clash", "details.html", lambda ctx: {"record": 1}))
    try:
        with pytest.raises(ValueError):
            world.web("bob").client.get(url(world, "open_rfi", "?tab=clash"))
    finally:
        del record_page.TABS["clash"]


def test_a_tab_module_that_does_not_exist_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    record_page.load_tab_modules()
    monkeypatch.setattr(record_page, "_loaded", False)
    monkeypatch.setattr(
        record_page, "TAB_MODULES", (*record_page.TAB_MODULES, "tl_web.pages.record_nowhere")
    )
    record_page.load_tab_modules()
    assert record_page._loaded  # pyright: ignore[reportPrivateUsage]
    assert not record_page._exists("tl_web.pages.record_nowhere")  # pyright: ignore


@pytest.mark.parametrize("key", ["open_rfi", "waiting", "closed"])
def test_no_technical_wording_in_any_tab_for_a_plain_user(
    world: Any, htmlkit: Any, ghost_and_probe: None, key: str
) -> None:
    bob = world.web("bob").client
    record = record_of(world, "bob", key)
    labels = labels_of(world, "bob", record)
    for tab in ("details", "properties", "history", "probe"):
        text = htmlkit.parse(bob.get(url(world, key, f"?tab={tab}")).text).visible_text()
        assert present.find_technical(text, labels) == [], f"{key} {tab}"
