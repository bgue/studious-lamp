"""The constraint log page: ``GET /web/p/{project}/constraints`` (P2-I2-TW2).

The reads of the page are patched with ``mock.patch.object(WebReadClient, ...)`` and the tl-tui
fake of the constraint reads (``seed_iwp``: 5 constraints on two subjects, one blocking; project
P123). The real, unpatched world is read once at the end (the empty state). The five readers are
covered by the walk row of ``walk.py`` (``test_web_confidentiality_walk.py``); here the rows are
checked for the person readers and the agent is refused.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from tl_api.routes.constraints import ConstraintList
from tl_core.services.errors import RecordNotFoundError
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

REPO = Path(__file__).resolve().parents[3]
PAGE = "/web/p/P123/constraints"
SCOPE = "project:P123"
PERSON_READERS = ("boss", "ctl", "bob", "amy")


def load_fake() -> Any:  # 4 IWPs, 6 scope rows, 5 constraints on two subjects, one readiness
    spec = importlib.util.spec_from_file_location(
        "tl_web_tests_fakes_iwp_tw2", REPO / "packages/tl-tui/tests/fakes_iwp.py"
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
    def list_constraints(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return fake.list_constraints(project, **kwargs)

    def get_constraint(self: WebReadClient, project: str, key: str) -> Any:
        return fake.get_constraint(project, key)

    with (
        mock.patch.object(WebReadClient, "list_constraints", list_constraints),
        mock.patch.object(WebReadClient, "get_constraint", get_constraint),
    ):
        yield


def expected_summary(rows: list[Any], subject: str | None = None) -> str:
    blocking = sum(1 for row in rows if row.severity == "blocking")
    aging = sum(1 for row in rows if row.aging)
    text = present.constraint_text.constraint_summary(
        len(rows), len(rows), blocking=blocking, aging=aging
    )
    return f"Constraints on {subject} · {text}" if subject is not None else text


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.constraints as constraints

    assert any(r is constraints.router for r in routers.page_routers())
    assert LOGS["constraints"].SLUG == "constraints"


def test_the_literals_of_the_web_client_are_the_core_constants() -> None:
    """``tl_web`` may not import ``tl_core`` (test_web_imports), so it spells two constants out."""
    import tl_web.pages.constraints as constraints
    from tl_core.constraints.commands import VIEW_WORD
    from tl_core.constraints.queries import MAX_LIMIT

    assert VIEW_WORD == "core.constraint.view"
    assert constraints.MAX_ROWS == MAX_LIMIT


def test_the_rows_and_headers_equal_the_text_module(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    assert doc.headers("log-table")[:3] == ["Constraint", "Subject", "Type"]
    rows = fake.list_constraints("P123").rows
    full = [present.constraint_text.constraint_cells(row) for row in rows]
    assert len(rows) == 5
    assert doc.rows("log-table") == htmlkit.project_cells(
        doc.headers("log-table"), present.constraint_text.CONSTRAINT_COLUMNS, full
    )


@pytest.mark.parametrize("reader", PERSON_READERS)
def test_every_person_reader_sees_the_same_rows(
    world: Any, htmlkit: Any, fake: Any, fakes: None, reader: str
) -> None:
    page = htmlkit.parse(world.web(reader).client.get(PAGE).text)
    assert [r.get("data-number") for r in page.log_rows()] == [
        row.key for row in fake.list_constraints("P123").rows
    ]


def test_the_agent_is_refused_the_page(world: Any, fakes: None) -> None:
    assert world.web("bot").client.get(PAGE).status_code == 401


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fake: Any, fakes: None) -> None:
    rows = fake.list_constraints("P123").rows
    status = htmlkit.parse(world.web("bob").client.get(PAGE).text).status()
    assert status == expected_summary(rows)


def test_an_empty_list_has_the_empty_summary(world: Any, htmlkit: Any, fakes: None) -> None:
    empty = mock.patch.object(
        WebReadClient,
        "list_constraints",
        lambda self, project, **kw: ConstraintList(rows=[], total=0),
    )
    with empty:
        page = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert page.log_rows() == []
    assert page.status() == "0 constraints, 0 blocking, 0 aging"


def test_a_subject_keeps_one_subjects_constraints(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    rows = fake.list_constraints("P123").rows
    subject = rows[0].subject_key
    mine = [row for row in rows if row.subject_key == subject]
    page = htmlkit.parse(world.web("bob").client.get(PAGE, params={"subject": subject}).text)
    assert [r.get("data-number") for r in page.log_rows()] == [row.key for row in mine]
    assert page.status() == expected_summary(mine, subject)


def test_the_panel_of_one_constraint_is_its_page_as_plain_lines(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    key = fake.list_constraints("P123").rows[0].key
    panel = world.web("bob").client.get(f"{PAGE}/panel/{key}")
    assert panel.status_code == 200
    want = present.constraint_text.constraint_page(
        fake.get_constraint("P123", key), technical=False, panel=True
    )
    assert htmlkit.missing_facts(htmlkit.parse(panel.text).root, want) == []


def test_the_filter_and_an_unknown_key(world: Any, htmlkit: Any, fake: Any, fakes: None) -> None:
    bob = world.web("bob").client
    key = fake.list_constraints("P123").rows[1].key
    found = htmlkit.parse(bob.get(PAGE, params={"q": key}).text)
    assert [r.get("data-number") for r in found.log_rows()] == [key]
    one = bob.get(f"{PAGE}/panel/P123-CON-9999")
    two = bob.get(f"{PAGE}/panel/P123-CON-9998")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_a_read_that_says_not_found_is_the_same_404(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    listed = fake.list_constraints("P123").rows[2].key

    def get_constraint(self: WebReadClient, project: str, key: str) -> Any:
        if key == listed:
            raise RecordNotFoundError(f"no constraint {key!r}")
        return fake.get_constraint(project, key)

    bob = world.web("bob").client
    with mock.patch.object(WebReadClient, "get_constraint", get_constraint):
        hidden = bob.get(f"{PAGE}/panel/{listed}")
    unknown = bob.get(f"{PAGE}/panel/P123-CON-9999")
    assert hidden.status_code == unknown.status_code == 404
    assert hidden.content == unknown.content


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: None) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_the_real_world_has_an_empty_constraint_log(world: Any, htmlkit: Any) -> None:
    """No patch: the world has no constraints, so the table is empty and any panel is a 404."""
    bob = world.web("bob").client
    page = htmlkit.parse(bob.get(PAGE).text)
    assert page.log_rows() == []
    missing = bob.get(f"{PAGE}/panel/P123-CON-0001")
    assert missing.status_code == 404
    assert missing.content == bob.get(f"{PAGE}/panel/P123-CON-9999").content
