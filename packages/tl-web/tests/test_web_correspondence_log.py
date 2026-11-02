"""The correspondence register page: ``GET /web/p/{project}/correspondence`` (P2-WEB1-T01, D22).

The register mode of the terminal's correspondence screen in the log standard: the columns, cells,
panel and summary are ``tl_tui.correspondence_text``'s. The status line counts every row the read
loaded, not the rows a filter leaves on the screen (D22).
"""

from __future__ import annotations

from typing import Any
from unittest import mock

from tl_web import present
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

P = "/web/p/P123"
BASE = f"{P}/correspondence"
NAMES = present.correspondence_text.REGISTER_COLUMNS
KEPT = ("Number", "Subject", "State")


def labels_for(w: Any, name: str) -> Any:
    return present.load_labels(
        present.as_client(w.reads(name)), "project:P123", ("correspondence.Correspondence",)
    )


def test_the_log_is_registered_and_the_page_answers(world: Any) -> None:
    log = LOGS.get("correspondence")
    assert log is not None and log.SLUG == "correspondence"
    assert world.web("bob").client.get(BASE).status_code == 200


def test_seven_regions_the_register_columns_and_cells_equal_register_cells(
    world: Any, htmlkit: Any
) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(BASE).text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    assert doc.headers("log-table")[:3] == list(KEPT)
    lines = world.reads("bob").list_correspondence("P123")
    labels = labels_for(world, "bob")
    full = [present.correspondence_text.register_cells(line, labels) for line in lines]
    assert len(doc.log_rows()) == len(full) >= 2
    assert doc.rows("log-table") == htmlkit.project_cells(doc.headers("log-table"), NAMES, full)
    shown = set(doc.headers("log-table"))
    for index, name in enumerate(NAMES):  # the columns rule
        distinct = {cells[index] for cells in full}
        if name not in KEPT:
            assert (name in shown) is (len(distinct) > 1), name


def test_the_panel_of_a_letter_is_plain_lines_of_item_page(world: Any, htmlkit: Any) -> None:
    number = world.numbers["open"]
    reader = world.reads("bob")
    item = reader.get_correspondence("P123", number)
    lines = present.plain_lines(
        present.correspondence_text.item_page(
            item, None, labels_for(world, "bob"), technical=False,
            client=present.as_client(reader), project="P123",
        )
    )  # fmt: skip
    panel = world.web("bob").client.get(f"{BASE}/panel/{number}")
    assert panel.status_code == 200
    assert htmlkit.parse(panel.text).pre().split("\n") == lines


def test_the_status_line_counts_all_loaded_rows_even_when_a_filter_narrows(
    world: Any, htmlkit: Any
) -> None:
    """D22: the filter narrows the rows on the screen, not the count the read loaded."""
    bob = world.web("bob").client
    shown = len(world.reads("bob").list_correspondence("P123"))
    want = present.correspondence_text.summary_line("register", shown)
    assert htmlkit.parse(bob.get(BASE).text).status() == want
    narrowed = htmlkit.parse(bob.get(BASE, params={"q": world.numbers["open"]}).text)
    assert len(narrowed.log_rows()) == 1 and narrowed.status() == want


def test_a_restricted_letter_is_the_404_page_and_in_no_answer_for_a_plain_user(world: Any) -> None:
    bob = world.web("bob").client
    start = len(world.answers)
    hidden = bob.get(f"{BASE}/panel/{world.numbers['restricted']}")
    unknown = bob.get(f"{BASE}/panel/P123-COR-9999")
    assert hidden.status_code == 404 and hidden.content == unknown.content
    for path in (
        BASE, f"{BASE}?q=restoken", f"{BASE}?sel={world.numbers['restricted']}",
        f"{BASE}?mode=technical", f"{BASE}/panel/{world.numbers['open']}?mode=technical",
    ):  # fmt: skip
        bob.get(path)
    for response in world.answers[start:]:
        assert b"RESTOKEN" not in response.content
        assert world.ids["restricted"].encode() not in response.content
    found = bob.get(BASE, params={"q": "restoken"})
    assert found.text.count("data-number=") == 0  # the filter finds nothing of it


def test_the_controller_reads_the_restricted_letter(world: Any, htmlkit: Any) -> None:
    ctl = world.web("ctl").client
    panel = ctl.get(f"{BASE}/panel/{world.numbers['restricted']}")
    assert panel.status_code == 200 and "RESTOKEN" in panel.text
    numbers = [r.get("data-number") for r in htmlkit.parse(ctl.get(BASE).text).log_rows()]
    assert world.numbers["restricted"] in numbers


def test_technical_mode_is_refused_for_a_plain_user_and_shows_ids_for_an_admin(
    world: Any, htmlkit: Any
) -> None:
    number = world.numbers["open"]
    plain = world.web("bob").client.get(f"{BASE}?mode=technical")
    assert plain.status_code == 200
    assert present.REFUSAL in htmlkit.parse(plain.text).status()
    assert world.ids["open"] not in htmlkit.parse(plain.text).visible_text()
    reader = world.reads("boss")
    item = reader.get_correspondence("P123", number)
    lines = present.plain_lines(
        present.correspondence_text.item_page(
            item, None, labels_for(world, "boss"), technical=True,
            client=present.as_client(reader), project="P123",
        )
    )  # fmt: skip
    assert world.ids["open"] in "\n".join(lines)
    panel = world.web("boss").client.get(f"{BASE}/panel/{number}?mode=technical")
    assert panel.status_code == 200
    assert htmlkit.parse(panel.text).pre().split("\n") == lines
    admin = htmlkit.parse(world.web("boss").client.get(f"{BASE}?mode=technical").text)
    assert present.REFUSAL not in admin.status()


def test_the_filter_narrows_the_rows(world: Any, htmlkit: Any) -> None:
    found = htmlkit.parse(world.web("bob").client.get(BASE, params={"q": "OPENTOKEN subject"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == [world.numbers["open"]]


def test_a_register_source_line_has_two_plain_lines_and_no_actions(
    world: Any, htmlkit: Any
) -> None:
    """A transmittal line (kind transmittal): the default selection, ``sel`` and its panel show the
    note, no action buttons, status 200."""
    real = WebReadClient.list_correspondence
    number, subject = "TRN-0001", "Transmittal to the contractor"
    lines = [f"{number}  {subject}", "Transmittal. Open it in the terminal for the full list."]

    def with_transmittal(self: WebReadClient, project: str, **kwargs: Any) -> list[Any]:
        rows = real(self, project, **kwargs)
        update = {"kind": "transmittal", "id": "TRN-REG-0001", "number": number, "subject": subject}
        return [rows[0].model_copy(update=update), *rows]

    bob = world.web("bob").client
    with mock.patch.object(WebReadClient, "list_correspondence", with_transmittal):
        answers = [
            bob.get(BASE),
            bob.get(f"{BASE}?sel={number}"),
            bob.get(f"{BASE}/panel/{number}"),
        ]
    for answer in answers:
        assert answer.status_code == 200
        doc = htmlkit.parse(answer.text)
        assert doc.buttons() == []
        assert doc.pre().split("\n") == lines


def test_a_real_transmittal_line_is_a_source_line_too(world: Any, htmlkit: Any) -> None:
    bob = world.web("bob").client
    number = world.numbers["transmittal"]
    panel = htmlkit.parse(bob.get(f"{BASE}/panel/{number}").text)
    assert panel.buttons() == []
    assert panel.pre().split("\n")[0].startswith(number)


def test_no_cookie_is_a_redirect_to_sign_in(world: Any) -> None:
    response = world.client().get(BASE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")
