"""The RFI log page: ``GET /web/p/{project}/rfis`` (S4 checks d and f, T15).

The columns, cells, panel and summary are the terminal's own functions (``rfi_text``); the rows are
what ``WebReadClient.list_rfis`` gives the viewer, so a hidden RFI is not among them, not in the
count, not in the status line and not in a link.
"""

from __future__ import annotations

from typing import Any

import pytest
from tl_web import present, routers
from tl_web.log import LOGS

P = "/web/p/P123"
KEPT = ("Number", "Subject", "State")


def labels_for(w: Any, name: str) -> Any:
    return present.load_labels(
        present.as_client(w.reads(name)), "project:P123", ("correspondence.TechnicalItem",)
    )


def expected_rows(w: Any, name: str, *, technical: bool) -> list[tuple[str, ...]]:
    labels = labels_for(w, name)
    return [
        present.rfi_text.rfi_cells(line, labels, technical=technical)
        for line in w.reads(name).list_rfis("P123").lines
    ]


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.rfis as rfis

    assert any(r is rfis.router for r in routers.page_routers())
    assert LOGS["rfis"].SLUG == "rfis"


def test_seven_regions_in_order_and_the_columns_start_number_subject_state(
    world: Any, htmlkit: Any
) -> None:
    page = world.web("bob").client.get(f"{P}/rfis")
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    assert doc.headers("log-table")[:3] == list(KEPT)


def test_the_cells_are_rfi_cells_of_the_same_fixture(world: Any, htmlkit: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(f"{P}/rfis").text)
    full = expected_rows(world, "bob", technical=False)
    names = present.rfi_text.RFI_COLUMNS
    assert len(doc.log_rows()) == len(full) >= 4
    assert doc.rows("log-table") == htmlkit.project_cells(doc.headers("log-table"), names, full)
    # one row, compared cell by cell with the terminal's function for the same RFI
    line = next(
        r
        for r in world.reads("bob").list_rfis("P123").lines
        if r.number == world.numbers["waiting"]
    )
    cells = present.rfi_text.rfi_cells(line, labels_for(world, "bob"), technical=False)
    row = next(r for r in doc.log_rows() if r.get("data-number") == line.number)
    shown = [names.index(h) for h in doc.headers("log-table")]
    assert doc.cells(row) == [cells[i] for i in shown]


def test_the_columns_rule_drops_a_constant_column_and_keeps_a_varying_one(
    world: Any, htmlkit: Any
) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(f"{P}/rfis").text)
    full = expected_rows(world, "bob", technical=False)
    names = present.rfi_text.RFI_COLUMNS
    shown = set(doc.headers("log-table"))
    for index, name in enumerate(names):
        distinct = {cells[index] for cells in full}
        if name in KEPT:
            assert name in shown
        elif len(distinct) > 1:
            assert name in shown, f"varying column {name} is dropped"
        else:
            assert name not in shown, f"constant column {name} is shown"


def test_a_row_is_selected(world: Any, htmlkit: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(f"{P}/rfis").text)
    assert [r.get("aria-selected") for r in doc.log_rows()].count("true") == 1


def test_the_panel_is_the_terminals_page_as_html(world: Any, htmlkit: Any) -> None:
    number = world.numbers["open_rfi"]
    reader = world.reads("bob")
    view = reader.get_rfi("P123", number)
    page = present.rfi_text.rfi_page(
        view,
        labels_for(world, "bob"),
        technical=False,
        client=present.as_client(reader),
        project="P123",
    )
    panel = world.web("bob").client.get(f"{P}/rfis/panel/{number}")
    assert panel.status_code == 200
    got = htmlkit.parse(panel.text)
    assert got.pre() == ""  # no terminal text: the page is HTML
    root = got.by_id("log-panel") or got.root
    assert root.find("h2", class_="tl-page-id").text() == page.identity
    assert (
        root.find("span", class_=f"tl-badge tl-{present.state_tone(page.state)}").text()
        == page.state
    )
    assert [h.text() for h in root.find_all("h3")] == [sec.heading for sec in page.sections]
    props = [p for sec in page.sections for p in sec.items if isinstance(p, present.layout.Prop)]
    assert props
    shown = [n.text() for n in root.find_all("dt")] + [n.text() for n in root.find_all("dd")]
    for prop in props:
        assert prop.label in shown
        assert (prop.value or present.layout.EMPTY) in shown
    for region in ("log-crumb", "log-actions", "log-status"):
        node = got.by_id(region)
        assert node is not None and node.get("hx-swap-oob") == "true", region
    assert f"{number}: " in got.region_text("log-crumb")


def test_the_status_line_is_the_rfi_summary(world: Any, htmlkit: Any) -> None:
    summary = present.rfi_text.rfi_summary(world.reads("bob").list_rfis("P123"))
    got = htmlkit.parse(world.web("bob").client.get(f"{P}/rfis").text).status()
    assert got == summary


def test_hidden_rfis_answer_the_bytes_of_an_unknown_number_and_leave_no_text(
    world: Any, k: Any
) -> None:
    bob = world.web("bob").client
    start = len(world.answers)
    reference = bob.get(f"{P}/rfis/panel/P123-RFI-9999")
    assert reference.status_code == 404
    for hidden in ("secret_rfi", "restricted_rfi"):
        answer = bob.get(f"{P}/rfis/panel/{world.numbers[hidden]}")
        assert answer.status_code == 404 and answer.content == reference.content, hidden
    selected = bob.get(f"{P}/rfis?sel={world.numbers['secret_rfi']}")  # a hidden number as sel
    assert selected.status_code == 200  # the page answers, the hidden row is absent
    bob.get(f"{P}/rfis?q=secretrfitoken")
    bob.get(f"{P}/rfis?q=restsecret")
    unknown = bob.get("/web/nowhere")
    assert unknown.content == reference.content  # the one 404 page
    assert bob.get(f"{P}/nolog/panel/{world.numbers['open_rfi']}").content == reference.content
    secrets = (
        "SECRETRFITOKEN", "RESTSECRET",
        world.numbers["secret_rfi"], world.numbers["restricted_rfi"],
        world.ids["secret_rfi"], world.ids["restricted_rfi"],
    )  # fmt: skip
    for response in world.answers[start:]:
        for secret in secrets:
            assert secret.encode() not in response.content, secret


def test_the_filter_works_on_the_rows(world: Any, htmlkit: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(f"{P}/rfis?q=awaiting").text)
    numbers = [r.get("data-number") for r in doc.log_rows()]
    assert world.numbers["waiting"] in numbers
    assert world.numbers["closed"] not in numbers


def test_technical_mode_is_plain_with_a_notice_for_a_non_admin(world: Any, htmlkit: Any) -> None:
    bob = world.web("bob").client
    labels = labels_for(world, "bob")
    for path in (
        f"{P}/rfis?mode=technical",
        f"{P}/rfis/panel/{world.numbers['open_rfi']}?mode=technical",
    ):
        assert htmlkit.parse(bob.get(path).text).status() == present.REFUSAL, path
    plain = htmlkit.parse(bob.get(f"{P}/rfis?mode=technical").text)
    lines = world.reads("bob").list_rfis("P123").lines
    names = present.rfi_text.RFI_COLUMNS
    cells = [present.rfi_text.rfi_cells(line, labels, technical=False) for line in lines]
    assert plain.rows("log-table") == htmlkit.project_cells(
        plain.headers("log-table"), names, cells
    )
    assert "mode=technical" not in bob.get(f"{P}/rfis?mode=technical").text


def test_an_admin_gets_the_raw_cells_and_the_mode_on_the_links_only_for_the_request(
    world: Any, htmlkit: Any
) -> None:
    boss = world.web("boss").client
    technical = htmlkit.parse(boss.get(f"{P}/rfis?mode=technical").text)
    assert technical.status() != present.REFUSAL
    labels = labels_for(world, "boss")
    lines = world.reads("boss").list_rfis("P123").lines
    names = present.rfi_text.RFI_COLUMNS
    raw = [present.rfi_text.rfi_cells(line, labels, technical=True) for line in lines]
    plain = [present.rfi_text.rfi_cells(line, labels, technical=False) for line in lines]
    assert raw != plain  # the fixture shows a difference
    assert technical.rows("log-table") == htmlkit.project_cells(
        technical.headers("log-table"), names, raw
    )
    assert "mode=technical" in boss.get(f"{P}/rfis?mode=technical").text
    assert "mode=technical" not in boss.get(f"{P}/rfis").text  # never stored


def test_no_cookie_is_a_redirect_to_sign_in(world: Any) -> None:
    response = world.client().get(f"{P}/rfis")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/web/sign-in")


@pytest.mark.parametrize("name", ["bad%20project", "x" * 80])
def test_a_bad_project_name_is_the_404_page(world: Any, name: str) -> None:
    bob = world.web("bob").client
    assert bob.get(f"/web/p/{name}/rfis").content == bob.get("/web/nowhere").content
