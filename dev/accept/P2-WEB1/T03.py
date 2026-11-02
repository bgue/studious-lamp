"""Acceptance script for P2-WEB1 T03: the Links and Trace tabs of the record page.

Reuses ``S4.World`` (loaded as a module, as S6 does; the S4 demo page is switched off). The ledger
holds no links, so ``WebReadClient.links_of`` and ``WebReadClient.trace`` are replaced for the run
by fakes that record their calls. Prints one ``PASS <letter>: ...`` per check, exits 0 when all
pass and 1 on the first failure. Expected text comes from the pure modules (``links_text``,
``trace_text``) on the fakes' values.
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

from tl_web import present  # noqa: E402
from tl_web.reads import WebReadClient  # noqa: E402

expect, passed, PROJECT = S4.expect, S4.passed, S4.PROJECT
UNKNOWN = "01J00000000000000000000000"
VOID = {"meta", "link", "input", "br", "img", "hr"}
STATE: dict[str, Any] = {
    "links": [],
    "tree": None,
    "trace_error": None,
    "link_calls": [],
    "trace_calls": [],
}


def view(**fields: Any) -> SimpleNamespace:
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


LINKS = [
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


def node(**fields: Any) -> SimpleNamespace:
    """A stand-in for ``tl_core.services.link_trace.TraceNode``."""
    base: dict[str, Any] = {
        "record_id": "r", "key": None, "title": "", "type": "core.Record", "status": None,
        "voided": False, "depth": 0, "link_id": None, "link_status": None, "relation": None,
        "direction": None, "label": None, "children": [], "more": 0,
    }  # fmt: skip
    base.update(fields)
    return SimpleNamespace(**base)


def make_tree(answered: str) -> SimpleNamespace:
    return node(
        record_id=answered,
        key="P123-RFI-0001",
        title="Answered RFI",
        children=[
            node(record_id="n1", key="NCR-1", title="Bevel damage", depth=1,
                 label="raised against", link_status="stale", link_id="L1"),  # fmt: skip
            node(record_id="n2", key="RFI-2", title="Crack", depth=1, label="has raised",
                 direction="in", more=2),  # fmt: skip
        ],
    )  # fmt: skip


def fake_links_of(self: WebReadClient, record_id: str, *, include_retracted: bool = False) -> Any:
    STATE["link_calls"].append(record_id)
    return list(STATE["links"])


def fake_trace(
    self: WebReadClient, record_id: str, *, depth: int = 2, direction: str = "both"
) -> Any:
    STATE["trace_calls"].append((record_id, depth, direction))
    if STATE["trace_error"] is not None:
        raise STATE["trace_error"]
    return STATE["tree"]


class Page(HTMLParser):
    """What the record page shows: the header, the tab links, the body and the trace controls."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.h1 = ""
        self.state = ""
        self.nav: list[dict[str, Any]] = []
        self.controls: list[dict[str, Any]] = []
        self.body_p: list[str] = []
        self.pre = ""
        self.headers: list[str] = []
        self.rows: list[tuple[bool, list[str]]] = []
        self._stack: list[tuple[str, str]] = []  # (tag, id) of each open element
        self._sink: list[str] | None = None  # the text of the element being read
        self._kind = ""  # what that element is: h1, state, nav, control, body_p, pre, th, td
        self._attrs: dict[str, str] = {}
        self._row: tuple[bool, list[str]] | None = None
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID:
            return
        a = {k: v or "" for k, v in attrs}
        self._stack.append((tag, a.get("id", "")))
        if self._sink is not None:
            return
        within = {ident for _, ident in self._stack}
        kind = ""
        if tag == "h1" and "rec-header" in within:
            kind = "h1"
        elif tag == "p" and "rec-header" in within:
            kind = "state"
        elif tag == "a" and "rec-tabs" in within:
            kind = "nav"
        elif tag == "a" and "trace-controls" in within:
            kind = "control"
        elif tag == "p" and "rec-body" in within:
            kind = "body_p"
        elif tag == "pre" and "rec-body" in within:
            kind = "pre"
        elif tag == "th" and "rec-body" in within:
            kind = "th"
        elif tag == "td" and "rec-body" in within:
            kind = "td"
        elif tag == "tr" and "rec-body" in within:
            self._row = ("tl-group" in a.get("class", "").split(), [])
        if kind:
            self._sink, self._kind, self._attrs = [], kind, a

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1][0] == tag:
            self._stack.pop()
        if self._sink is not None and self._kind and tag in self._tags_of(self._kind):
            self._finish()
        if tag == "tr" and self._row is not None:
            if self._row[1]:
                self.rows.append(self._row)
            self._row = None

    @staticmethod
    def _tags_of(kind: str) -> tuple[str, ...]:
        return {
            "h1": ("h1",), "state": ("p",), "nav": ("a",), "control": ("a",),
            "body_p": ("p",), "pre": ("pre",), "th": ("th",), "td": ("td",),
        }[kind]  # fmt: skip

    def _finish(self) -> None:
        text = "".join(self._sink or [])
        kind, attrs = self._kind, self._attrs
        self._sink, self._kind = None, ""
        if kind == "h1":
            self.h1 = text
        elif kind == "state":
            self.state = text
        elif kind == "nav":
            self.nav.append(
                {
                    "href": attrs.get("href", ""),
                    "current": attrs.get("aria-current", ""),
                    "text": text,
                }
            )
        elif kind == "control":
            self.controls.append(
                {
                    "href": attrs.get("href", ""),
                    "current": attrs.get("aria-current", ""),
                    "text": text,
                }
            )
        elif kind == "body_p":
            self.body_p.append(text)
        elif kind == "pre":
            self.pre = text
        elif kind == "th":
            self.headers.append(text)
        elif kind == "td" and self._row is not None:
            self._row[1].append(text)

    def handle_data(self, data: str) -> None:
        if self._sink is not None:
            self._sink.append(data)


def url(world: Any, key: str, query: str = "") -> str:
    return f"/web/p/{PROJECT}/records/{world.ids[key]}{query}"


# --- (a) the nav -----------------------------------------------------------------------------


def check_nav(world: Any) -> None:
    alice, _ = world.web("alice")
    page = Page(alice.get(url(world, "answered")).text)
    labels = [str(link["text"]) for link in page.nav]
    expect(labels[:5] == ["Details", "Properties", "Links", "History", "Trace"], f"nav {labels}")
    expect(all(label in ("Thread", "Files") for label in labels[5:]), f"nav tail {labels[5:]}")
    hrefs = [str(link["href"]) for link in page.nav[:5]]
    expect(
        hrefs == ["?tab=details", "?tab=properties", "?tab=links", "?tab=history", "?tab=trace"],
        f"hrefs {hrefs}",
    )
    current = [link["href"] for link in page.nav if link["current"] == "page"]
    expect(current == ["?tab=details"], f"aria-current on {current}")
    passed("a: nav lists Links after Properties and Trace after History (Thread, Files may follow)")


# --- (b) the Links page ----------------------------------------------------------------------


def check_links(world: Any) -> None:
    alice, _ = world.web("alice")
    STATE["links"] = list(LINKS)
    response = alice.get(url(world, "answered", "?tab=links"))
    expect(response.status_code == 200, f"links page {response.status_code}")
    page = Page(response.text)
    want = present.links_text.build_rows(LINKS)
    expect(page.headers == list(present.links_text.COLUMNS), f"headers {page.headers}")
    expect(
        page.rows == [(r.link_id is None, list(r.cells)) for r in want],
        f"rows\n{page.rows}\n{want}",
    )
    expect(any(group for group, _ in page.rows), "no group row is marked")
    expect(not all(group for group, _ in page.rows), "every row is marked as a group")
    expect("<b>x</b>" not in response.text, "the title markup is raw in the page")
    expect("&lt;b&gt;x&lt;/b&gt;" in response.text, "the title markup is not escaped")
    passed(f"b: headers == COLUMNS; {len(want)} rows == build_rows; group rows marked; escaped")


# --- (c) no links ----------------------------------------------------------------------------


def check_empty(world: Any) -> None:
    alice, _ = world.web("alice")
    STATE["links"] = []
    response = alice.get(url(world, "answered", "?tab=links"))
    expect(response.status_code == 200, f"empty links {response.status_code}")
    body = response.text.split('id="rec-body"', 1)[1].split("</div>", 1)[0]
    expect("<p>No links yet.</p>" in body, "no 'No links yet.' line")
    expect("<table" not in body, "a table with no links")
    expect(Page(response.text).rows == [], "rows with no links")
    STATE["links"] = list(LINKS)
    passed("c: no links: 'No links yet.' in a <p>, no table")


# --- (d) the Trace page ----------------------------------------------------------------------


def check_trace(world: Any) -> None:
    alice, _ = world.web("alice")
    answered = str(world.ids["answered"])
    STATE["tree"] = make_tree(answered)
    STATE["trace_calls"].clear()
    response = alice.get(url(world, "answered", "?tab=trace"))
    expect(response.status_code == 200, f"trace page {response.status_code}")
    page = Page(response.text)
    want = "\n".join(present.trace_text.tree_lines(make_tree(answered)))
    expect(page.pre == want, f"pre\n{page.pre!r}\n{want!r}")
    expect(page.body_p == [present.trace_text.head_text(2, "both")], f"head {page.body_p}")
    expect(STATE["trace_calls"] == [(answered, 2, "both")], f"calls {STATE['trace_calls']}")
    passed("d: <pre> == tree_lines of the fake tree; head == head_text(2, both); one default call")


# --- (e) the query values --------------------------------------------------------------------


def check_query(world: Any) -> None:
    alice, _ = world.web("alice")
    answered = str(world.ids["answered"])
    cases = {
        "?tab=trace&depth=9&dir=sideways": (6, "both"),
        "?tab=trace&depth=x": (2, "both"),
        "?tab=trace&depth=0&dir=in": (1, "in"),
    }
    for query, (depth, direction) in cases.items():
        STATE["trace_calls"].clear()
        expect(alice.get(url(world, "answered", query)).status_code == 200, f"{query} status")
        expect(STATE["trace_calls"] == [(answered, depth, direction)], f"{query}: {STATE}")
    passed("e: depth 9 is clamped to 6, depth x is 2, depth 0 is 1; a bad dir is both")


# --- (f) the controls ------------------------------------------------------------------------


def check_controls(world: Any) -> None:
    alice, _ = world.web("alice")
    root, _ = world.web("root")
    plain = Page(alice.get(url(world, "answered", "?tab=trace")).text)
    expect(len(plain.controls) == 5, f"controls {[c['text'] for c in plain.controls]}")
    for control in plain.controls:
        expect(control["href"].startswith("?tab=trace&depth="), f"href {control['href']}")
        expect("mode=technical" not in control["href"], f"alice has a mode {control['href']}")
    current = [c["text"] for c in plain.controls if c["current"] == "true"]
    expect(current == ["both directions"], f"current {current}")
    texts = [c["text"] for c in plain.controls]
    expect(texts == ["both directions", "outbound", "inbound", "Less", "More"], f"{texts}")
    hrefs = [c["href"] for c in plain.controls]
    expect(hrefs[3] == "?tab=trace&depth=1&dir=both", f"Less {hrefs[3]}")
    expect(hrefs[4] == "?tab=trace&depth=3&dir=both", f"More {hrefs[4]}")
    high = Page(alice.get(url(world, "answered", "?tab=trace&depth=9")).text)
    expect("More" not in [c["text"] for c in high.controls], "More at the top of the clamp")
    expect("Less" in [c["text"] for c in high.controls], "no Less at depth 6")
    low = Page(alice.get(url(world, "answered", "?tab=trace&depth=1")).text)
    expect("Less" not in [c["text"] for c in low.controls], "Less at depth 1")
    rooted = Page(root.get(url(world, "answered", "?tab=trace&mode=technical")).text)
    expect(len(rooted.controls) == 5, f"root controls {len(rooted.controls)}")
    for control in rooted.controls:
        expect(control["href"].startswith("?tab=trace&depth="), f"root href {control['href']}")
        expect(control["href"].endswith("&mode=technical"), f"root href {control['href']}")
    passed("f: controls carry &mode=technical only for root; clamp hides Less at 1, More at 6")


# --- (g) hidden records ----------------------------------------------------------------------


def check_hidden(world: Any) -> None:
    alice, _ = world.web("alice")
    start = len(world.answers)
    calls = (len(STATE["link_calls"]), len(STATE["trace_calls"]))
    for key in ("secret", "restricted"):
        for tab in ("links", "trace"):
            query = f"?tab={tab}"
            reference = alice.get(f"/web/p/{PROJECT}/records/{UNKNOWN}{query}")
            hidden = alice.get(url(world, key, query))
            expect(reference.status_code == 404, f"unknown {reference.status_code}")
            expect(hidden.status_code == 404, f"{key}{query}: {hidden.status_code}")
            expect(hidden.content == reference.content, f"{key}{query}: not the 404 page")
    ids = {world.ids["secret"], world.ids["restricted"]}
    new = STATE["link_calls"][calls[0] :] + [c[0] for c in STATE["trace_calls"][calls[1] :]]
    expect(not ids & set(new), f"a read was made for a hidden record: {new}")
    for response in world.answers[start:]:
        for secret in ("PRIVSECRET", "RESTSECRET"):
            expect(secret.encode() not in response.content, f"{secret} in an answer for alice")
    passed("g: secret and restricted with tab=links or tab=trace: the 404 page; no read made")


# --- (h) the read is unavailable -------------------------------------------------------------


def check_unavailable(world: Any) -> None:
    alice, _ = world.web("alice")
    STATE["trace_error"] = NotImplementedError("the trace read is not installed")
    try:
        response = alice.get(url(world, "answered", "?tab=trace"))
    finally:
        STATE["trace_error"] = None
    expect(response.status_code == 200, f"unavailable trace {response.status_code}")
    pre = Page(response.text).pre
    expect(pre.startswith("Trace unavailable:"), f"pre {pre!r}")
    passed("h: a Trace read that raises NotImplementedError shows 'Trace unavailable:', status 200")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        world = S4.World(Path(tmp))
        try:
            STATE["tree"] = make_tree(str(world.ids["answered"]))
            with (
                mock.patch.object(WebReadClient, "links_of", fake_links_of),
                mock.patch.object(WebReadClient, "trace", fake_trace),
            ):
                check_nav(world)
                check_links(world)
                check_empty(world)
                check_trace(world)
                check_query(world)
                check_controls(world)
                check_hidden(world)
                check_unavailable(world)
        finally:
            world.backend.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
