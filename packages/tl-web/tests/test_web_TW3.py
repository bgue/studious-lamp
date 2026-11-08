"""The readiness page: ``GET /web/p/{project}/readiness?number=<IWP number>`` (P2-I2-TW3).

The reads of the page are patched with ``mock.patch.object(WebReadClient, ...)`` and the tl-tui
fake of the IWP reads (``seed_iwp``: IWP P123-IWP-PIP-0001 has a readiness of 9 checks; the second
IWP, P123-IWP-PIP-0002, is visible and never evaluated; project P123). The real, unpatched world is
read once at the end (no IWP, so any number is the one 404 page). The five readers are covered by
the walk row of ``walk.py`` (``test_web_confidentiality_walk.py``); here the rows are checked for
the person readers and the agent is refused.
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
PAGE = "/web/p/P123/readiness"
EVALUATED = "P123-IWP-PIP-0001"
NOT_EVALUATED = "P123-IWP-PIP-0002"
PERSON_READERS = ("boss", "ctl", "bob", "amy")


def load_fake() -> Any:  # 4 IWPs, one readiness of 9 checks on the first
    spec = importlib.util.spec_from_file_location(
        "tl_web_tests_fakes_iwp_tw3", REPO / "packages/tl-tui/tests/fakes_iwp.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    fake = mod.FakeIwpSupport()
    fake._init_iwp()
    mod.seed_iwp(fake, "P123")
    return fake


@pytest.fixture(scope="module")
def fake() -> Any:
    return load_fake()


@pytest.fixture
def fakes(fake: Any) -> Iterator[None]:
    def get_iwp_readiness(self: WebReadClient, project: str, number: str) -> Any:
        return fake.get_iwp_readiness(project, number)

    def get_iwp(self: WebReadClient, project: str, number: str) -> Any:
        return fake.get_iwp(project, number)

    with (
        mock.patch.object(WebReadClient, "get_iwp_readiness", get_iwp_readiness),
        mock.patch.object(WebReadClient, "get_iwp", get_iwp),
    ):
        yield


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.readiness as readiness

    assert any(r is readiness.router for r in routers.page_routers())
    assert LOGS["readiness"].SLUG == "readiness"


def test_the_regions_headers_and_rows_equal_the_text_module(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    page = world.web("bob").client.get(PAGE, params={"number": EVALUATED})
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    assert doc.headers("log-table")[:3] == ["Check", "State", "Passing"]
    view = fake.get_iwp_readiness("P123", EVALUATED)
    full = [cells for cells, _ in present.readiness_text.readiness_rows(view)]
    assert len(full) == 9
    assert doc.rows("log-table") == htmlkit.project_cells(
        doc.headers("log-table"), present.readiness_text.READINESS_COLUMNS, full
    )


@pytest.mark.parametrize("reader", PERSON_READERS)
def test_every_person_reader_sees_the_same_rows(
    world: Any, htmlkit: Any, fake: Any, fakes: None, reader: str
) -> None:
    page = htmlkit.parse(world.web(reader).client.get(PAGE, params={"number": EVALUATED}).text)
    view = fake.get_iwp_readiness("P123", EVALUATED)
    assert len(page.log_rows()) == len(present.readiness_text.readiness_rows(view))


def test_the_agent_is_refused_the_page(world: Any, fakes: None) -> None:
    refused = world.web("bot").client.get(PAGE, params={"number": EVALUATED})
    assert refused.status_code == 401


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fake: Any, fakes: None) -> None:
    view = fake.get_iwp_readiness("P123", EVALUATED)
    page = world.web("bob").client.get(PAGE, params={"number": EVALUATED})
    assert htmlkit.parse(page.text).status() == present.readiness_text.readiness_summary(view)


def test_the_page_carries_the_panel_of_the_readiness(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    view = fake.get_iwp_readiness("P123", EVALUATED)
    page = world.web("bob").client.get(PAGE, params={"number": EVALUATED})
    want = present.readiness_text.readiness_page(EVALUATED, view, panel=True)
    assert htmlkit.missing_facts(htmlkit.parse(page.text).root, want) == []


def test_the_panel_of_one_row_is_the_readiness_page(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    view = fake.get_iwp_readiness("P123", EVALUATED)
    panel = world.web("bob").client.get(f"{PAGE}/panel/{EVALUATED}")
    assert panel.status_code == 200
    want = present.readiness_text.readiness_page(EVALUATED, view, panel=True)
    assert htmlkit.missing_facts(htmlkit.parse(panel.text).root, want) == []


def test_a_filter_keeps_the_checks_that_match(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    view = fake.get_iwp_readiness("P123", EVALUATED)
    rows = present.readiness_text.readiness_rows(view)
    mine = [cells for cells, _ in rows if "blocked" in " ".join(cells).lower()]
    found = htmlkit.parse(
        world.web("bob").client.get(PAGE, params={"number": EVALUATED, "q": "blocked"}).text
    )
    assert len(found.log_rows()) == len(mine) == 2


def test_an_iwp_never_evaluated_says_so(world: Any, htmlkit: Any, fakes: None) -> None:
    page = world.web("bob").client.get(PAGE, params={"number": NOT_EVALUATED})
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.log_rows() == []
    assert doc.status() == present.readiness_text.not_evaluated_text(NOT_EVALUATED)


def test_a_hidden_and_an_unknown_iwp_are_the_same_404(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    def readiness(self: WebReadClient, project: str, number: str) -> Any:
        raise RecordNotFoundError(f"no IWP {number!r}")

    def get_iwp(self: WebReadClient, project: str, number: str) -> Any:
        if number == EVALUATED:
            raise RecordNotFoundError(f"no IWP {number!r}")
        return fake.get_iwp(project, number)

    bob = world.web("bob").client
    with (
        mock.patch.object(WebReadClient, "get_iwp_readiness", readiness),
        mock.patch.object(WebReadClient, "get_iwp", get_iwp),
    ):
        hidden = bob.get(PAGE, params={"number": EVALUATED})
    unknown = bob.get(PAGE, params={"number": "P123-IWP-XXX-9999"})
    assert hidden.status_code == unknown.status_code == 404
    assert hidden.content == unknown.content


def test_no_number_is_the_same_404(world: Any, fakes: None) -> None:
    bob = world.web("bob").client
    none = bob.get(PAGE)
    unknown = bob.get(PAGE, params={"number": "P123-IWP-XXX-9999"})
    assert none.status_code == unknown.status_code == 404
    assert none.content == unknown.content


def test_the_panel_of_an_unknown_iwp_is_the_same_404(world: Any, fakes: None) -> None:
    bob = world.web("bob").client
    one = bob.get(f"{PAGE}/panel/P123-IWP-XXX-9999")
    two = bob.get(f"{PAGE}/panel/P123-IWP-YYY-9998")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_the_page_offers_no_action_and_no_link_to_a_record(world: Any, fakes: None) -> None:
    text = world.web("bob").client.get(PAGE, params={"number": EVALUATED}).text
    assert "/records/" not in text
    assert "data-command" not in text


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: None) -> None:
    response = world.client().get(PAGE, params={"number": EVALUATED})
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_the_real_world_has_no_readiness_to_show(world: Any, htmlkit: Any) -> None:
    """No patch: the world has no IWP, so any number is the one 404 page."""
    bob = world.web("bob").client
    missing = bob.get(PAGE, params={"number": EVALUATED})
    assert missing.status_code == 404
    assert missing.content == bob.get(PAGE, params={"number": "P123-IWP-XXX-9999"}).content
