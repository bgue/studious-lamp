"""ADR-0016 on the web: a walk of every route that can carry record text, as five kinds of reader.

The ledger is ``seed_hidden_world`` plus a few RFIs (see ``conftest.py``). The readers are the
five of ``packages/tl-api/tests/test_confidentiality_walk.py`` (``MAY_READ``): ``boss`` the admin
controller, ``ctl`` the document controller, ``bob`` the plain user, ``amy`` the person named on the
privileged items (the restricted-class reader) and ``bot`` the agent. ``WALK`` (in ``walk.py``) is
one table of route templates; **every GET and POST route with a path parameter must be in ``WALK``
or in ``NO_RECORD_TEXT``**, so a twin page adds one entry and this file needs no edit.

For each row and each reader:

a. hidden equals missing: for a record the reader may not read, the answer is byte-equal to the
   answer for an id that never existed (status, every header but ``Date`` and ``Set-Cookie``, body),
   no read is made for it on the tab routes, and no marker string of it is in any answer;
b. visibility comes before the count and before the LIMIT: a log lists the rows the JSON route lists
   for that reader, and its status line counts those and nothing else;
c. a visible record's text is there; for the agent every route is 401.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest import mock
from urllib.parse import quote

import pytest
from tl_web import present
from tl_web.reads import WebReadClient

READERS = ("boss", "ctl", "bob", "amy", "bot")
PEOPLE = ("boss", "ctl", "bob", "amy")
IGNORED_HEADERS = {"date", "set-cookie"}


def test_the_readers_are_the_five_of_the_json_walk(k: Any) -> None:
    assert set(READERS) == set(k.READERS)
    assert set(k.MAY_READ["bob"]) == {"open"} and "bogus" not in k.MAY_READ["ctl"]


def test_every_parameter_route_is_walked_or_named(world: Any, k: Any, walk: Any) -> None:
    """The test that makes a twin page add its entry: an unlisted route fails here."""
    routes = [(m, p) for m, p in k.web_routes(world.app, {"GET", "POST"}) if "{" in p]
    assert len(routes) >= 8
    unlisted = [r for r in routes if r not in walk.WALK and r not in walk.NO_RECORD_TEXT]
    assert not unlisted, (
        f"routes with a path parameter that the walk does not know: {unlisted}. Add one entry to "
        "WALK in tests/walk.py (the kinds of text it can carry and how to ask for it), or to "
        "NO_RECORD_TEXT with the reason it carries none."
    )


def test_the_walk_tables_name_no_route_that_is_gone(world: Any, k: Any, walk: Any) -> None:
    live = set(k.web_routes(world.app))
    stale = [r for r in (*walk.WALK, *walk.NO_RECORD_TEXT) if r not in live]
    assert not stale, f"WALK or NO_RECORD_TEXT names routes the app no longer has: {stale}"
    assert all(reason.strip() for reason in walk.NO_RECORD_TEXT.values())  # a reason per entry
    assert not set(walk.WALK) & set(walk.NO_RECORD_TEXT)


def test_the_walk_covers_the_pages_the_brief_names(walk: Any) -> None:
    templates = {t for _, t in walk.WALK}
    for needle in ("/rfis", "/correspondence", "/documents", "/panel/", "/records/{record_id}",
                   "/view", "/content", "/page1.png", "/do/{command}"):  # fmt: skip
        assert any(needle in t for t in templates), needle
    assert walk.TABS == ("details", "properties", "history", "links", "trace", "thread", "files")


class Session:
    """A reader: the signed-in client, what it may read, and the markers it must never see."""

    def __init__(self, world: Any, k: Any, walk: Any, name: str) -> None:
        self.name = name
        self.web = world.web(name)
        self.may: set[str] = set(k.MAY_READ[name])
        self.targets = walk.targets(world)
        self.walk = walk
        self.hidden = [t for t in self.targets.values() if not t.readable_by(self.may)]
        self.markers = [m for t in self.hidden for m in t.markers]

    def probes(self) -> Iterator[tuple[Any, Any, Any]]:
        """``(row, target, probe)`` for every route of the walk and every record or file it fits."""
        for row in self.walk.WALK.values():
            for target in self.targets.values():
                if row.applies(target):
                    for probe in row.build(target):
                        yield row, target, probe

    def ask(self, method: str, url: str) -> Any:
        headers = self.web.headers() if method == "POST" else {}
        return self.web.client.request(method, url, headers=headers)


def swapped(response: Any, pairs: list[tuple[str, str]]) -> bytes:
    body = response.content
    for text, _ in pairs:
        if text:
            body = body.replace(text.encode(), b"@")
    return body


def same_answer(hidden: Any, never: Any, hidden_pairs: list[tuple[str, str]],
                never_pairs: list[tuple[str, str]], *, strict: bool) -> None:  # fmt: skip
    assert hidden.status_code == never.status_code
    skip = IGNORED_HEADERS | (set() if strict else {"content-length"})
    a = {k: v for k, v in hidden.headers.items() if k not in skip}
    b = {k: v for k, v in never.headers.items() if k not in skip}
    assert a == b, "the headers of a hidden record differ from those of a missing one"
    assert swapped(hidden, hidden_pairs) == swapped(never, never_pairs)


@pytest.fixture
def sessions(world: Any, k: Any, walk: Any) -> Any:
    cache: dict[str, Session] = {}

    def get(name: str) -> Session:
        if name not in cache:
            cache[name] = Session(world, k, walk, name)
        return cache[name]

    return get


# --- a. hidden equals missing -------------------------------------------------------------------


@pytest.mark.parametrize("reader", PEOPLE)
def test_a_hidden_record_is_byte_equal_to_a_missing_one_on_every_route(
    sessions: Any, reader: str
) -> None:
    s = sessions(reader)
    checked = 0
    for _, target, probe in s.probes():
        if target.readable_by(s.may) or probe.never_url is None:
            continue
        hidden = s.ask(probe.method, probe.url)
        never = s.ask(probe.method, probe.never_url)
        same_answer(
            hidden, never,
            [(target.id, ""), (target.number, ""), (probe.typed[0], "")],
            [(s.walk.NEVER_ID, ""), (s.walk.NEVER_FILE, ""), (target.never_number, ""),
             (probe.typed[1], "")],
            strict=probe.typed == ("", ""),
        )  # fmt: skip
        checked += 1
    assert checked >= 15, "the walk found too few hidden requests"


@pytest.mark.parametrize("reader", PEOPLE)
def test_no_marker_string_of_a_hidden_record_is_in_any_answer(sessions: Any, reader: str) -> None:
    s = sessions(reader)
    assert s.markers  # every person has something hidden
    for _, target, probe in s.probes():
        response = s.ask(probe.method, probe.url)
        # what the reader typed (a filter, an id or number in the address) may be echoed
        typed = [(probe.typed[0], ""), (target.id, ""), (target.number, "")]
        body = swapped(
            response,
            [(t, "") for t, _ in typed if t and quote(t) in probe.url or t == probe.typed[0]],
        )
        for marker in s.markers:
            assert marker.encode() not in body, f"{reader}: {marker} in {probe.label} {probe.url}"


@pytest.mark.parametrize("reader", PEOPLE)
def test_no_marker_is_in_a_walk_with_the_technical_mode_either(sessions: Any, reader: str) -> None:
    s = sessions(reader)
    pages = [
        p for _, t, p in s.probes() if p.method == "GET" and not t.is_file and "?" not in p.url
    ]
    assert len(pages) >= 20
    for probe in pages:
        response = s.ask("GET", f"{probe.url}?mode=technical")
        for marker in s.markers:
            assert marker.encode() not in response.content, f"{reader}: {marker} in {probe.url}"


@pytest.fixture
def counted(world: Any) -> Iterator[list[tuple[str, str]]]:
    """Every read a tab makes (name, record id), the real read still runs."""
    calls: list[tuple[str, str]] = []
    patches = []
    names = (
        "links_of", "trace", "thread_page", "list_record_files", "history", "form_metadata",
        "conformance", "link_counts", "workflow_status", "allowed_actions",
    )  # fmt: skip
    for name in names:
        real = getattr(WebReadClient, name)

        def wrapper(self: Any, *args: Any, _real: Any = real, _name: str = name, **kw: Any) -> Any:
            first = args[0] if args else next(iter(kw.values()), "")
            if _name == "form_metadata":
                first = args[2] if len(args) > 2 else kw.get("record_id", "")
            calls.append((_name, str(first) if not isinstance(first, list) else ",".join(first)))
            return _real(self, *args, **kw)

        patch = mock.patch.object(WebReadClient, name, wrapper)
        patch.start()
        patches.append(patch)
    try:
        yield calls
    finally:
        for patch in patches:
            patch.stop()


@pytest.mark.parametrize("reader", PEOPLE)
def test_no_read_is_made_for_a_hidden_record_on_the_tab_routes(
    sessions: Any, counted: list[tuple[str, str]], reader: str
) -> None:
    s = sessions(reader)
    for target in s.hidden:
        if target.is_file:
            continue
        for tab in s.walk.TABS:
            s.ask("GET", f"{s.walk.P}/records/{target.id}?tab={tab}")
        s.ask("GET", f"{s.walk.P}/records/{target.id}/do/{s.walk.UNOFFERED}/form")
        s.ask("POST", f"{s.walk.P}/records/{target.id}/do/{s.walk.UNOFFERED}")
    touched = {record for _, record in counted}
    leaked = [t.kind for t in s.hidden if not t.is_file and t.id in touched]
    assert not leaked, f"{reader}: a tab read was made for {leaked}"
    # and the reads do run for a record the reader may read (the counter works)
    s.ask("GET", f"{s.walk.P}/records/{s.targets['open_rfi'].id}?tab=history")
    assert ("history", s.targets["open_rfi"].id) in counted


# --- b. visibility before the count and the LIMIT -----------------------------------------------


def numbers_of_rfis(j: Any) -> list[str]:
    return [r["number"] for r in j["lines"]]


def numbers_of_list(j: Any) -> list[str]:
    return [r["number"] for r in j]


@pytest.mark.parametrize("reader", PEOPLE)
def test_a_log_lists_the_rows_the_json_route_lists_and_counts_only_those(
    world: Any, sessions: Any, htmlkit: Any, reader: str
) -> None:
    s = sessions(reader)
    api = world.api(reader)
    reads = world.reads(reader)
    labels = lambda types: present.load_labels(  # noqa: E731
        present.as_client(reads), "project:P123", types
    )
    logs = (
        ("rfis", "/projects/P123/rfis", numbers_of_rfis),
        ("correspondence", "/projects/P123/correspondence", numbers_of_list),
        ("documents", "/projects/P123/documents", numbers_of_list),
    )
    for slug, path, numbers in logs:
        sent = api.get(path, params={"limit": 500})
        assert sent.status_code == 200, (reader, slug, sent.text[:200])
        want = numbers(sent.json())
        page = htmlkit.parse(s.ask("GET", f"{s.walk.P}/{slug}").text)
        got = [r.get("data-number") for r in page.log_rows()]
        assert sorted(got) == sorted(want), f"{reader} {slug}: rows differ from the JSON route"
        for target in s.hidden:
            assert target.number not in got, f"{reader}: {target.kind} is a row of {slug}"
        status = page.status()
        if slug == "rfis":
            assert status == present.rfi_text.rfi_summary(reads.list_rfis("P123"))
        elif slug == "correspondence":
            assert status == present.correspondence_text.summary_line("register", len(want))
        else:
            expected = present.document_text.summary_line(
                len(want), len(want), state=None, doc_type=None, include_void=False, text="",
                labels=labels(("documents.Document",)),
            )  # fmt: skip
            assert status == expected
        assert (
            str(len(want)) in status or slug == "rfis"
        )  # the count in the line is the visible one


@pytest.mark.parametrize("reader", PEOPLE)
def test_a_limit_counts_visible_rows_only(world: Any, reader: str) -> None:
    """Hidden rows go before the LIMIT: asking for exactly the visible count gets them all."""
    reads = world.reads(reader)
    everything = reads.list_rfis("P123", limit=500)
    visible = len(everything.lines)
    assert everything.total == visible
    assert len(reads.list_rfis("P123", limit=visible).lines) == visible
    assert len(reads.list_rfis("P123", limit=1).lines) == 1
    docs = reads.list_documents("P123", limit=500)
    assert len(reads.list_documents("P123", limit=len(docs))) == len(docs)


# --- c. a visible record's text, and the agent --------------------------------------------------


@pytest.mark.parametrize("reader", PEOPLE)
def test_a_record_the_reader_may_read_answers_with_its_text(sessions: Any, reader: str) -> None:
    s = sessions(reader)
    seen = 0
    for _, target, probe in s.probes():
        if not target.readable_by(s.may):
            continue
        response = s.ask(probe.method, probe.url)
        if probe.label.startswith("record "):
            assert response.status_code == 200, f"{reader}: {probe.label} {probe.url}"
        if probe.positive is not None:
            assert probe.positive(response), f"{reader}: {probe.label} of {target.kind}"
            seen += 1
        if probe.label in ("action form", "action run"):
            assert response.status_code == 409, f"{reader}: {probe.label}"  # offered nothing
    readable = [t for t in s.targets.values() if t.readable_by(s.may) and not t.is_file]
    assert seen == len(readable)  # one details page per record the reader may read


@pytest.mark.parametrize("reader", PEOPLE)
def test_a_file_the_reader_may_read_answers_and_one_it_may_not_does_not(
    sessions: Any, reader: str
) -> None:
    s = sessions(reader)
    for kind in s.walk.FILE_NEEDS:
        target = s.targets[kind]
        readable = target.readable_by(s.may)
        view = s.ask("GET", f"{s.walk.P}/files/{target.id}/view")
        content = s.ask("GET", f"/web/files/{target.id}/content{s.walk.SCOPE_Q}")
        page1 = s.ask("GET", f"/web/files/{target.id}/page1.png{s.walk.SCOPE_Q}")
        if readable:
            assert view.status_code == 200 and content.status_code == 200, (reader, kind)
            assert page1.status_code == 404 and page1.json()["error"] == "no_preview"
        else:
            assert view.status_code == content.status_code == page1.status_code == 404
            assert content.json()["error"] != "no_preview"
            assert page1.json()["error"] != "no_preview"  # not "there is a file, but no picture"


def test_an_agent_behind_the_cookie_is_401_on_every_route_of_the_walk(sessions: Any) -> None:
    s = sessions("bot")
    count = 0
    for _, _, probe in s.probes():
        response = s.ask(probe.method, probe.url)
        assert response.status_code == 401, f"{probe.label} {probe.url}: {response.status_code}"
        count += 1
    assert count >= 80
