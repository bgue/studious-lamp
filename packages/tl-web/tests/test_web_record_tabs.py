"""The Links, Trace, Thread and Files tabs of the record screen (P2-WEB1-T03, T04, D23, D24).

The ledger holds no links, threads or stored PDFs for these records, so the four reads
(``links_of``, ``trace``, ``thread_page``, ``list_record_files``) are replaced by fakes that record
their calls (``mock.patch.object(WebReadClient, ...)``; a fake takes ``self``). Expected text comes
from the pure modules (``links_text``, ``trace_text``, ``thread_text``, ``file_text``) on the fakes'
values. D24 pins: Trace depth is clamped 1 to 6 with ``dir`` both, out or in; Thread is one page per
``before`` with an Older link; Files shows page 1 of the first PDF only, with View and Download
links.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest import mock
from urllib.parse import quote

import pytest
from pydantic import ValidationError
from tl_api.errors import body_for
from tl_web import present
from tl_web.pages import record as record_page
from tl_web.reads import WebReadClient

P = "/web/p/P123"
SCOPE = "project:P123"
SEVEN = "?tab=thread&before=7"
#: D23: the tabs in this order, each its own module.
ORDER = ["details", "properties", "links", "history", "trace", "thread", "files"]


def url(w: Any, key: str, query: str = "") -> str:
    return f"{P}/records/{w.ids[key]}{query}"


def view(**fields: Any) -> Any:
    """A stand-in for ``tl_core.services.link_queries.LinkView`` (the attributes the text reads)."""
    base: dict[str, Any] = {
        "link_id": "L0", "direction": "out", "relation": "raised_against",
        "label": "raised against",
        "other_id": "other", "other_key": "NCR-1", "other_title": "Bevel damage",
        "other_type": "core.Record", "other_status": None, "other_voided": False,
        "status": "active", "pin": None, "note": None, "source": "manual", "confidence": None,
        "reason": None, "declined": False, "verified_by": None, "verified_at": None,
        "created_at": "2026-01-01T00:00:00Z", "version": 1,
    }  # fmt: skip
    base.update(fields)
    return SimpleNamespace(**base)


LINKS: list[Any] = [
    view(link_id="L1", other_title="<b>x</b> Bevel", status="active"),
    view(
        link_id="L2",
        other_key=None,
        other_title="Crack",
        pin="rev B",
        note="checked on site",
        verified_by="alice",
    ),  # fmt: skip
    view(
        link_id="L3",
        relation="supports",
        label="supports",
        other_key="RFI-7",
        other_title="Suggested one",
        status="suggested",
        confidence=0.82,
    ),  # fmt: skip
]


def node(**fields: Any) -> Any:
    """A stand-in for ``tl_core.services.link_trace.TraceNode``."""
    base: dict[str, Any] = {
        "record_id": "r", "key": None, "title": "", "type": "core.Record", "status": None,
        "voided": False, "depth": 0, "link_id": None, "link_status": None, "relation": None,
        "direction": None, "label": None, "children": [], "more": 0,
    }  # fmt: skip
    base.update(fields)
    return SimpleNamespace(**base)


def make_tree(record_id: str, key: str) -> Any:
    return node(
        record_id=record_id, key=key, title="Answered RFI",
        children=[
            node(record_id="n1", key="NCR-1", title="Bevel damage", depth=1,
                 label="raised against", link_status="stale", link_id="L1"),
            node(record_id="n2", key="RFI-2", title="Crack", depth=1, label="has raised",
                 direction="in", more=2),
        ],
    )  # fmt: skip


FILES = [
    SimpleNamespace(file_id="FA01", scope=SCOPE, filename="a.pdf",
                    content_type="application/pdf", size=2048),
    SimpleNamespace(file_id="FB02", scope=SCOPE, filename="b.pdf",
                    content_type="application/pdf", size=5000000),
    SimpleNamespace(file_id="FN03", scope=SCOPE, filename="n.txt",
                    content_type="text/plain", size=12),
]  # fmt: skip
BODY = "First line\nsecond line with <b>x</b>\n  indented"


class Fakes:
    """What the fake reads hand back, and the calls they saw."""

    def __init__(self, w: Any) -> None:
        self.w = w
        self.links: list[Any] = list(LINKS)
        self.tree: Any = make_tree(w.ids["open_rfi"], w.numbers["open_rfi"])
        self.link_calls: list[str] = []
        self.trace_calls: list[tuple[str, int, str]] = []
        self.thread_calls: list[tuple[str, int | None]] = []
        self.file_calls: list[str] = []
        pairs = [
            ("user:alice", "2026-11-02T07:02:00Z", BODY, "message", {}),
            ("agent:planner", "2026-11-02T07:05:00Z", "Reply here", "reminder", {"edited": True}),
            ("user:alice", "2026-11-02T07:09:00Z", "withdrawn", "message", {"retracted": True}),
        ]
        messages = [
            SimpleNamespace(
                author=a, posted_at=t, body=b,
                **{"retracted": False, "edited": False, "dispatch": None, **flags},
            )
            for a, t, b, _, flags in pairs
        ]  # fmt: skip
        self.answered: Any = SimpleNamespace(
            enabled=True, dispatch_enabled=False, participants=["user:alice", "agent:planner"],
            messages=messages, kinds=[p[3] for p in pairs], next_before=7,
            record=SimpleNamespace(
                key=w.numbers["open_rfi"], id=w.ids["open_rfi"], record_type="rfi"
            ),
        )  # fmt: skip
        self.closed: Any = SimpleNamespace(
            enabled=False, dispatch_enabled=False, participants=[], messages=[], kinds=[],
            next_before=None,
            record=SimpleNamespace(
                key=w.numbers["closed"], id=w.ids["closed"], record_type="rfi"
            ),
        )  # fmt: skip


@pytest.fixture
def fakes(world: Any) -> Iterator[Fakes]:
    f = Fakes(world)

    def links_of(self: Any, record_id: str, *, include_retracted: bool = False) -> Any:
        f.link_calls.append(record_id)
        return list(f.links)

    def trace(self: Any, record_id: str, *, depth: int = 2, direction: str = "both") -> Any:
        f.trace_calls.append((record_id, depth, direction))
        return f.tree

    def thread_page(
        self: Any, record_id: str, *, limit: int = 50, before_seq: int | None = None
    ) -> Any:
        f.thread_calls.append((record_id, before_seq))
        return f.closed if record_id == world.ids["closed"] else f.answered

    def list_record_files(self: Any, record_id: str) -> Any:
        f.file_calls.append(record_id)
        return [] if record_id == world.ids["waiting"] else FILES

    with (
        mock.patch.object(WebReadClient, "links_of", links_of),
        mock.patch.object(WebReadClient, "trace", trace),
        mock.patch.object(WebReadClient, "thread_page", thread_page),
        mock.patch.object(WebReadClient, "list_record_files", list_record_files),
    ):
        yield f


class Page:
    def __init__(self, htmlkit: Any, text: str) -> None:
        self.doc = htmlkit.parse(text)
        body = self.doc.by_id("rec-body")
        assert body is not None
        self.body = body
        nav = self.doc.by_id("rec-tabs")
        self.nav = (
            [(a.get("href"), a.text(), "aria-current" in a.attrs) for a in nav.find_all("a")]
            if nav
            else []
        )
        self.ps = [p.text() for p in body.find_all("p")]
        self.pres = [p.text() for p in body.find_all("pre")]
        self.headers = [th.text() for th in body.find_all("th")]
        self.rows = [
            [td.text() for td in tr.find_all("td")] for tr in body.find_all("tr") if tr.find("td")
        ]
        self.groups = [
            "tl-group" in tr.get("class").split() for tr in body.find_all("tr") if tr.find("td")
        ]
        self.links = [(a.get("href"), a.text()) for a in body.find_all("a")]
        self.imgs = body.find_all("img")
        controls = self.doc.by_id("trace-controls")
        self.controls = (
            [
                (a.get("href"), a.text(), a.get("aria-current") == "true")
                for a in controls.find_all("a")
            ]
            if controls
            else []
        )

    @property
    def names(self) -> list[str]:
        return [href.split("tab=")[1].split("&")[0] for href, _, _ in self.nav]


def labels_of(w: Any, name: str, key: str) -> Any:
    record = w.reads(name).get_record_by_id(w.ids[key])
    return present.load_labels(
        present.as_client(w.reads(name)), SCOPE, ("core.Record", str(record["type"]))
    )


# --- the nav ------------------------------------------------------------------------------------


def test_the_nav_is_details_properties_links_history_trace_thread_files(
    world: Any, htmlkit: Any, fakes: Fakes
) -> None:
    page = Page(htmlkit, world.web("bob").client.get(url(world, "open_rfi")).text)
    assert page.names == ORDER
    assert [label for _, label, _ in page.nav] == [
        "Details", "Properties", "Links", "History", "Trace", "Thread", "Files",
    ]  # fmt: skip
    assert [href for href, _, cur in page.nav if cur] == ["?tab=details"]
    registered = [n for n in record_page.ORDER if n in record_page.TABS]
    assert page.names == registered


# --- Links (T03) --------------------------------------------------------------------------------


def test_the_links_page_is_build_rows_with_group_rows_marked_and_titles_escaped(
    world: Any, htmlkit: Any, fakes: Fakes
) -> None:
    response = world.web("bob").client.get(url(world, "open_rfi", "?tab=links"))
    assert response.status_code == 200
    page = Page(htmlkit, response.text)
    want = present.links_text.build_rows(LINKS)
    assert page.headers == list(present.links_text.COLUMNS)
    assert page.rows == [list(r.cells) for r in want]
    assert page.groups == [r.link_id is None for r in want]
    assert any(page.groups) and not all(page.groups)
    assert "<b>x</b>" not in response.text and "&lt;b&gt;x&lt;/b&gt;" in response.text


def test_no_links_is_one_line_and_no_table(world: Any, htmlkit: Any, fakes: Fakes) -> None:
    fakes.links = []
    response = world.web("bob").client.get(url(world, "open_rfi", "?tab=links"))
    assert response.status_code == 200
    body = response.text.split('id="rec-body"', 1)[1].split("</div>", 1)[0]
    assert "<p>No links yet.</p>" in body and "<table" not in body


# --- Trace (T03, D24) ---------------------------------------------------------------------------


def test_the_trace_is_the_tree_lines_with_the_head_and_one_default_call(
    world: Any, htmlkit: Any, fakes: Fakes
) -> None:
    page = Page(htmlkit, world.web("bob").client.get(url(world, "open_rfi", "?tab=trace")).text)
    tree = make_tree(world.ids["open_rfi"], world.numbers["open_rfi"])
    assert page.pres == ["\n".join(present.trace_text.tree_lines(tree))]
    assert page.ps == [present.trace_text.head_text(2, "both")]
    assert fakes.trace_calls == [(world.ids["open_rfi"], 2, "both")]


@pytest.mark.parametrize(
    ("query", "depth", "direction"),
    [
        ("?tab=trace&depth=9&dir=sideways", 6, "both"),  # clamped to 6, a bad dir is both
        ("?tab=trace&depth=x", 2, "both"),
        ("?tab=trace&depth=0&dir=in", 1, "in"),  # clamped to 1
        ("?tab=trace&depth=-4&dir=out", 1, "out"),
        ("?tab=trace&depth=3&dir=out", 3, "out"),
    ],
)
def test_the_trace_depth_is_clamped_one_to_six_and_dir_is_both_out_or_in(
    world: Any, fakes: Fakes, query: str, depth: int, direction: str
) -> None:
    response = world.web("bob").client.get(url(world, "open_rfi", query))
    assert response.status_code == 200
    assert fakes.trace_calls == [(world.ids["open_rfi"], depth, direction)]


def test_the_trace_controls_and_the_mode_only_for_an_admin(
    world: Any, htmlkit: Any, fakes: Fakes
) -> None:
    plain = Page(htmlkit, world.web("bob").client.get(url(world, "open_rfi", "?tab=trace")).text)
    assert [text for _, text, _ in plain.controls] == [
        "both directions", "outbound", "inbound", "Less", "More",
    ]  # fmt: skip
    assert all(
        h.startswith("?tab=trace&depth=") and "mode=technical" not in h
        for h, _, _ in plain.controls
    )
    assert [text for _, text, cur in plain.controls if cur] == ["both directions"]
    hrefs = [h for h, _, _ in plain.controls]
    assert hrefs[3] == "?tab=trace&depth=1&dir=both" and hrefs[4] == "?tab=trace&depth=3&dir=both"
    top = Page(
        htmlkit, world.web("bob").client.get(url(world, "open_rfi", "?tab=trace&depth=9")).text
    )
    texts = [t for _, t, _ in top.controls]
    assert "More" not in texts and "Less" in texts  # at the top of the clamp
    low = Page(
        htmlkit, world.web("bob").client.get(url(world, "open_rfi", "?tab=trace&depth=1")).text
    )
    assert "Less" not in [t for _, t, _ in low.controls]
    boss = world.web("boss").client
    rooted = Page(htmlkit, boss.get(url(world, "open_rfi", "?tab=trace&mode=technical")).text)
    assert len(rooted.controls) == 5
    assert all(h.endswith("&mode=technical") for h, _, _ in rooted.controls)
    assert "mode=technical" not in boss.get(url(world, "open_rfi", "?tab=trace")).text


def test_a_trace_read_that_is_not_installed_shows_unavailable_at_200(
    world: Any, htmlkit: Any, fakes: Fakes
) -> None:
    def unavailable(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("the trace read is not installed")

    with mock.patch.object(WebReadClient, "trace", unavailable):
        response = world.web("bob").client.get(url(world, "open_rfi", "?tab=trace"))
    assert response.status_code == 200
    assert Page(htmlkit, response.text).pres[0].startswith("Trace unavailable:")


# --- Thread (T04, D24) --------------------------------------------------------------------------


def test_the_thread_is_message_lines_with_the_head_and_the_body_escaped(
    world: Any, htmlkit: Any, fakes: Fakes
) -> None:
    labels = labels_of(world, "bob", "open_rfi")
    raw = world.web("bob").client.get(url(world, "open_rfi", "?tab=thread")).text
    page = Page(htmlkit, raw)
    lines = present.thread_text.message_lines(fakes.answered, labels, technical=False)
    assert lines and page.pres == ["\n".join(lines)]
    assert page.ps[:1] == [present.thread_text.header_text(fakes.answered, labels, technical=False)]
    assert "&lt;b&gt;x&lt;/b&gt;" in raw and "<b>x</b>" not in raw
    assert page.pres[0].count("<b>x</b>") == 1  # the text is not lost
    assert [label for _, label, cur in page.nav if cur] == ["Thread"]


def test_the_thread_is_one_page_per_before_with_an_older_link(
    world: Any, htmlkit: Any, fakes: Fakes
) -> None:
    bob = world.web("bob").client
    page = Page(htmlkit, bob.get(url(world, "open_rfi", "?tab=thread")).text)
    assert page.links == [(SEVEN, "Older messages")]
    assert fakes.thread_calls[-1] == (world.ids["open_rfi"], None)
    bob.get(url(world, "open_rfi", SEVEN))
    assert fakes.thread_calls[-1] == (world.ids["open_rfi"], 7)
    for raw in ("x", "-3"):
        bob.get(url(world, "open_rfi", f"?tab=thread&before={raw}"))
        assert fakes.thread_calls[-1] == (world.ids["open_rfi"], None), raw


def test_a_type_with_threads_off_says_so_and_has_no_text(
    world: Any, htmlkit: Any, fakes: Fakes
) -> None:
    page = Page(htmlkit, world.web("bob").client.get(url(world, "closed", "?tab=thread")).text)
    assert "Threads are not switched on for this type." in page.body.text()
    assert page.pres == []


def test_the_older_link_carries_the_mode_for_an_admin_only(
    world: Any, htmlkit: Any, fakes: Fakes
) -> None:
    boss, bob = world.web("boss").client, world.web("bob").client
    labels = labels_of(world, "boss", "open_rfi")
    page = Page(htmlkit, boss.get(url(world, "open_rfi", "?tab=thread&mode=technical")).text)
    technical = present.thread_text.message_lines(fakes.answered, labels, technical=True)
    plain = present.thread_text.message_lines(fakes.answered, labels, technical=False)
    assert technical != plain
    assert page.pres == ["\n".join(technical)]
    assert page.links == [("?tab=thread&before=7&mode=technical", "Older messages")]
    other = Page(htmlkit, bob.get(url(world, "open_rfi", "?tab=thread&mode=technical")).text)
    assert other.links == [(SEVEN, "Older messages")]
    assert "mode=technical" not in bob.get(url(world, "open_rfi", "?tab=thread")).text


@pytest.mark.parametrize("error", ["not_installed", "mapped"])
def test_an_unavailable_thread_or_files_read_shows_the_text_at_200(
    world: Any, htmlkit: Any, fakes: Fakes, error: str
) -> None:
    bob = world.web("bob").client
    mapped = ValidationError.from_exception_data(
        "Thread", [{"type": "missing", "loc": ("before",), "input": {}}]
    )
    raised: BaseException = NotImplementedError() if error == "not_installed" else mapped

    def raiser(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise raised

    with mock.patch.object(WebReadClient, "thread_page", raiser):
        thread = bob.get(url(world, "open_rfi", "?tab=thread"))
    with mock.patch.object(WebReadClient, "list_record_files", raiser):
        files = bob.get(url(world, "open_rfi", "?tab=files"))
    assert thread.status_code == 200 and files.status_code == 200
    if error == "not_installed":
        assert "Thread unavailable:" in Page(htmlkit, thread.text).body.text()
        assert "Files unavailable:" in Page(htmlkit, files.text).body.text()
    else:
        body = body_for(mapped)
        assert body is not None
        assert f"Thread unavailable: {body[1].message}" in Page(htmlkit, thread.text).body.text()


# --- Files (T04, D24) ---------------------------------------------------------------------------


def test_the_files_tab_is_a_table_with_page_1_of_the_first_pdf_and_view_download_links(
    world: Any, htmlkit: Any, fakes: Fakes
) -> None:
    response = world.web("bob").client.get(url(world, "open_rfi", "?tab=files"))
    assert response.status_code == 200
    page = Page(htmlkit, response.text)
    assert page.headers == ["Name", "Type", "Size"]
    assert page.rows == [
        [
            f"{f.filename} View Download",
            present.file_text.file_kind(f.content_type, f.filename),
            present.file_text.human_size(f.size),
        ]
        for f in FILES
    ]
    assert len(page.imgs) == 1  # page 1 of the first PDF only, not of b.pdf
    assert page.imgs[0].get("src") == f"/web/files/FA01/page1.png?scope={quote(SCOPE, safe='')}"
    want: list[tuple[str, str]] = []
    for f in FILES:
        want.append((f"/web/p/P123/files/{f.file_id}/view", "View"))
        want.append((f"/web/files/{f.file_id}/content?scope=project%3AP123", "Download"))
    assert page.links == want


def test_no_files_is_one_line_and_no_picture(world: Any, htmlkit: Any, fakes: Fakes) -> None:
    page = Page(htmlkit, world.web("bob").client.get(url(world, "waiting", "?tab=files")).text)
    assert "No files." in page.body.text()
    assert page.imgs == [] and page.rows == []


# --- hidden records -----------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["secret_rfi", "restricted_rfi"])
@pytest.mark.parametrize("tab", ["links", "trace", "thread", "files"])
def test_a_hidden_record_is_the_404_page_and_no_read_is_made_for_it(
    world: Any, k: Any, fakes: Fakes, key: str, tab: str
) -> None:
    bob = world.web("bob").client
    reference = bob.get(f"{P}/records/{k.NEVER}?tab={tab}")
    hidden = bob.get(url(world, key, f"?tab={tab}"))
    assert reference.status_code == 404 and hidden.status_code == 404
    assert hidden.content == reference.content
    touched = {c for c in fakes.link_calls} | {c[0] for c in fakes.trace_calls}
    touched |= {c[0] for c in fakes.thread_calls} | set(fakes.file_calls)
    assert world.ids[key] not in touched  # the visibility check came before any tab read
