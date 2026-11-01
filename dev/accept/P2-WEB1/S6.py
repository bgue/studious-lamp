"""Acceptance script for P2-WEB1 S6: the record screen on the web (``tl_web.pages.record``).

Reuses ``S4.World`` (loaded as a module, as T15 does; the S4 demo page is switched off). Prints one
``PASS <letter>: ...`` per check, exits 0 when all pass and 1 on the first failure. The expected
text is computed here by calling the pure modules (``record_text``, ``properties_text``) on reads
from ``world.reads(name)``. A fake tab ``probe`` and an invisible tab ``ghost`` are registered
before ``create_app`` (the World builds the app).
"""

from __future__ import annotations

import html
import importlib.util
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

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
from tl_tui import display  # noqa: E402
from tl_web import present  # noqa: E402
from tl_web.pages import record as record_page  # noqa: E402
from tl_web.reads import MIRRORS, WebReadClient  # noqa: E402

expect, passed, Doc, PROJECT, SCOPE = S4.expect, S4.passed, S4.Doc, S4.PROJECT, S4.SCOPE
RECORD_REGIONS = ["rec-header", "rec-tabs", "log-actions", "log-panel", "rec-body", "log-status"]
SECRETS = ("PRIVSECRET", "RESTSECRET", "P123-RFI-0004", "P123-RFI-0005")
PLANTED = 'Plant <i>bold</i> & "quoted"'
BEFORE_MIRRORS = 22  # the reads of S5 before this piece


def register_fake_tabs() -> None:
    probe = record_page.Tab(
        "probe", "Probe", "record/details.html", lambda ctx: {"lines": f"probe {ctx.project} <b>"}
    )
    record_page.tab(probe)
    record_page.tab(
        record_page.Tab(
            "ghost", "Ghost", "details.html", lambda ctx: {"lines": "ghost"}, lambda ctx: False
        )
    )


class Page(HTMLParser):
    """What the record page shows: the header lines, the tab links, the body text and table."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.h1 = ""
        self.state = ""
        self.links: list[dict[str, str | None]] = []
        self.pre = ""
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self._in: list[str] = []
        self._link: dict[str, str | None] | None = None
        self._cell: list[str] | None = None
        self._row: list[str] | None = None
        self._head: list[str] | None = None
        self._pre: list[str] | None = None
        self._h: list[str] | None = None
        self._p: list[str] | None = None
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        self._in.append(a.get("id") or "")
        within = set(self._in)
        if tag == "h1" and "rec-header" in within:
            self._h = []
        if tag == "p" and "rec-header" in within:
            self._p = []
        if tag == "a" and "rec-tabs" in within:
            self._link = {"href": a.get("href"), "current": a.get("aria-current"), "text": ""}
        if tag == "pre" and "rec-body" in within:
            self._pre = []
        if "rec-body" in within:
            if tag == "th":
                self._head = []
            if tag == "tr":
                self._row = []
            if tag == "td":
                self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if self._in:
            self._in.pop()
        if tag == "h1" and self._h is not None:
            self.h1, self._h = "".join(self._h), None
        if tag == "p" and self._p is not None:
            self.state, self._p = "".join(self._p), None
        if tag == "a" and self._link is not None:
            self.links.append(self._link)
            self._link = None
        if tag == "pre" and self._pre is not None:
            self.pre, self._pre = "".join(self._pre), None
        if tag == "th" and self._head is not None:
            self.headers.append("".join(self._head))
            self._head = None
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell))
            self._cell = None
        if tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        for part in (self._h, self._p, self._pre, self._head, self._cell):
            if part is not None:
                part.append(data)
        if self._link is not None:
            self._link["text"] = (self._link["text"] or "") + data


def url(world: Any, key: str, query: str = "") -> str:
    return f"/web/p/{PROJECT}/records/{world.ids[key]}{query}"


def status_text(response: Any) -> str:
    return html.unescape(Doc(response.text).texts.get("log-status", "")).strip()


def labels_of(world: Any, name: str, record: dict[str, Any]) -> Any:
    return present.load_labels(
        present.as_client(world.reads(name)), SCOPE, ("core.Record", str(record["type"]))
    )


def expected_details(world: Any, name: str, record: dict[str, Any], *, technical: bool) -> str:
    reader = world.reads(name)
    rows = present.details.details_for(
        present.as_client(reader),
        PROJECT,
        record,
        labels_of(world, name, record),
        record_page.mode_for(technical),
    )
    return present.record_text.details_lines(rows)


def expected_properties(world: Any, name: str, record: dict[str, Any], *, technical: bool) -> str:
    reader = world.reads(name)
    try:
        meta = reader.form_metadata(SCOPE, record["type"], record["id"])
        report = reader.conformance(record["id"])
    except Exception as exc:  # noqa: BLE001
        mapped = body_for(exc)
        expect(mapped is not None, f"properties read raised {exc!r}")
        assert mapped is not None
        return f"Properties unavailable: {mapped[1].message}"
    return present.properties_text.psets_text(meta, record, report, technical=technical)


def expected_header(
    world: Any, name: str, record: dict[str, Any], *, technical: bool
) -> tuple[str, str]:
    reader = world.reads(name)
    badges = present.record_text.badges_text(
        reader.workflow_status(record["id"]).entered_at,
        reader.link_counts([record["id"]]).get(record["id"]),
    )
    parts = present.record_text.header_parts(record, badges, technical=technical)
    return parts.identity, f"{parts.status}{parts.version} · {parts.mark}{parts.rest}"


# --- (a) imports ------------------------------------------------------------------------------


def check_imports() -> None:
    code = (
        "import sys\n"
        "import tl_tui.record_text, tl_tui.properties_text, tl_tui.links_text, tl_tui.trace_text\n"
        "assert 'textual' not in sys.modules, 'textual'\nassert 'rich' not in sys.modules, 'rich'\n"
        "import tl_web.present\nassert 'textual' not in sys.modules, 'textual via present'\n"
        "print('clean')"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=ROOT
    )
    expect(out.returncode == 0 and "clean" in out.stdout, f"fresh interpreter: {out.stderr[-300:]}")
    old = (
        "from tl_tui.widgets.record_view import details_lines, event_label, event_summary, "
        "_or_empty, _sorted_keys, _plain_keys, _EVENT_WORDS\n"
        "from tl_tui.widgets.psets_tab import psets_text, rule_text, value_text, unit_text, "
        "adhoc_lines, HEADER, CUSTOM_RULE, ADD_LINE, LEGEND\n"
        "from tl_tui.widgets.links_tab import TableRow, status_text, pin_text, group_title, "
        "missing_line, build_rows, _link_row, _header_row, SUGGESTED\n"
        "from tl_tui.widgets.trace_tab import node_text, tree_lines, head_text, DIRECTIONS, "
        "DIRECTION_WORDS, MIN_DEPTH, MAX_DEPTH, Direction\nprint('old')"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", old], capture_output=True, text=True, cwd=ROOT
    )
    expect(out.returncode == 0 and "old" in out.stdout, f"old names: {out.stderr[-300:]}")
    public = {n for n, m in vars(WebReadClient).items() if not n.startswith("_") and callable(m)}
    expect(public == set(MIRRORS), f"MIRRORS {sorted(public ^ set(MIRRORS))}")
    expect(len(MIRRORS) == BEFORE_MIRRORS + 2, f"{len(MIRRORS)} mirrors")
    expect(
        MIRRORS["conformance"] == "get_conformance" and MIRRORS["trace"] == "get_record_trace",
        "the two new rows",
    )
    passed(
        "a: four modules import without textual/rich; old names import; MIRRORS +conformance +trace"
    )


# --- (b) the frame ----------------------------------------------------------------------------


def check_frame(world: Any) -> None:
    alice, _ = world.web("alice")
    record = world.reads("alice").get_record_by_id(world.ids["answered"])
    assert record is not None
    response = alice.get(url(world, "answered"))
    expect(response.status_code == 200, f"page {response.status_code}")
    doc = Doc(response.text)
    seen = [i for i in doc.ids if i in RECORD_REGIONS]
    expect(seen == RECORD_REGIONS, f"regions {seen}")
    page = Page(response.text)
    identity, state = expected_header(world, "alice", record, technical=False)
    expect((page.h1, page.state) == (identity, state), f"header {(page.h1, page.state)}")
    expect("v" + str(record["version"]) not in state, "the version shows in plain mode")
    names = [str(link["href"]).split("tab=")[1] for link in page.links]
    registered = [n for n in record_page.ORDER if n in record_page.TABS]
    expect(registered == ["details", "properties", "history"], f"registered {registered}")
    expect(names == [*registered, "probe"], f"nav {names}")
    current = [link["href"] for link in page.links if link["current"] == "page"]
    expect(current == ["?tab=details"], f"aria-current on {current}")
    expect(
        [link["text"] for link in page.links[:3]] == ["Details", "Properties", "History"], "labels"
    )
    expect("<script" not in response.text.split("<main>")[1], "script in the body")
    passed("b: regions in order; #rec-header == header_parts; nav lists registered tabs")


# --- (c) the three tabs -----------------------------------------------------------------------


def check_tabs(world: Any) -> None:
    alice, _ = world.web("alice")
    root, _ = world.web("root")
    reader = world.reads("alice")
    for key in ("answered", "waiting"):
        record = reader.get_record_by_id(world.ids[key])
        assert record is not None
        got = Page(alice.get(url(world, key)).text)
        want = expected_details(world, "alice", record, technical=False)
        expect(got.pre == want and want != "", f"{key}: Details differ\n{got.pre!r}\n{want!r}")
        got = Page(alice.get(url(world, key, "?tab=properties")).text)
        want = expected_properties(world, "alice", record, technical=False)
        expect(got.pre == want, f"{key}: Properties differ\n{got.pre!r}\n{want!r}")
        events = reader.history(record["id"])
        labels = labels_of(world, "alice", record)
        got = Page(alice.get(url(world, key, "?tab=history")).text)
        rows = [
            list(present.record_text.history_cells(e, labels, technical=False))
            for e in reversed(events)
        ]
        expect(got.headers == ["When", "What", "By", "Summary"], f"headers {got.headers}")
        expect(got.rows == rows and len(rows) > 0, f"{key}: History rows\n{got.rows}\n{rows}")
    record = reader.get_record_by_id(world.ids["answered"])
    assert record is not None
    properties = Page(alice.get(url(world, "answered", "?tab=properties")).text).pre
    print(f"  (properties body: {properties.splitlines()[0][:60]!r})")
    # the admin in technical mode
    rreader = world.reads("root")
    rrecord = rreader.get_record_by_id(world.ids["answered"])
    assert rrecord is not None
    got = Page(root.get(url(world, "answered", "?tab=history&mode=technical")).text)
    expect(got.headers == ["#", "When", "Event", "Actor", "Summary"], f"headers {got.headers}")
    rlabels = labels_of(world, "root", rrecord)
    rows = [
        list(present.record_text.history_cells(e, rlabels, technical=True))
        for e in reversed(rreader.history(rrecord["id"]))
    ]
    expect(got.rows == rows and len(rows) > 0, f"technical History rows\n{got.rows}\n{rows}")
    # a planted `<` in a subject shows escaped everywhere
    planted = alice.get(url(world, "planted"))
    expect(planted.status_code == 200, f"planted {planted.status_code}")
    for tab in ("details", "properties", "history"):
        raw = alice.get(url(world, "planted", f"?tab={tab}")).text
        expect("<i>" not in raw and "</i>" not in raw, f"{tab}: raw markup in the page")
        expect("<u>" not in raw and "</u>" not in raw, f"{tab}: raw markup in the page")
    expect("Plant &lt;i&gt;bold&lt;/i&gt;" in planted.text, "the subject is not escaped")
    body = alice.get(url(world, "planted", "?tab=details")).text
    expect("Why &lt;u&gt;this&lt;/u&gt;?" in body, "the question is not escaped in Details")
    expect(Page(planted.text).h1.endswith(PLANTED), f"h1 {Page(planted.text).h1!r}")
    passed(
        "c: Details == details_lines, Properties == psets_text, History == history_cells; escaped"
    )


# --- (d) hidden = missing ---------------------------------------------------------------------


def check_hidden(world: Any) -> None:
    alice, _ = world.web("alice")
    start = len(world.answers)
    reference = alice.get(f"/web/p/{PROJECT}/records/01J00000000000000000000000")
    expect(reference.status_code == 404, f"unknown {reference.status_code}")
    for key in ("secret", "restricted"):
        for query in ("", "?tab=properties", "?tab=history", "?tab=probe"):
            hidden = alice.get(url(world, key, query))
            expect(hidden.status_code == 404, f"{key}{query}: {hidden.status_code}")
            expect(hidden.content == reference.content, f"{key}{query}: not the 404 page")
    others = [
        alice.get(f"/web/p/OTHER/records/{world.ids['answered']}"),  # url project != scope
        alice.get(url(world, "other")),  # a record of another project scope
        alice.get(url(world, "answered", "?tab=nope")),
        alice.get(url(world, "answered", "?tab=links")),  # not registered yet
        alice.get(url(world, "answered", "?tab=ghost")),  # registered, not visible
        alice.get(f"/web/p/bad%20project/records/{world.ids['answered']}"),
    ]
    for response in others:
        expect(response.status_code == 404, f"{response.url}: {response.status_code}")
        expect(response.content == reference.content, f"{response.url}: not the 404 page")
    expect(
        "Ghost" not in Page(alice.get(url(world, "answered")).text).links.__repr__(),
        "an invisible tab is in the nav",
    )
    for response in world.answers[start:]:
        for secret in (*SECRETS, world.ids["secret"], world.ids["restricted"]):
            expect(secret.encode() not in response.content, f"{secret} in an answer for alice")
    passed("d: hidden, other-project, unknown/unregistered/invisible tab: one 404, no secret text")


# --- (e) technical mode -----------------------------------------------------------------------


def check_mode(world: Any) -> None:
    alice, _ = world.web("alice")
    root, _ = world.web("root")
    record = world.reads("alice").get_record_by_id(world.ids["answered"])
    assert record is not None
    response = alice.get(url(world, "answered", "?mode=technical"))
    expect(status_text(response) == present.REFUSAL, f"status {status_text(response)!r}")
    page = Page(response.text)
    expect(page.pre == expected_details(world, "alice", record, technical=False), "alice not plain")
    expect(f"v{record['version']}" not in page.state, "alice saw the version")
    expect("mode=technical" not in response.text, "mode carried for a non-admin")
    plain = alice.get(url(world, "answered"))
    expect(status_text(plain) == "", f"plain status {status_text(plain)!r}")
    rrecord = world.reads("root").get_record_by_id(world.ids["answered"])
    assert rrecord is not None
    response = root.get(url(world, "answered", "?mode=technical"))
    expect(status_text(response) != present.REFUSAL, "an admin was refused")
    page = Page(response.text)
    want = expected_details(world, "root", rrecord, technical=True)
    expect(page.pre == want, f"root Details\n{page.pre!r}\n{want!r}")
    expect(want != expected_details(world, "root", rrecord, technical=False), "no technical rows")
    expect(
        page.state == expected_header(world, "root", rrecord, technical=True)[1]
        and f" · v{rrecord['version']}" in page.state,
        f"root state {page.state!r}",
    )
    for link in page.links:
        expect(str(link["href"]).endswith("&mode=technical"), f"link {link['href']} lacks the mode")
    expect("mode=technical" not in root.get(url(world, "answered")).text, "mode stored")
    passed("e: alice: plain + REFUSAL, no mode on links; root: raw rows, mode on every tab link")


# --- (f) actions and sign-in ------------------------------------------------------------------


def check_actions(world: Any) -> None:
    alice, _ = world.web("alice")
    seen = 0
    for key, number in (("answered", "0001"), ("waiting", "0003"), ("closed", "0002")):
        mine = Doc(alice.get(url(world, key)).text)
        log = Doc(alice.get(f"/web/p/{PROJECT}/rfis?sel=P123-RFI-{number}").text)
        ours = [b["attrs"]["data-command"] for b in mine.buttons]
        theirs = [b["attrs"]["data-command"] for b in log.buttons]
        expect(ours == theirs, f"{key}: bar {ours} != log {theirs}")
        seen += len(ours)
        if ours:
            expect(
                [b["attrs"].get("hx-post") or b["attrs"].get("hx-get") for b in mine.buttons]
                == [b["attrs"].get("hx-post") or b["attrs"].get("hx-get") for b in log.buttons],
                f"{key}: urls differ",
            )
        expect("log-open" not in mine.ids, f"{key}: an open link on the record page")
    expect(seen > 0, "no RFI had an offer")
    response = world.client().get(url(world, "answered"))
    expect(response.status_code == 303, f"no cookie: {response.status_code}")
    expect(response.headers.get("location", "").startswith("/web/sign-in"), "redirect")
    passed(
        f"f: the bar lists the log page's buttons ({seen} offers); no cookie: 303 to /web/sign-in"
    )


# --- (g) the registry -------------------------------------------------------------------------


def check_registry(world: Any) -> None:
    alice, _ = world.web("alice")
    response = alice.get(url(world, "answered", "?tab=probe"))
    expect(response.status_code == 200, f"probe {response.status_code}")
    page = Page(response.text)
    expect(page.pre == f"probe {PROJECT} <b>", f"probe body {page.pre!r}")
    expect("<b>" not in response.text.split("rec-body")[1], "the probe value is not escaped")
    expect([link["current"] for link in page.links].count("page") == 1, "current marks")
    expect(
        page.links[-1]["current"] == "page" and page.links[-1]["text"] == "Probe", "probe current"
    )
    try:
        record_page.tab(record_page.Tab("probe", "Again", "details.html", lambda ctx: {}))
    except ValueError:
        pass
    else:
        raise AssertionError("a duplicate tab name was accepted")
    clash = record_page.Tab("clash", "Clash", "details.html", lambda ctx: {"record": 1})
    record_page.tab(clash)
    try:
        try:
            alice.get(url(world, "answered", "?tab=clash"))
        except ValueError:
            pass
        else:
            raise AssertionError("a tab returned a frame name")
    finally:
        del record_page.TABS["clash"]
    expect(not any(record_page._exists(n) for n in record_page.TAB_MODULES), "a tab module exists")
    record_page._loaded = False
    original = record_page.TAB_MODULES
    record_page.TAB_MODULES = (*original, "tl_web.pages.record_nowhere")
    try:
        record_page.load_tab_modules()
    finally:
        record_page.TAB_MODULES = original
    expect(record_page._loaded, "the tab modules were not loaded")
    passed("g: probe tab in nav and at ?tab=probe; duplicate refused; missing TAB_MODULES skipped")


# --- (h) plain walk ---------------------------------------------------------------------------


def check_plain(world: Any) -> None:
    alice, _ = world.web("alice")
    for key in ("answered", "waiting", "closed"):
        record = world.reads("alice").get_record_by_id(world.ids[key])
        assert record is not None
        labels = labels_of(world, "alice", record)
        for tab in ("details", "properties", "history", "probe"):
            text = Doc(alice.get(url(world, key, f"?tab={tab}")).text).text
            found = display.find_technical(text, labels)
            expect(found == [], f"{key} {tab}: {found}")
    passed("h: find_technical finds nothing in the text of any tab as alice")


def main() -> int:
    check_imports()
    register_fake_tabs()
    with tempfile.TemporaryDirectory() as tmp:
        world = S4.World(Path(tmp))
        try:
            world.ids["planted"] = world.corr.forge_technical(
                "P123-RFI-0007",
                subject=PLANTED,
                state="Awaiting response",
                scope=SCOPE,
                question="Why <u>this</u>?",
            )
            world.ids["other"] = world.corr.forge_technical(
                "OTH-RFI-0001", subject="Other project", state="Draft", scope="project:OTHER"
            )
            check_frame(world)
            check_tabs(world)
            check_hidden(world)
            check_mode(world)
            check_actions(world)
            check_registry(world)
            check_plain(world)
        finally:
            world.backend.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
