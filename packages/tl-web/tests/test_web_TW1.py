"""The IWP log page: ``GET /web/p/{project}/iwps`` (P2-I2-TW1).

The reads of the page are patched with ``mock.patch.object(WebReadClient, ...)`` and the tl-tui
fake of the IWP reads (``seed_iwp``: 4 IWPs, 6 scope rows on the first; project P123). The real,
unpatched world is read once at the end (the empty state). The five readers are covered by the
walk rows of ``walk.py`` (``test_web_confidentiality_walk.py``); here the rows are checked for the
person readers and the agent is refused.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from tl_core.services.errors import RecordNotFoundError
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

REPO = Path(__file__).resolve().parents[3]
PAGE = "/web/p/P123/iwps"
SCOPE = "project:P123"
PERSON_READERS = ("boss", "ctl", "bob", "amy")


def load_fake() -> Any:  # 4 IWPs, 6 scope rows on the first, 5 constraints, one readiness
    spec = importlib.util.spec_from_file_location(
        "tl_web_tests_fakes_iwp", REPO / "packages/tl-tui/tests/fakes_iwp.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    fake = mod.FakeIwpSupport()
    fake._init_iwp()
    mod.seed_iwp(fake, "P123")
    return fake


def labels_for(w: Any, name: str) -> Any:
    return present.load_labels(present.as_client(w.reads(name)), SCOPE, ("awp.IWP",))


@pytest.fixture(scope="module")
def fake() -> Any:
    return load_fake()


@pytest.fixture
def fakes(fake: Any) -> Iterator[None]:
    def list_iwps(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return fake.list_iwps(project, **kwargs)

    def get_iwp(self: WebReadClient, project: str, number: str) -> Any:
        return fake.get_iwp(project, number)

    def list_iwp_scope(self: WebReadClient, project: str, number: str, **kwargs: Any) -> Any:
        return fake.list_iwp_scope(project, number, **kwargs)

    with (
        mock.patch.object(WebReadClient, "list_iwps", list_iwps),
        mock.patch.object(WebReadClient, "get_iwp", get_iwp),
        mock.patch.object(WebReadClient, "list_iwp_scope", list_iwp_scope),
    ):
        yield


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.iwps as iwps

    assert any(r is iwps.router for r in routers.page_routers())
    assert LOGS["iwps"].SLUG == "iwps"


def test_the_log_rows_and_headers_equal_the_text_module(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    assert doc.headers("log-table")[:3] == ["Number", "Subject", "State"]
    labels = labels_for(world, "bob")
    rows = fake.list_iwps("P123")
    full = [present.iwp_text.iwp_cells(row, labels) for row in rows]
    assert len(rows) == 4
    assert doc.rows("log-table") == htmlkit.project_cells(
        doc.headers("log-table"), present.iwp_text.IWP_COLUMNS, full
    )


@pytest.mark.parametrize("reader", PERSON_READERS)
def test_every_person_reader_sees_the_same_rows(
    world: Any, htmlkit: Any, fake: Any, fakes: None, reader: str
) -> None:
    page = htmlkit.parse(world.web(reader).client.get(PAGE).text)
    assert [r.get("data-number") for r in page.log_rows()] == [
        r.number for r in fake.list_iwps("P123")
    ]


def test_the_agent_is_refused_the_page(world: Any, fakes: None) -> None:
    assert world.web("bot").client.get(PAGE).status_code == 401


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: None) -> None:
    assert htmlkit.parse(world.web("bob").client.get(PAGE).text).status() == "4 IWPs"


def test_the_panel_of_one_iwp_is_the_iwp_page_as_plain_lines(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    number = fake.list_iwps("P123")[0].number
    panel = world.web("bob").client.get(f"{PAGE}/panel/{number}")
    assert panel.status_code == 200
    want = present.iwp_text.iwp_page(
        fake.get_iwp("P123", number),
        fake.list_iwp_scope("P123", number),
        labels_for(world, "bob"),
        technical=False,
        panel=True,
    )
    assert htmlkit.missing_facts(htmlkit.parse(panel.text).root, want) == []


def test_the_filter_and_an_unknown_number(world: Any, htmlkit: Any, fake: Any, fakes: None) -> None:
    bob = world.web("bob").client
    number = fake.list_iwps("P123")[1].number
    found = htmlkit.parse(bob.get(PAGE, params={"q": number}).text)
    assert [r.get("data-number") for r in found.log_rows()] == [number]
    one = bob.get(f"{PAGE}/panel/P123-IWP-XXX-9999")
    two = bob.get(f"{PAGE}/panel/P123-IWP-YYY-9998")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_a_read_that_says_not_found_is_the_same_404(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    listed = fake.list_iwps("P123")[2].number

    def get_iwp(self: WebReadClient, project: str, number: str) -> Any:
        if number == listed:
            raise RecordNotFoundError(f"no IWP {number!r}")
        return fake.get_iwp(project, number)

    bob = world.web("bob").client
    with mock.patch.object(WebReadClient, "get_iwp", get_iwp):
        hidden = bob.get(f"{PAGE}/panel/{listed}")
    unknown = bob.get(f"{PAGE}/panel/P123-IWP-XXX-9999")
    assert hidden.status_code == unknown.status_code == 404
    assert hidden.content == unknown.content


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: None) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_the_actions_bar_holds_only_the_open_link(world: Any, htmlkit: Any, fakes: None) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.buttons() == []
    bar = doc.by_id("log-actions")
    assert bar is not None and bar.find("a", id="log-open") is not None
    assert "data-command" not in bar.text()


def test_the_real_world_has_an_empty_iwp_log(world: Any, htmlkit: Any) -> None:
    """No patch: the world has no IWPs, so the table is empty, the status says 0 and any panel is
    the same 404."""
    bob = world.web("bob").client
    page = htmlkit.parse(bob.get(PAGE).text)
    assert page.log_rows() == []
    assert page.status() == "0 IWPs"
    missing = bob.get(f"{PAGE}/panel/P123-IWP-PIP-0001")
    assert missing.status_code == 404
    assert missing.content == bob.get(f"{PAGE}/panel/P123-IWP-XXX-9999").content
