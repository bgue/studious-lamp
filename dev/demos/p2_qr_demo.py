"""Driver for dev/demos/P2-QR.sh: the clauses that are HTTP reads or label-file checks.

They are not a `tl` command.

The web client is the running `tl serve` at TL_API_URL. Each mode signs in as the people it needs
(a fresh session per mode, so the per-session miss counter of one mode does not leak into another),
reads the scan page or the API, and checks the answer. Label files and `tl` output are passed as
file paths in P2_QR_WORKDIR; no code is put on a command line, and this driver prints no code.
Each mode prints ``ok <what>`` lines; a miss prints ``FAIL <what>`` and exits 1. The shell prints
the ``PASS clause N`` line once the mode has returned.

Modes (first argument):

* ``platform SRC DST URL``: a copy of the shipped platform settings file with the default of
  ``api.public_base_url`` set to URL (the scratch file the label calls read; the shipped file is not
  changed).
* ``label-check LABEL OUT KEY PROJECT``: LABEL is the label file, OUT the stdout of `tl qr label`.
  The grouped code is the only code in the file (its QR text is checked when the QR library is
  installed, else the file must carry the no-QR note); the file and OUT hold no key, record id,
  project or register id outside the grouped print, and no code.
* ``clause2 LABEL KEY``: signed out, the scan path and a nonsense path give the same sign-in bounce;
  signed in as uma, the card shows its banner, key, "as of" and lines.
* ``visible LABEL``: as uma, the label's scan is a card (checked before the restriction).
* ``clause3 REVOKED HIDDEN``: as uma, a malformed, an unknown, a revoked and a hidden code give
  byte-identical 404 pages and headers (Date aside).
* ``clause4-hit NEW KEY``: the new code resolves to its card (fresh session).
* ``clause4-misses OLD``: as uma, eleven lookups in one session: the first ten answer 404 (the old
  code is one of them), the eleventh answers 429 with Retry-After.
* ``clause5``: the scaffold card. Prints ``ok`` when ``tl_mod_scaffold`` has no ``scan_card``.
* ``clause6-agent LABEL KEY``: the agent token (env P2_QR_AGENT_TOKEN) is refused on the scan path
  and on the two API routes before any card; a signed-in person gets the 404 miss.
* ``export-eq LS EXPORT``: the `tl qr ls` rows of a record equal its jsonl export rows.
* ``no-code OUT LABEL...``: OUT holds no code of any of the label files.
* ``card-compare LABEL CLI [BANNER]``: the signed-in web card (as uma) and the `tl qr resolve`
  output CLI show the same banner, key, title and lines; BANNER, when given, is the card's banner.
"""

from __future__ import annotations

import html
import http.client
import importlib
import importlib.util
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlencode, urlsplit

from sqlalchemy import text
from tl_adapters.db import as_target, open_uow
from tl_cli.derive_support import cell
from tl_mod_qr import labels
from tl_mod_qr.codes import new_code
from tl_mod_qr.labels import NO_QR_NOTE

PASSWORDS = {
    "uma": "a long passphrase for uma",
    "demo": "demo",
}
PROJECT = "P123"
GROUPED = re.compile(r'<div class="code">([A-Z0-9-]{19})</div>')
CODE16 = re.compile(r"[A-Z0-9]{16}")
CARD_BANNER = re.compile(r'<p class="tl-scan-banner [^"]*" role="status">(.*?)</p>', re.S)
CARD_KEY = re.compile(r'<div class="tl-card tl-scan">.*?<h1>(.*?)</h1>', re.S)
CARD_TITLE = re.compile(r'<p class="tl-scan-title">(.*?)</p>', re.S)
CARD_ASOF = re.compile(r'<p class="tl-scan-asof">as of (.*?)</p>', re.S)
CARD_LINE = re.compile(r"<dt>(.*?)</dt><dd>(.*?)</dd>", re.S)
GAS_VALUE = re.compile(r"none taken|\w+ at \d\d:\d\d UTC")
LIMITED = "Too many lookups"
MISS_STATUS = 404
SHORT_CODE = "7KQ2"  # not 16 characters: a malformed code
HTTP_TIMEOUT_S = 600


def ok(text_: str) -> None:
    print(f"ok {text_}", flush=True)


def fail(what: str) -> NoReturn:
    print(f"FAIL {what}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def check(condition: bool, what: str) -> None:
    if not condition:
        fail(what)


def workdir() -> Path:
    return Path(os.environ["P2_QR_WORKDIR"])


def code_of(label: Path) -> str:
    """The plain code of a label file (the grouped print); used only to build requests."""
    found = GROUPED.search(label.read_text(encoding="utf-8"))
    if found is None:
        fail(f"no grouped code in {label}")
    return found.group(1).replace("-", "")


def record_id_of(key: str) -> str:
    """The record id of ``key`` (read from the ledger; no command prints it)."""
    with open_uow(as_target(os.environ["TL_DB"]), readonly=True) as uow:
        row = (
            uow.conn()
            .execute(text("SELECT id FROM cur_core_record WHERE key = :key"), {"key": key})
            .first()
        )
    check(row is not None, f"no record {key}")
    assert row is not None
    return str(row.id)


# --- the web client over HTTP ---------------------------------------------------------


@dataclass
class Reply:
    status: int
    headers: list[tuple[str, str]]
    body: bytes

    def header(self, name: str) -> str | None:
        for key, value in self.headers:
            if key.lower() == name.lower():
                return value
        return None

    def comparable(self) -> tuple[int, list[tuple[str, str]], bytes]:
        """Status, headers and body; Date is left out, it changes between two requests."""
        kept = [(k, v) for k, v in self.headers if k.lower() != "date"]
        return (self.status, kept, self.body)


class Web:
    def __init__(self) -> None:
        self.base = os.environ["TL_API_URL"]
        parts = urlsplit(self.base)
        self.host, self.port = parts.hostname or "127.0.0.1", parts.port or 80

    def request(
        self,
        method: str,
        path: str,
        *,
        cookie: str | None = None,
        bearer: str | None = None,
        form: dict[str, str] | None = None,
    ) -> Reply:
        headers: dict[str, str] = {"Origin": self.base}
        if cookie:
            headers["Cookie"] = cookie
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        body = None
        if form is not None:
            body = urlencode(form)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        # Postgres scans can be slow (the core hidden filter): a generous socket timeout.
        conn = http.client.HTTPConnection(self.host, self.port, timeout=HTTP_TIMEOUT_S)
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            return Reply(response.status, response.getheaders(), response.read())
        finally:
            conn.close()

    def sign_in(self, who: str) -> str:
        """A fresh session for ``who``; returns the cookie header. The password goes in the body."""
        reply = self.request(
            "POST", "/web/sign-in", form={"username": who, "password": PASSWORDS[who]}
        )
        check(reply.status == 303, f"the {who} sign-in gave {reply.status}, not 303")
        set_cookie = reply.header("set-cookie") or ""
        found = re.search(r"tl_session=([^;]+)", set_cookie)
        check(found is not None, f"the {who} sign-in set no session cookie")
        assert found is not None
        check("HttpOnly" in set_cookie, "the session cookie is not HttpOnly")
        return f"tl_session={found.group(1)}"


def scan(code: str) -> str:
    return f"/web/q/{code}"


def is_card(reply: Reply) -> bool:
    return reply.status == 200 and b'class="tl-card tl-scan"' in reply.body


@dataclass
class Card:
    banner: str
    key: str
    title: str
    as_of: str
    lines: list[tuple[str, str]]


def parse_card(reply: Reply) -> Card:
    page = reply.body.decode("utf-8")
    banner = CARD_BANNER.search(page)
    key = CARD_KEY.search(page)
    title = CARD_TITLE.search(page)
    as_of = CARD_ASOF.search(page)
    if banner is None or key is None or title is None or as_of is None:
        fail("the card lacks its banner, key, title or as-of line")
    lines = [(html.unescape(a), html.unescape(b)) for a, b in CARD_LINE.findall(page)]
    return Card(
        banner=html.unescape(banner.group(1)),
        key=html.unescape(key.group(1)),
        title=html.unescape(title.group(1)),
        as_of=as_of.group(1),
        lines=lines,
    )


# --- label files and output -----------------------------------------------------------


def label_check(label: Path, out: Path, key: str, project: str) -> None:
    page = label.read_text(encoding="utf-8")
    stdout = out.read_text(encoding="utf-8")
    match = GROUPED.findall(page)
    check(len(match) == 1, "the label file does not carry exactly one grouped code")
    plain = match[0].replace("-", "")
    register = stdout.split()[1]
    rest = GROUPED.sub("", page)
    for leaked in (key, project, register, record_id_of(key), plain):
        check(leaked not in rest, f"the label file holds {leaked} outside the grouped print")
    check(CODE16.search(rest) is None, "the label file holds a 16-character code outside the print")
    for leaked in (plain, match[0], key, record_id_of(key)):
        check(leaked not in stdout, "the label command printed a code or an id to stdout")
    check("http" not in stdout, "the label command printed an address")
    url = labels.label_url(os.environ["P2_QR_BASE"], plain)
    if "<svg" in page:
        expected = labels.make_svg(url)
        check(expected is not None and expected in page, "the QR is not the one for the label URL")
        ok("label file: QR of <base>/web/q/<16 chars>; no key, id or project outside the print")
    else:
        check(NO_QR_NOTE in page, "the label file has neither a QR nor the no-QR note")
        ok("label file: no QR drawn (labels extra not installed); no key, id or project outside")


def ls_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


# --- the clauses -----------------------------------------------------------------------


def mode_platform(src: str, dst: str, url: str) -> None:
    text_ = Path(src).read_text(encoding="utf-8")
    old = '  - key: api.public_base_url\n    type: string\n    default: ""\n'
    check(text_.count(old) == 1, "the base-address entry is not where the demo expects it")
    Path(dst).write_text(
        text_.replace(old, old.replace('default: ""', f'default: "{url}"')), "utf-8"
    )
    ok(f"scratch platform settings written with the base address {url}")


def mode_label_check(label: str, out: str, key: str, project: str) -> None:
    label_check(Path(label), Path(out), key, project)


def mode_clause2(label: str, key: str) -> None:
    web = Web()
    code = code_of(Path(label))
    bounces = [web.request("GET", scan(code)), web.request("GET", scan(new_code()))]
    for reply in bounces:
        check(reply.status == 303, f"a signed-out scan path gave {reply.status}, not 303")
        check(not is_card(reply), "a signed-out scan path showed a card")
    locations = [(r.header("location") or "").split("?")[0] for r in bounces]
    check(locations[0] == locations[1] == "/web/sign-in", f"the bounces go to {locations}")
    check(bounces[0].body == bounces[1].body, "the two bounces differ in body")
    ok("signed out: the code and a nonsense path both answer 303 to sign-in, same body")
    cookie = web.sign_in("uma")
    card = web.request("GET", scan(code), cookie=cookie)
    check(is_card(card), f"uma's scan of the label gave {card.status}, not a card")
    shown = parse_card(card)
    check(shown.key == key, f"the card key is {shown.key}, not {key}")
    check(shown.banner != "", "the card has no banner")
    check(bool(shown.as_of) and bool(shown.lines), "the card has no as-of or no lines")
    count = len(shown.lines)
    ok(f"signed in as uma: banner '{shown.banner}', key {shown.key}, as of {shown.as_of}, {count}")


def mode_visible(label: str) -> None:
    """Before a restriction: uma's scan of the label is a card; a later miss is the restriction."""
    web = Web()
    card = web.request("GET", scan(code_of(Path(label))), cookie=web.sign_in("uma"))
    check(is_card(card), f"before the restriction uma's scan gave {card.status}, not a card")
    ok(f"before the restriction uma's scan of the label shows the card of {parse_card(card).key}")


def mode_clause3(revoked: str, hidden: str) -> None:
    web = Web()
    cookie = web.sign_in("uma")
    paths = [
        ("malformed", scan(SHORT_CODE)),
        ("unknown", scan(new_code())),
        ("revoked", scan(code_of(Path(revoked)))),
        ("hidden", scan(code_of(Path(hidden)))),
    ]
    replies = []
    for kind, path in paths:
        reply = web.request("GET", path, cookie=cookie)
        check(reply.status == MISS_STATUS, f"the {kind} code gave {reply.status}, not 404")
        check(not is_card(reply), f"the {kind} code showed a card")
        replies.append(reply)
    first = replies[0].comparable()
    for (kind, _), reply in zip(paths, replies, strict=True):
        check(reply.comparable() == first, f"the {kind} miss differs from the malformed miss")
    ok("uma: malformed, unknown, revoked, hidden: one 404 page and headers (Date aside)")


def mode_clause4_hit(new_label: str, key: str) -> None:
    web = Web()
    cookie = web.sign_in("uma")
    card = web.request("GET", scan(code_of(Path(new_label))), cookie=cookie)
    check(is_card(card), f"the new code gave {card.status}, not a card")
    check(parse_card(card).key == key, "the new code's card is not for the record")
    ok(f"the new code resolves to the card of {key}")


def mode_clause4_misses(old_label: str) -> None:
    web = Web()
    cookie = web.sign_in("uma")
    statuses: list[int] = []
    old = web.request("GET", scan(code_of(Path(old_label))), cookie=cookie)
    statuses.append(old.status)
    for _ in range(9):
        statuses.append(web.request("GET", scan(new_code()), cookie=cookie).status)
    check(statuses == [MISS_STATUS] * 10, f"the first ten lookups gave {statuses}")
    eleventh = web.request("GET", scan(new_code()), cookie=cookie)
    check(eleventh.status == 429, f"the eleventh lookup gave {eleventh.status}, not 429")
    check(eleventh.header("retry-after") is not None, "the 429 carries no Retry-After")
    check(LIMITED.encode() in eleventh.body, "the 429 does not carry the limited text")
    ok("one session, eleven lookups: ten 404 (old code and nine nonsense), the eleventh 429")


def mode_clause5() -> None:
    if importlib.util.find_spec("tl_mod_scaffold") is not None:
        module = importlib.import_module("tl_mod_scaffold")
        check(
            not hasattr(module, "scan_card"), "the scaffold card exists: clause 5 is not deferred"
        )
    ok("tl_mod_scaffold has no scan_card: clause 5 is deferred")


def mode_clause6_agent(label: str, key: str) -> None:
    web = Web()
    token = os.environ["P2_QR_AGENT_TOKEN"]
    code = code_of(Path(label))
    page = web.request("GET", scan(code), bearer=token)
    check(page.status in (401, 403), f"the agent on the scan path gave {page.status}")
    check(not is_card(page), "the agent on the scan path showed a card")
    listing = web.request("GET", f"/qr/codes?project={PROJECT}&record={key}", bearer=token)
    check(listing.status == 403, f"the agent on /qr/codes gave {listing.status}, not 403")
    resolved = web.request("GET", f"/qr/resolve/{code}", bearer=token)
    check(resolved.status == 403, f"the agent on /qr/resolve gave {resolved.status}, not 403")
    for reply in (listing, resolved):
        check(
            code.encode() not in reply.body and key.encode() not in reply.body,
            "an agent answer names the record",
        )
    ok(f"agent token: scan path {page.status}, /qr/codes 403, /qr/resolve 403, no card, no record")
    cookie = web.sign_in("uma")
    miss = web.request("GET", scan(new_code()), cookie=cookie)
    check(
        miss.status == MISS_STATUS and b"Not found" in miss.body,
        "a signed-in person did not get the 404 miss",
    )
    ok("signed in as uma: a nonsense code gets the one 404 miss page")


def mode_export_eq(ls_path: str, export_path: str) -> None:
    lines = ls_lines(Path(ls_path))
    rows = [json.loads(line) for line in Path(export_path).read_text(encoding="utf-8").splitlines()]
    check(
        lines[:1] == [f"scan codes: {len(rows)}"],
        f"ls says {lines[:1]}, export has {len(rows)} rows",
    )
    expected = [
        f"{r['id']}  {cell(r['label_text'], 40)}  {r['size']}  {r['state']}  "
        f"{cell(r['issued_by'], 120)}  {cell(r['issued_at'])}  {cell(r['expires_on'])}"
        for r in rows
    ]
    check(lines[1:] == expected, "the ls rows differ from the export rows")
    check(len(rows) >= 2, "the export has fewer than two rows")
    ok(f"tl qr export jsonl: {len(rows)} rows equal the tl qr ls rows field by field")


def mode_card_compare(label: str, cli: str, banner: str | None) -> None:
    web = Web()
    cookie = web.sign_in("uma")
    card = web.request("GET", scan(code_of(Path(label))), cookie=cookie)
    check(is_card(card), f"uma's scan gave {card.status}, not a card")
    shown = parse_card(card)
    out = ls_lines(Path(cli))
    check(out[0] == shown.banner, f"CLI banner {out[0]!r} differs from the card {shown.banner!r}")
    check(out[1] == f"key  {shown.key}", "CLI key line differs from the card key")
    check(out[2] == shown.title, "CLI title differs from the card title")
    check(out[-1].startswith("as of "), "CLI has no as-of line last")
    check(
        out[3:-1] == [f"{a}  {b}" for a, b in shown.lines], "CLI lines differ from the card lines"
    )
    if banner is not None:
        check(shown.banner == banner, f"the card banner is {shown.banner!r}, not {banner!r}")
    for label_, value in shown.lines:
        if label_ == "Gas test":
            check(GAS_VALUE.fullmatch(value) is not None, f"the gas test line reads {value!r}")
    lines = len(shown.lines)
    ok(f"web card and tl qr resolve agree: banner '{shown.banner}', key {shown.key}, {lines} lines")


def mode_no_code(out: str, *labels: str) -> None:
    """The output holds no code of any of the label files (plain or grouped)."""
    text_ = Path(out).read_text(encoding="utf-8")
    for label in labels:
        plain = code_of(Path(label))
        grouped = GROUPED.search(Path(label).read_text(encoding="utf-8"))
        check(plain not in text_, "the output holds a code")
        check(
            grouped is not None and grouped.group(1) not in text_, "the output holds a grouped code"
        )
    ok(f"the output holds none of the {len(labels)} codes")


MODES: dict[str, tuple[Callable[..., None], int]] = {
    "platform": (mode_platform, 3),
    "label-check": (mode_label_check, 4),
    "clause2": (mode_clause2, 2),
    "visible": (mode_visible, 1),
    "clause3": (mode_clause3, 2),
    "clause4-hit": (mode_clause4_hit, 2),
    "clause4-misses": (mode_clause4_misses, 1),
    "clause5": (mode_clause5, 0),
    "clause6-agent": (mode_clause6_agent, 2),
    "export-eq": (mode_export_eq, 2),
    "card-compare": (mode_card_compare, -1),
    "no-code": (mode_no_code, -1),
}


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in MODES:
        fail(f"usage: p2_qr_demo.py {{{'|'.join(MODES)}}} ARGS")
    func, arity = MODES[argv[0]]
    args = argv[1:]
    if argv[0] == "no-code":
        check(len(args) >= 2, "no-code takes OUT LABEL...")
        mode_no_code(args[0], *args[1:])
    elif arity == -1:
        check(len(args) in (2, 3), "card-compare takes LABEL CLI [BANNER]")
        func(args[0], args[1], args[2] if len(args) == 3 else None)
    else:
        check(len(args) == arity, f"{argv[0]} takes {arity} arguments")
        func(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
