"""The table of web routes the walks go through (``WALK``) and the routes that carry no record text.

Loaded by the ``walk`` fixture of ``conftest.py`` (no sibling imports in importlib mode), used by
``test_web_confidentiality_walk.py`` and ``test_web_plain_walk.py``. A twin ticket that adds a page
adds one entry to ``WALK`` (a route template, the kinds of record text it can carry, and a function
that builds its requests for one record or file); a route with a path parameter that is in neither
``WALK`` nor ``NO_RECORD_TEXT`` fails ``test_every_parameter_route_is_walked_or_named``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

P = "/web/p/P123"
SCOPE_Q = "?scope=project%3AP123"
#: Same length as a real record id, so the 404 for it has the same size as the 404 for a hidden one.
NEVER_ID = "01J00000000000000000000000"
NEVER_FILE = "01J00000000000000000000001"
TABS = ("details", "properties", "history", "links", "trace", "thread", "files")
#: A command in the terminal's action table that no record of these types is ever offered.
UNOFFERED = "RenameTag"

#: record kind -> the key of ``MAY_READ`` a reader needs for it (``None``: every reader reads it).
NEEDS: dict[str, str | None] = {
    "open": None, "open_rfi": None, "open_document": None, "waiting": None, "closed": None,
    "draft": None, "planted": None,
    "restricted": "restricted", "restricted_rfi": "restricted", "privileged": "privileged",
    "bogus": "bogus", "secret_rfi": "secret_rfi", "commercial": "commercial",
    "document": "document",
}  # fmt: skip
FILE_NEEDS: dict[str, str | None] = {"open_file": None, "restricted_file": "file"}
#: The words only the record's own text holds (``tl_mod_correspondence.confseed.TOKENS`` and the
#: subjects of the extra RFIs).
WORDS = {
    "restricted": "RESTOKEN", "privileged": "PRIVTOKEN", "bogus": "BOGUSTOKEN",
    "secret_rfi": "SECRETRFITOKEN", "commercial": "COMMTOKEN", "document": "DOCTOKEN",
    "restricted_rfi": "RESTSECRET", "restricted_file": "FILETOKEN",
}  # fmt: skip
FAMILY = {
    "open": "corr", "restricted": "corr", "privileged": "corr", "bogus": "corr",
    "open_rfi": "rfi", "secret_rfi": "rfi", "waiting": "rfi", "closed": "rfi", "draft": "rfi",
    "restricted_rfi": "rfi", "planted": "rfi", "commercial": "ew",
    "document": "doc", "open_document": "doc",
}  # fmt: skip
NEVER_NUMBER = {
    "rfi": "P123-RFI-9999",
    "corr": "P123-COR-9999",
    "ew": "P123-EW-9999",
    "doc": "ISO-9999",
}


@dataclass(frozen=True)
class Target:
    """One record or file the walk asks about."""

    kind: str
    id: str
    number: str  # the number or key ("" for a file)
    family: str  # rfi, corr, ew, doc, file
    needs: str | None
    markers: tuple[str, ...]  # text only this thing holds: it must not reach a reader who may not
    is_file: bool = False

    def readable_by(self, may: set[str]) -> bool:
        return self.needs is None or self.needs in may

    @property
    def never_number(self) -> str:
        return NEVER_NUMBER.get(self.family, "P123-XXX-9999")


@dataclass(frozen=True)
class Probe:
    """One request: the real one and the same one for an id that never existed."""

    method: str
    url: str
    never_url: str | None  # ``None``: a list or a page with no id to swap
    typed: tuple[str, str] = ("", "")  # text the reader typed (a filter): echoed, so swapped out
    label: str = ""
    positive: Callable[[Any], bool] | None = None  # what a visible record's answer must hold


@dataclass(frozen=True)
class Row:
    kinds: str  # the kinds of record text the route can carry
    build: Callable[[Target], list[Probe]]
    applies: Callable[[Target], bool] = lambda t: not t.is_file  # noqa: E731


def targets(w: Any) -> dict[str, Target]:
    """Every record and file kind of the world as a ``Target``."""
    found: dict[str, Target] = {}
    for kind, needs in NEEDS.items():
        words = [WORDS[kind]] if kind in WORDS else []
        found[kind] = Target(
            kind, w.ids[kind], w.numbers[kind], FAMILY[kind], needs,
            (*words, w.numbers[kind], w.ids[kind]),
        )  # fmt: skip
    files = {
        "open_file": ("open.pdf", "OPENFILETEXT"),
        "restricted_file": ("restricted.pdf", "FILETOKEN"),
    }
    for kind, needs in FILE_NEEDS.items():
        name, word = files[kind]
        file_id = w.hidden.extra_ids[kind]
        marks = (file_id, name, *([word] if needs else []))
        found[kind] = Target(kind, file_id, "", "file", needs, marks, is_file=True)
    return found


def _page(slug: str) -> Callable[[Target], list[Probe]]:
    """A log page asked for with the record's text as the filter and its number as the selection."""

    def build(t: Target) -> list[Probe]:
        word = WORDS.get(t.kind, t.number)
        base = f"{P}/{slug}"
        return [
            Probe("GET", f"{base}?q={quote(word)}", f"{base}?q={quote('NEVER' + word)}",
                  typed=(word, "NEVER" + word), label=f"{slug} filtered"),
            Probe("GET", f"{base}?sel={quote(t.number)}", f"{base}?sel={quote(t.never_number)}",
                  label=f"{slug} selected"),
        ]  # fmt: skip

    return build


def _panel(slug: str) -> Callable[[Target], list[Probe]]:
    def build(t: Target) -> list[Probe]:
        base = f"{P}/{slug}/panel"
        return [Probe("GET", f"{base}/{quote(t.number)}", f"{base}/{quote(t.never_number)}",
                      label=f"{slug} panel")]  # fmt: skip

    return build


def _record(t: Target) -> list[Probe]:
    out: list[Probe] = []
    for tab in TABS:
        out.append(
            Probe("GET", f"{P}/records/{t.id}?tab={tab}", f"{P}/records/{NEVER_ID}?tab={tab}",
                  label=f"record {tab}",
                  positive=(lambda r, n=t.number: n in r.text) if tab == "details" else None)
        )  # fmt: skip
    return out


def _form(t: Target) -> list[Probe]:
    url = f"{P}/records/{t.id}/do/{UNOFFERED}/form"
    return [Probe("GET", url, f"{P}/records/{NEVER_ID}/do/{UNOFFERED}/form", label="action form")]


def _do(t: Target) -> list[Probe]:
    url = f"{P}/records/{t.id}/do/{UNOFFERED}"
    return [Probe("POST", url, f"{P}/records/{NEVER_ID}/do/{UNOFFERED}", label="action run")]


def _view(t: Target) -> list[Probe]:
    return [Probe("GET", f"{P}/files/{t.id}/view", f"{P}/files/{NEVER_FILE}/view", label="viewer")]


def _file(suffix: str) -> Callable[[Target], list[Probe]]:
    def build(t: Target) -> list[Probe]:
        url = f"/web/files/{t.id}/{suffix}{SCOPE_Q}"
        never = f"/web/files/{NEVER_FILE}/{suffix}{SCOPE_Q}"
        return [Probe("GET", url, never, label=f"file {suffix}")]

    return build


def _panels(t: Target) -> list[Probe]:
    """The panel route of every log page in ``WALK``, each asked for this record's number."""
    slugs = [
        m[1].rsplit("/", 1)[1]
        for m in WALK
        if m[1].startswith("/web/p/{project}/") and m[1].count("/") == 4
    ]
    return [p for slug in slugs for p in _panel(slug)(t)]


def _files_only(t: Target) -> bool:
    return t.is_file


#: ``(method, route template)`` -> the row. Every GET and POST route with a path parameter is here
#: or in ``NO_RECORD_TEXT``.
WALK: dict[tuple[str, str], Row] = {
    ("GET", "/web/p/{project}/rfis"): Row("rfi subjects, numbers, states", _page("rfis")),
    ("GET", "/web/p/{project}/correspondence"): Row(
        "letters, RFIs, early warnings, transmittals", _page("correspondence")
    ),
    ("GET", "/web/p/{project}/documents"): Row("document numbers and titles", _page("documents")),
    # --- T09 rows (CWP register): add them under this line
    ("GET", "/web/p/{project}/cwps"): Row("cwp numbers, titles, states, CWAs", _page("cwps")),

    # --- T09b rows (CWA register): add them under this line
    ("GET", "/web/p/{project}/cwas"): Row("CWA codes, titles and locations", _page("cwas")),

    # --- T10 rows (WBS tree): add them under this line
    ("GET", "/web/p/{project}/wbs"): Row(
        "WBS codes and titles, cost codes, CWP numbers and titles", _page("wbs")
    ),

    # --- T11 rows (packages): add them under this line
    ("GET", "/web/p/{project}/packages"): Row(
        "package numbers, subjects and the CWP numbers that require them", _page("packages")
    ),

    # --- T16 rows (path): add them under this line

    ("GET", "/web/p/{project}/{log}/panel/{number:path}"): Row(
        "the panel of one row of a log: details, files, clocks, links", _panels
    ),
    ("GET", "/web/p/{project}/records/{record_id}"): Row(
        "the record page and its seven tabs: details, properties, history, links, trace, "
        "thread, files", _record
    ),  # fmt: skip
    ("GET", "/web/p/{project}/records/{record_id}/do/{command}/form"): Row(
        "the questions of an action on a record", _form
    ),
    ("POST", "/web/p/{project}/records/{record_id}/do/{command}"): Row(
        "the answer to running an action on a record", _do
    ),
    ("GET", "/web/p/{project}/files/{file_id}/view"): Row(
        "a file name and its download link", _view, _files_only
    ),
    ("GET", "/web/files/{file_id}/content"): Row(
        "the bytes of a file", _file("content"), _files_only
    ),
    ("GET", "/web/files/{file_id}/page1.png"): Row(
        "page 1 of a file", _file("page1.png"), _files_only
    ),
}  # fmt: skip

_CATCH_ALL = "the 404 page: one text for every unknown path, it reads no record"
#: Routes with a path parameter that carry no record text, and why.
NO_RECORD_TEXT: dict[tuple[str, str], str] = {
    (method, "/web/{rest:path}"): _CATCH_ALL
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")
}
