"""Acceptance script for P2-WEB1 T04: the Thread and Files tabs of the record screen.

Reuses ``S4.World`` (loaded as a module, as S6 does; the S4 demo page is switched off). The reads
behind the two tabs are replaced by fakes for the whole run (``mock.patch.object`` on
``WebReadClient``). Prints one ``PASS <letter>: ...`` per check, exits 0 when all pass and 1 on
the first failure.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock
from urllib.parse import quote

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("accept_s4", ROOT / "dev/accept/P2-WEB1/S4.py")
assert spec is not None and spec.loader is not None
S4 = importlib.util.module_from_spec(spec)
sys.modules["accept_s4"] = S4
spec.loader.exec_module(S4)
S4.PAGE_SOURCE = (
    "from fastapi import APIRouter\n"
    "router = APIRouter(prefix='/web', include_in_schema=False)\n"  # S4's own demo page off
)

from tl_api.errors import body_for  # noqa: E402
from tl_web import present  # noqa: E402
from tl_web.pages import record as record_page  # noqa: E402
from tl_web.reads import WebReadClient  # noqa: E402

expect, passed, PROJECT, SCOPE = S4.expect, S4.passed, S4.PROJECT, S4.SCOPE
NOT_FOUND_ID = "01J00000000000000000000000"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"}
SEVEN = "?tab=thread&before=7"
#: What the fakes hand back, filled by ``main`` (the record ids come from the World).
STATE: dict[str, Any] = {}
CALLS: dict[str, list[Any]] = {"thread": [], "files": []}
PATCHES: list[Any] = []

FILES = [
    SimpleNamespace(
        file_id="FA01", scope=SCOPE, filename="a.pdf", content_type="application/pdf", size=2048
    ),
    SimpleNamespace(
        file_id="FB02", scope=SCOPE, filename="b.pdf", content_type="application/pdf", size=5000000
    ),
    SimpleNamespace(
        file_id="FN03", scope=SCOPE, filename="n.txt", content_type="text/plain", size=12
    ),
]
BODY = "First line\nsecond line with <b>x</b>\n  indented"


class Page(HTMLParser):
    """The parts of the record page this script reads: the header, the tab links, and what is in
    ``#rec-body``: its text, ``<pre>`` and ``<p>`` texts, table headers and rows, links, images."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.h1 = ""
        self.state = ""
        self.nav: list[tuple[str, str, bool]] = []  # (href, label, current)
        self.body = ""
        self.pres: list[str] = []
        self.ps: list[str] = []
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self.links: list[tuple[str, str]] = []  # (href, text) inside #rec-body
        self.imgs: list[dict[str, str | None]] = []
        self._stack: list[tuple[str, str]] = []
        self._sinks: dict[str, list[str]] = {}
        self._hrefs: dict[str, tuple[str, bool]] = {}
        self._row: list[str] = []
        self.feed(text)

    def _in(self, ident: str) -> bool:
        return any(i == ident for _, i in self._stack)

    def _done(self, key: str) -> str:
        return "".join(self._sinks.pop(key))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag in VOID:
            if tag == "img" and self._in("rec-body"):
                self.imgs.append(a)
            return
        self._stack.append((tag, a.get("id") or ""))
        if tag == "h1" and self._in("rec-header"):
            self._sinks["h1"] = []
        elif tag == "p" and self._in("rec-header"):
            self._sinks["state"] = []
        elif tag == "a" and self._in("rec-tabs"):
            self._sinks["nav"] = []
            self._hrefs["nav"] = (a.get("href") or "", "aria-current" in a)
        elif tag == "pre" and self._in("rec-body"):
            self._sinks["pre"] = []
        elif tag == "p" and self._in("rec-body"):
            self._sinks["p"] = []
        elif tag in ("th", "td") and self._in("rec-body"):
            self._sinks[tag] = []
        elif tag == "a" and self._in("rec-body"):
            self._sinks["a"] = []
            self._hrefs["a"] = (a.get("href") or "", False)

    def handle_endtag(self, tag: str) -> None:
        for pos in range(len(self._stack) - 1, -1, -1):
            if self._stack[pos][0] == tag:
                del self._stack[pos:]
                break
        else:
            return
        if tag == "h1" and "h1" in self._sinks:
            self.h1 = self._done("h1")
        elif tag == "p" and "state" in self._sinks:
            self.state = self._done("state")
        elif tag == "p" and "p" in self._sinks:
            self.ps.append(self._done("p"))
        elif tag == "pre" and "pre" in self._sinks:
            self.pres.append(self._done("pre"))
        elif tag == "a" and "nav" in self._sinks:
            href, current = self._hrefs.pop("nav")
            self.nav.append((href, self._done("nav"), current))
        elif tag == "a" and "a" in self._sinks:
            href, _ = self._hrefs.pop("a")
            self.links.append((href, self._done("a")))
        elif tag == "td" and "td" in self._sinks:
            self._row.append(self._done("td"))
        elif tag == "th" and "th" in self._sinks:
            self.headers.append(self._done("th"))
        elif tag == "tr" and self._row:
            self.rows.append(self._row)
            self._row = []

    def handle_data(self, data: str) -> None:
        for buffer in self._sinks.values():
            buffer.append(data)
        if self._in("rec-body"):
            self.body += data


def url(world: Any, key: str, query: str = "") -> str:
    return f"/web/p/{PROJECT}/records/{world.ids[key]}{query}"


def record_of(world: Any, name: str, key: str) -> dict[str, Any]:
    row = world.reads(name).get_record_by_id(world.ids[key])
    expect(row is not None, f"{name} cannot read {key}")
    assert row is not None
    return row


def labels_of(world: Any, name: str, record: dict[str, Any]) -> Any:
    return present.load_labels(
        present.as_client(world.reads(name)), SCOPE, ("core.Record", str(record["type"]))
    )


def message(author: str, posted_at: str, body: str, kind: str, **flags: bool) -> Any:
    fields = {"retracted": False, "edited": False, "dispatch": None, **flags}
    return SimpleNamespace(author=author, posted_at=posted_at, body=body, **fields), kind


def stand_ins(ids: dict[str, str]) -> tuple[Any, Any]:
    """The thread of the answered record (three messages, the second by an agent, the third
    retracted, the next page at 7) and the page of a type with threads off."""
    pairs = [
        message("user:alice", "2026-11-02T07:02:00Z", BODY, "message"),
        message("agent:planner", "2026-11-02T07:05:00Z", "Reply here", "reminder", edited=True),
        message("user:alice", "2026-11-02T07:09:00Z", "withdrawn", "message", retracted=True),
    ]
    answered = SimpleNamespace(
        enabled=True,
        dispatch_enabled=False,
        participants=["user:alice", "agent:planner"],
        messages=[m for m, _ in pairs],
        kinds=[k for _, k in pairs],
        next_before=7,
        record=SimpleNamespace(key="P123-RFI-0001", id=ids["answered"], record_type="rfi"),
    )
    closed = SimpleNamespace(
        enabled=False,
        dispatch_enabled=False,
        participants=[],
        messages=[],
        kinds=[],
        next_before=None,
        record=SimpleNamespace(key="P123-RFI-0002", id=ids["closed"], record_type="rfi"),
    )
    return answered, closed


def fakes(ids: dict[str, str]) -> tuple[Any, Any]:
    answered, closed = STATE["answered"], STATE["closed"]

    def thread_page(
        self: Any, record_id: str, *, limit: int = 50, before_seq: int | None = None
    ) -> Any:
        CALLS["thread"].append((record_id, before_seq))
        return closed if record_id == ids["closed"] else answered

    def list_record_files(self: Any, record_id: str) -> Any:
        CALLS["files"].append(record_id)
        return [] if record_id == ids["waiting"] else FILES

    return thread_page, list_record_files


# --- (a) the nav -----------------------------------------------------------------------------


def check_nav(world: Any) -> None:
    alice, _ = world.web("alice")
    response = alice.get(url(world, "answered"))
    expect(response.status_code == 200, f"page {response.status_code}")
    page = Page(response.text)
    names = [href.split("tab=")[1] for href, _, _ in page.nav]
    labels = [label for _, label, _ in page.nav]
    expect(labels[-2:] == ["Thread", "Files"], f"last two tabs {labels}")
    expect(names[-2:] == ["thread", "files"], f"last two names {names}")
    expect(names.index("history") < names.index("thread"), f"History not before Thread {names}")
    registered = [n for n in record_page.ORDER if n in record_page.TABS]
    expect(names == registered, f"nav {names} != registered {registered}")
    current = [href for href, _, is_current in page.nav if is_current]
    expect(current == ["?tab=details"], f"current on {current}")
    passed(f"a: nav ends Thread, Files after History ({', '.join(names)})")


# --- (b) the thread text ---------------------------------------------------------------------


def check_thread_text(world: Any) -> None:
    alice, _ = world.web("alice")
    labels = labels_of(world, "alice", record_of(world, "alice", "answered"))
    raw = alice.get(url(world, "answered", "?tab=thread")).text
    page = Page(raw)
    lines = present.thread_text.message_lines(STATE["answered"], labels, technical=False)
    expect(lines != [] and page.pres == ["\n".join(lines)], f"pre {page.pres!r} vs {lines!r}")
    head = present.thread_text.header_text(STATE["answered"], labels, technical=False)
    expect(page.ps[:1] == [head], f"head {page.ps[:1]!r} vs {head!r}")
    expect("&lt;b&gt;x&lt;/b&gt;" in raw and "<b>x</b>" not in raw, "the body is not escaped")
    expect(page.pres[0].count("<b>x</b>") == 1, "the body text is lost")
    current = [label for _, label, is_current in page.nav if is_current]
    expect(current == ["Thread"], f"current tab {current}")
    passed("b: <pre> == message_lines, head == header_text, the body markup is escaped")


# --- (c) the Older link and before= ----------------------------------------------------------


def check_older(world: Any) -> None:
    alice, _ = world.web("alice")
    answered = world.ids["answered"]
    page = Page(alice.get(url(world, "answered", "?tab=thread")).text)
    expect(page.links == [(SEVEN, "Older messages")], f"Older link {page.links}")
    expect(CALLS["thread"][-1] == (answered, None), f"first page call {CALLS['thread'][-1]}")
    alice.get(url(world, "answered", SEVEN))
    expect(CALLS["thread"][-1] == (answered, 7), f"before=7 call {CALLS['thread'][-1]}")
    for raw_before in ("x", "-3"):
        alice.get(url(world, "answered", f"?tab=thread&before={raw_before}"))
        last = CALLS["thread"][-1]
        expect(last == (answered, None), f"before={raw_before} {last}")
    passed("c: Older is ?tab=thread&before=7; before=7 -> 7; before=x and before=-3 -> None")


# --- (d) threads off -------------------------------------------------------------------------


def check_disabled(world: Any) -> None:
    alice, _ = world.web("alice")
    page = Page(alice.get(url(world, "closed", "?tab=thread")).text)
    expect("Threads are not switched on for this type." in page.body, f"body {page.body!r}")
    expect(page.pres == [], f"a <pre> on a disabled thread: {page.pres!r}")
    passed("d: enabled=False shows 'Threads are not switched on for this type.' and no <pre>")


# --- (e) the Files tab -----------------------------------------------------------------------


def check_files(world: Any) -> None:
    alice, _ = world.web("alice")
    response = alice.get(url(world, "answered", "?tab=files"))
    expect(response.status_code == 200, f"files {response.status_code}")
    page = Page(response.text)
    expect(page.headers == ["Name", "Type", "Size"], f"headers {page.headers}")
    want_rows = [
        [
            f"{f.filename} View Download",
            present.file_text.file_kind(f.content_type, f.filename),
            present.file_text.human_size(f.size),
        ]
        for f in FILES
    ]
    expect(page.rows == want_rows, f"rows {page.rows} != {want_rows}")
    expect(len(page.imgs) == 1, f"{len(page.imgs)} images")
    picture = f"/web/files/{FILES[0].file_id}/page1.png?scope={quote(SCOPE, safe='')}"
    expect(page.imgs[0].get("src") == picture, f"img src {page.imgs[0].get('src')!r}")
    want_links: list[tuple[str, str]] = []
    for f in FILES:
        want_links.append((f"/web/p/{PROJECT}/files/{f.file_id}/view", "View"))
        want_links.append((f"/web/files/{f.file_id}/content?scope=project%3AP123", "Download"))
    expect(page.links == want_links, f"links {page.links}")
    passed(
        "e: headers Name Type Size; rows == file_kind/human_size; one img of a.pdf; "
        "View and Download links"
    )


# --- (f) no files ----------------------------------------------------------------------------


def check_no_files(world: Any) -> None:
    alice, _ = world.web("alice")
    page = Page(alice.get(url(world, "waiting", "?tab=files")).text)
    expect("No files." in page.body, f"body {page.body!r}")
    expect(page.imgs == [] and page.rows == [], f"rows {page.rows} imgs {page.imgs}")
    passed("f: no files shows 'No files.' and no <img>")


# --- (g) technical mode and the Older link ---------------------------------------------------


def check_mode(world: Any) -> None:
    root, _ = world.web("root")
    alice, _ = world.web("alice")
    rrecord = record_of(world, "root", "answered")
    rlabels = labels_of(world, "root", rrecord)
    page = Page(root.get(url(world, "answered", "?tab=thread&mode=technical")).text)
    technical = present.thread_text.message_lines(STATE["answered"], rlabels, technical=True)
    plain = present.thread_text.message_lines(STATE["answered"], rlabels, technical=False)
    expect(technical != plain, "the technical and plain lines are the same")
    expect(page.pres == ["\n".join(technical)], f"root pre {page.pres!r}")
    expect(
        page.links == [("?tab=thread&before=7&mode=technical", "Older messages")],
        f"root Older {page.links}",
    )
    plain_page = Page(alice.get(url(world, "answered", "?tab=thread&mode=technical")).text)
    expect(plain_page.links == [(SEVEN, "Older messages")], f"alice Older {plain_page.links}")
    expect("mode=technical" not in alice.get(url(world, "answered", "?tab=thread")).text, "mode")
    passed("g: root's Older carries &mode=technical, alice's does not; root gets technical lines")


# --- (h) hidden records and the unavailable reads ---------------------------------------------


def check_hidden(world: Any) -> None:
    alice, _ = world.web("alice")
    for key in ("secret", "restricted"):
        for query in ("?tab=thread", "?tab=files"):
            reference = alice.get(f"/web/p/{PROJECT}/records/{NOT_FOUND_ID}{query}")
            expect(reference.status_code == 404, f"unknown {reference.status_code}")
            hidden = alice.get(url(world, key, query))
            expect(hidden.status_code == 404, f"{key}{query}: {hidden.status_code}")
            expect(hidden.content == reference.content, f"{key}{query}: not the 404 page")
    touched = {record_id for record_id, _ in CALLS["thread"]} | set(CALLS["files"])
    expect(
        not touched & {world.ids["secret"], world.ids["restricted"]},
        "a read was made for a hidden record",
    )
    passed("h: secret and restricted, thread and files: the 404 page; no read was made for them")


def check_unavailable(world: Any) -> None:
    alice, _ = world.web("alice")

    def raiser(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    with mock.patch.object(WebReadClient, "thread_page", raiser):
        thread = alice.get(url(world, "answered", "?tab=thread"))
    with mock.patch.object(WebReadClient, "list_record_files", raiser):
        files = alice.get(url(world, "answered", "?tab=files"))
    expect(thread.status_code == 200 and "Thread unavailable:" in Page(thread.text).body, "thread")
    expect(files.status_code == 200 and "Files unavailable:" in Page(files.text).body, "files")

    error = ValidationError.from_exception_data(
        "Thread", [{"type": "missing", "loc": ("before",), "input": {}}]
    )
    mapped = body_for(error)
    expect(mapped is not None, "body_for does not map the test error")
    assert mapped is not None

    def mapped_raiser(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise error

    with mock.patch.object(WebReadClient, "thread_page", mapped_raiser):
        shown = alice.get(url(world, "answered", "?tab=thread"))
    want = f"Thread unavailable: {mapped[1].message}"
    expect(shown.status_code == 200 and want in Page(shown.text).body, f"mapped: {want!r}")
    passed(
        "h: NotImplementedError and a mapped error show 'Thread unavailable:' or "
        "'Files unavailable:' at 200"
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        world = S4.World(Path(tmp))
        try:
            STATE["answered"], STATE["closed"] = stand_ins(world.ids)
            thread_fake, files_fake = fakes(world.ids)
            for target, fake in (("thread_page", thread_fake), ("list_record_files", files_fake)):
                patch = mock.patch.object(WebReadClient, target, fake)
                patch.start()
                PATCHES.append(patch)
            check_nav(world)
            check_thread_text(world)
            check_older(world)
            check_disabled(world)
            check_files(world)
            check_no_files(world)
            check_mode(world)
            check_hidden(world)
            check_unavailable(world)
        finally:
            for patch in reversed(PATCHES):
                patch.stop()
            world.backend.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
