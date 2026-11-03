"""Plain wording for a plain user, technical wording only for an admin who asks (D13).

* For a plain user ``tl_tui.display.find_technical`` finds nothing in any page, panel and tab of the
  walk (``WALK``, in ``walk.py``) for a record the user may read.
* ``?mode=technical`` from a plain user gives the plain output and the status text
  "Technical details are for admins".
* For the admin ``?mode=technical`` shows record ids; ``mode=technical`` is carried on the Older
  link, the trace controls and the tab links for that admin only, and never stored: a second request
  without the query is plain.
* The plain wording is the terminal's own text functions' (one row per log).
"""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest
from tl_web import present
from tl_web.reads import WebReadClient

P = "/web/p/P123"
REFUSAL = "Technical details are for admins"


def labels_of(w: Any, name: str) -> Any:
    """The labels of every type the pages read, so a domain key is recognised wherever it shows."""
    return present.load_labels(
        present.as_client(w.reads(name)),
        "project:P123",
        (
            "core.Record", "correspondence.TechnicalItem", "correspondence.Correspondence",
            "documents.Document", "correspondence.CommercialItem",
        ),
    )  # fmt: skip


def get_pages(walk: Any, targets: dict[str, Any], may: set[str]) -> list[tuple[str, str]]:
    """``(label, url)`` of every GET page, panel and tab of the walk for a readable record."""
    seen: list[tuple[str, str]] = []
    for (method, _), row in walk.WALK.items():
        if method != "GET":
            continue
        for target in targets.values():
            if target.is_file or not row.applies(target) or not target.readable_by(may):
                continue
            for probe in row.build(target):
                if probe.label.startswith(("action form",)):
                    continue  # a fragment of questions, not a page of record text
                seen.append((probe.label, probe.url))
    return seen


def test_the_walk_has_pages_panels_and_tabs_to_read(world: Any, walk: Any, k: Any) -> None:
    pages = get_pages(walk, walk.targets(world), set(k.MAY_READ["bob"]))
    labels = {label for label, _ in pages}
    assert {"rfis filtered", "correspondence panel", "record details", "record files"} <= labels
    assert len(pages) >= 60


def test_find_technical_finds_nothing_for_a_plain_user_on_any_page_panel_or_tab(
    world: Any, walk: Any, k: Any, htmlkit: Any
) -> None:
    bob = world.web("bob").client
    labels = labels_of(world, "bob")
    pages = get_pages(walk, walk.targets(world), set(k.MAY_READ["bob"]))
    found: dict[str, list[str]] = {}
    for label, url in pages:
        response = bob.get(url)
        assert response.status_code in (200, 404), (label, url, response.status_code)
        text = htmlkit.parse(response.text).visible_text()
        hits = present.find_technical(text, labels)
        if hits:
            found[f"{label} {url}"] = hits
    assert not found, found


@pytest.mark.parametrize(
    "path",
    [
        f"{P}/rfis", f"{P}/correspondence", f"{P}/documents",
        f"{P}/rfis/panel/P123-RFI-0001", f"{P}/correspondence/panel/P123-COR-0001",
        f"{P}/documents/panel/ISO-9002",
    ],
)  # fmt: skip
def test_technical_mode_from_a_plain_user_is_plain_output_and_the_notice(
    world: Any, htmlkit: Any, path: str
) -> None:
    bob = world.web("bob").client
    plain = htmlkit.parse(bob.get(path).text)
    asked = htmlkit.parse(bob.get(path, params={"mode": "technical"}).text)
    assert asked.status() == REFUSAL == present.REFUSAL
    assert asked.rows() == plain.rows()  # the same cells
    assert asked.pre() == plain.pre()  # the same panel
    assert "mode=technical" not in bob.get(path, params={"mode": "technical"}).text


def test_technical_mode_on_a_record_tab_is_plain_with_the_notice_for_a_plain_user(
    world: Any, htmlkit: Any
) -> None:
    bob = world.web("bob").client
    base = f"{P}/records/{world.ids['open_rfi']}"
    for tab in ("details", "history", "links", "trace", "thread", "files"):
        plain = htmlkit.parse(bob.get(base, params={"tab": tab}).text)
        asked = htmlkit.parse(bob.get(base, params={"tab": tab, "mode": "technical"}).text)
        assert asked.status() == REFUSAL, tab
        assert asked.rows("rec-body") == plain.rows("rec-body"), tab
        assert asked.pre("rec-body") == plain.pre("rec-body"), tab
        assert "mode=technical" not in bob.get(base, params={"tab": tab, "mode": "technical"}).text


def test_an_admin_in_technical_mode_sees_the_record_ids(world: Any, htmlkit: Any) -> None:
    boss = world.web("boss").client
    path = f"{P}/correspondence/panel/{world.numbers['open']}"
    plain = htmlkit.parse(boss.get(path).text).visible_text()
    technical = htmlkit.parse(boss.get(path, params={"mode": "technical"}).text).visible_text()
    assert world.ids["open"] in technical and world.ids["open"] not in plain


def test_an_admin_in_technical_mode_sees_the_version_on_the_record_page(
    world: Any, htmlkit: Any
) -> None:
    boss = world.web("boss").client
    record = world.reads("boss").get_record_by_id(world.ids["open_rfi"])
    path = f"{P}/records/{world.ids['open_rfi']}"
    plain = htmlkit.parse(boss.get(path).text).visible_text()
    technical = htmlkit.parse(boss.get(path, params={"mode": "technical"}).text).visible_text()
    assert f"v{record['version']}" in technical and f"v{record['version']}" not in plain
    assert technical != plain


def test_the_mode_rides_on_links_for_the_admin_only_and_is_never_stored(
    world: Any, htmlkit: Any
) -> None:
    boss, bob = world.web("boss").client, world.web("bob").client
    rec = f"{P}/records/{world.ids['open_rfi']}"
    with_mode = htmlkit.parse(boss.get(rec, params={"mode": "technical"}).text)
    assert all(h.endswith("&mode=technical") for h, _ in with_mode.links("rec-tabs"))
    trace = htmlkit.parse(boss.get(rec, params={"tab": "trace", "mode": "technical"}).text)
    assert all(h.endswith("&mode=technical") for h, _ in trace.links("trace-controls"))
    log = htmlkit.parse(boss.get(f"{P}/rfis", params={"mode": "technical"}).text)
    assert all("mode=technical" in r.get("hx-get") for r in log.log_rows())
    after = boss.get(rec)  # a second request without the query: plain, nothing stored
    assert "mode=technical" not in after.text
    assert "mode=technical" not in boss.get(f"{P}/rfis").text
    for path, params in ((rec, {"mode": "technical"}), (f"{P}/rfis", {"mode": "technical"}),
                         (rec, {"tab": "trace", "mode": "technical"})):  # fmt: skip
        assert "mode=technical" not in bob.get(path, params=params).text, path


def test_the_older_link_carries_the_mode_only_for_the_admin(world: Any, htmlkit: Any) -> None:
    class Thread:
        enabled = True
        dispatch_enabled = False
        participants = ["user:bob"]
        next_before = 7
        record = type("R", (), {"key": "K", "id": "I", "record_type": "rfi"})()
        messages = [
            type(
                "M",
                (),
                {
                    "author": "user:bob",
                    "posted_at": "2026-11-02T07:02:00Z",
                    "body": "hi",
                    "retracted": False,
                    "edited": False,
                    "dispatch": None,
                },
            )()  # fmt: skip
        ]
        kinds = ["message"]

    def page(self: Any, record_id: str, *, limit: int = 50, before_seq: int | None = None) -> Any:
        return Thread()

    rec = f"{P}/records/{world.ids['open_rfi']}"
    with mock.patch.object(WebReadClient, "thread_page", page):
        boss = htmlkit.parse(
            world.web("boss").client.get(rec, params={"tab": "thread", "mode": "technical"}).text
        )
        bob = htmlkit.parse(
            world.web("bob").client.get(rec, params={"tab": "thread", "mode": "technical"}).text
        )
        again = htmlkit.parse(world.web("boss").client.get(rec, params={"tab": "thread"}).text)
    assert boss.links("rec-body") == [("?tab=thread&before=7&mode=technical", "Older messages")]
    assert bob.links("rec-body") == [("?tab=thread&before=7", "Older messages")]
    assert again.links("rec-body") == [("?tab=thread&before=7", "Older messages")]


def test_the_plain_wording_is_the_terminals_text_functions_one_row_per_log(
    world: Any, htmlkit: Any
) -> None:
    bob = world.web("bob").client
    reads = world.reads("bob")
    labels = labels_of(world, "bob")
    rfi = reads.list_rfis("P123").lines[0]
    cells = present.rfi_text.rfi_cells(rfi, labels, technical=False)
    page = htmlkit.parse(bob.get(f"{P}/rfis").text)
    names = present.rfi_text.RFI_COLUMNS
    shown = [names.index(h) for h in page.headers("log-table")]
    row = next(r for r in page.log_rows() if r.get("data-number") == rfi.number)
    assert page.cells(row) == [cells[i] for i in shown]

    line = reads.list_correspondence("P123")[0]
    cells = present.correspondence_text.register_cells(line, labels)
    page = htmlkit.parse(bob.get(f"{P}/correspondence").text)
    names = present.correspondence_text.REGISTER_COLUMNS
    shown = [names.index(h) for h in page.headers("log-table")]
    row = next(r for r in page.log_rows() if r.get("data-number") == line.number)
    assert page.cells(row) == [cells[i] for i in shown]

    doc = reads.list_documents("P123")[0]
    cells = present.document_text.row_cells(doc, labels, technical=False)
    page = htmlkit.parse(bob.get(f"{P}/documents").text)
    names = present.document_text.COLUMNS
    shown = [names.index(h) for h in page.headers("log-table")]
    row = next(r for r in page.log_rows() if r.get("data-number") == doc.number)
    assert page.cells(row) == [cells[i] for i in shown]
