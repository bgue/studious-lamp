"""The scan page: five readers, one miss, the sign-in bounce, the headers, the limits (P2-QR-S3)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Connection, text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.qr import registry
from tl_core.qr.types import ScanCard, ScanCardProvider, ScanLine
from tl_core.services.commands import Command
from tl_core.services.records import create_module_record
from tl_core.settings import resolver
from tl_mod_qr import service
from tl_mod_qr.codes import code_hash
from tl_mod_qr.commands import IssueScanCode, RevokeScanCode
from tl_web import scan_limit
from tl_web.pages import scan

OPEN_TYPE = "quality.PunchItem"  # anyone signed in holds its word
WORD_TYPE = "engineering.Tag"  # its word is a controller's: a plain user lacks it
SECRET_TYPE = "correspondence.Correspondence"  # the hidden items of the seed
LINES = [ScanLine(label=f"L{n}", value=f"V{n}") for n in range(8)]
OWN_ORIGIN = "http://127.0.0.1"
BASE = "https://tl.example.com"
REAL_LOAD = registry.load_scan_cards
NOW = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
CSRF = re.compile(r'(name="csrf-token" content=")[^"]*|(name="csrf" value=")[^"]*')


class Fake:
    """A provider that answers a card for any record the viewer can read."""

    def __init__(self, record_type: str, view_word: str, **card: Any) -> None:
        self.record_type, self.view_word = record_type, view_word
        self.extra = card
        self.calls = 0

    def card(
        self, conn: Connection, record_id: str, viewer: cf.Viewer, now: datetime
    ) -> ScanCard | None:
        self.calls += 1
        if cf.is_hidden(conn, record_id, viewer):
            return None
        fields: dict[str, Any] = {
            "record_type": self.record_type, "key": "K-1", "title": "Fake title",
            "banner": "ACTIVE", "tone": "go", "as_of": now, "lines": LINES[:2],
        }  # fmt: skip
        return ScanCard(**{**fields, **self.extra})


class Setup:
    def __init__(self, world: Any, codes: dict[str, str], fakes: dict[str, Fake]) -> None:
        self.world, self.codes, self.fakes = world, codes, fakes
        self.webs: dict[str, Any] = {}

    def get(self, who: str | None, path: str, **kw: Any) -> Any:
        if who and who not in self.webs:
            self.webs[who] = self.world.web(who)
        client = self.webs[who].client if who else self.world.client()
        return client.get(path, **kw)


def issue(world: Any, target: str) -> str:
    cmd = IssueScanCode(actor="user:boss", source="test", scope="project:P123", target_id=target)
    with open_uow(world.target) as uow:
        with cf.use_viewer(cf.viewer_for_actor(uow.conn(), cmd.actor)):
            return service.issue(uow, cmd).code


def record(world: Any, record_type: str, key: str) -> str:
    cmd = Command(actor="user:boss", source="test", scope="project:P123")
    with open_uow(world.target) as uow:
        return create_module_record(uow, cmd, record_type=record_type, title=key, key=key).stream_id


@pytest.fixture(scope="module")
def setup(world: Any, monkeypatch_module: pytest.MonkeyPatch) -> Setup:
    fakes = {
        OPEN_TYPE: Fake(OPEN_TYPE, "quality.view"),
        WORD_TYPE: Fake(WORD_TYPE, "awp.cwp.release"),
        SECRET_TYPE: Fake(SECRET_TYPE, "quality.view"),
    }
    providers: dict[str, ScanCardProvider] = dict(fakes)
    monkeypatch_module.setattr(registry, "load_scan_cards", lambda *a, **k: providers)
    # ``api.public_base_url`` is a platform default only: stand in for the platform file
    real = resolver.value_of
    monkeypatch_module.setattr(
        service, "value_of",
        lambda conn, key, **kw: (
            BASE if key == service.BASE_URL else real(conn, key, **kw)
        ),
    )  # fmt: skip
    codes = {
        "open": issue(world, record(world, OPEN_TYPE, "T-1")),
        "word": issue(world, record(world, WORD_TYPE, "T-2")),
        "hidden": issue(world, world.ids["restricted"]),
    }
    providers["awp.IWP"] = Fake("awp.IWP", "quality.view")  # issue needs a provider ...
    codes["orphan"] = issue(world, record(world, "awp.IWP", "T-3"))
    del providers["awp.IWP"]  # ... the scan finds none
    return Setup(world, codes, fakes)


@pytest.fixture(autouse=True)
def fresh_counter(world: Any) -> Iterator[None]:
    world.app.state.scan_misses = scan_limit.MissCounter()
    yield
    world.app.state.scan_misses = scan_limit.MissCounter()


def path(code: str) -> str:
    return f"/web/q/{code}"


def blank(text: str) -> str:
    return CSRF.sub(lambda m: (m.group(1) or m.group(2)) + "X", text)


# --- the five readers -------------------------------------------------------------------------


def test_the_open_card_for_a_signed_in_user(setup: Setup) -> None:
    response = setup.get("bob", path(setup.codes["open"]))
    assert response.status_code == 200
    assert "ACTIVE" in response.text and "K-1" in response.text and "Fake title" in response.text
    assert "L0" in response.text and "V1" in response.text
    assert re.search(r"as of \d{4}-\d\d-\d\d \d\d:\d\d UTC", response.text)
    assert "tl-tone-go" in response.text
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers


def test_typed_and_lower_case_codes_reach_the_same_card(setup: Setup) -> None:
    code = setup.codes["open"]
    me = setup.world.web("bob")
    typed = me.client.post(
        "/web/q", data={"code": f"{code[:4]}-{code[4:8].lower()} {code[8:]}"},
        headers={"Origin": setup.world.client().base_url.__str__().rstrip("/")},
    )  # fmt: skip
    assert typed.status_code == 303 and typed.headers["location"] == path(code)
    assert "?" not in typed.headers["location"]
    assert me.client.get(path(code.lower())).status_code == 200


def test_five_readers_one_card_or_the_one_miss(setup: Setup) -> None:
    c = setup.codes
    # (reader, code) -> whether a card is shown
    table: list[tuple[str, str, bool]] = [
        ("bob", "open", True), ("ctl", "open", True), ("boss", "open", True),
        ("bob", "hidden", False),  # a plain user: hidden is missing
        ("ctl", "hidden", True),  # the cleared reader reads it
        ("bob", "word", False),  # a user without the view word
        ("boss", "word", True),
        ("bob", "orphan", False), ("boss", "orphan", False),  # no provider
    ]  # fmt: skip
    misses: dict[str, list[tuple[int, bytes, dict[str, str]]]] = {}
    for reader, kind, shown in table:
        response = setup.get(reader, path(c[kind]))
        assert (response.status_code == 200) is shown, (reader, kind)
        if not shown:
            assert response.status_code == 404
            misses.setdefault(reader, []).append(
                (response.status_code, response.content, dict(response.headers))
            )
    # a malformed, an unknown, a revoked and an expired code are the same miss for the same reader
    for reader in ("bob", "boss"):
        for odd in ("short", "I" * 16, "ZZZZZZZZZZZZZZZZ", c["open"][:-1] + "!"):
            response = setup.get(reader, path(odd))
            misses[reader].append((response.status_code, response.content, dict(response.headers)))
    for reader, seen in misses.items():
        assert len(seen) >= 4
        assert all(item == seen[0] for item in seen), reader
    # across readers the miss differs only by the session's own CSRF token
    bob, boss = misses["bob"][0], misses["boss"][0]
    assert blank(bob[1].decode()) == blank(boss[1].decode())
    assert bob[0] == boss[0] and bob[2] == boss[2]
    assert b"nothing at this address" in bob[1]


def test_revoked_and_expired_codes_are_the_same_miss(setup: Setup) -> None:
    world = setup.world
    revoked = issue(world, record(world, OPEN_TYPE, "T-REV"))
    expired = issue(world, record(world, OPEN_TYPE, "T-EXP"))
    with open_uow(world.target) as uow:
        row = uow.conn().execute(text("SELECT id, code_hash FROM cur_qr_scan_code")).all()
    ids = {r.code_hash: r.id for r in row}
    cmd = RevokeScanCode(
        actor="user:boss", source="test", scope="project:P123",
        code_id=ids[code_hash(revoked)], reason="lost",
    )  # fmt: skip
    with open_uow(world.target) as uow:
        with cf.use_viewer(cf.viewer_for_actor(uow.conn(), cmd.actor)):
            service.revoke(uow, cmd)
    with open_uow(world.target) as uow:
        uow.conn().execute(
            text("UPDATE cur_qr_scan_code SET expires_on = :d WHERE id = :i"),
            {
                "d": (datetime.now(UTC).date() - timedelta(days=2)).isoformat(),
                "i": ids[code_hash(expired)],
            },
        )
    me = world.web("bob")
    a = me.client.get(path(revoked))
    b = me.client.get(path(expired))
    c = me.client.get(path("ZZZZZZZZZZZZZZZZ"))
    assert a.status_code == b.status_code == c.status_code == 404
    assert a.content == b.content == c.content and dict(a.headers) == dict(b.headers)


def test_an_agent_token_gets_no_card_and_no_lookup(setup: Setup) -> None:
    bot = setup.world.web("bot")
    before = setup.fakes[OPEN_TYPE].calls
    for url in (path(setup.codes["open"]), path("ZZZZZZZZZZZZZZZZ"), "/web/q"):
        response = bot.client.get(url)
        assert response.status_code in (401, 403), url
        assert "ACTIVE" not in response.text and "tl-scan" not in response.text
    bearer = setup.world.client(bearer=setup.world.agent_token)
    assert bearer.get(path(setup.codes["open"])).status_code in (401, 403)
    assert setup.fakes[OPEN_TYPE].calls == before


# --- signed out -------------------------------------------------------------------------------


def test_signed_out_answers_the_sign_in_page_before_any_lookup(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = setup.world
    resolver_calls: list[str] = []
    backend_calls: list[str] = []
    ctx = world.app.state.ctx
    real_backend = ctx.backend

    def counting_backend(*args: Any, **kwargs: Any) -> Any:
        backend_calls.append("open")
        return real_backend(*args, **kwargs)

    monkeypatch.setattr(scan, "resolve", lambda *a, **k: resolver_calls.append("resolve"))
    monkeypatch.setattr(ctx, "backend", counting_backend)
    segments = [
        setup.codes["open"], setup.codes["open"].lower(), "ZZZZZZZZZZZZZZZZ", "short", "..x",
        "ABCDEFGH23456789", "x" * 300, "%C4%B1" * 16, "a b",
    ]  # fmt: skip
    pages: list[tuple[int, str, dict[str, str]]] = []
    client = world.client()
    for segment in segments:
        first = client.get(path(segment))
        assert first.status_code == 303, segment
        assert first.headers["referrer-policy"] == "no-referrer"
        assert first.headers["cache-control"] == "no-store" and "set-cookie" not in first.headers
        page = client.get(first.headers["location"])
        assert page.status_code == 200 and "Sign in" in page.text
        pages.append((page.status_code, page.text, dict(page.headers)))
    assert resolver_calls == [] and backend_calls == []
    # the answers differ only by the ``next`` the visitor typed itself
    nexts = [re.findall(r'name="next" value="([^"]*)"', text) for _, text, _ in pages]
    assert nexts[0] == [path(setup.codes["open"])] and nexts[1] == nexts[0]  # upper-cased
    assert nexts[5] == [path("ABCDEFGH23456789")]
    assert nexts[2] == [path("ZZZZZZZZZZZZZZZZ")]  # well formed: echoed whether or not it exists
    assert [nexts[i] for i in (3, 4, 6, 7, 8)] == [[]] * 5  # malformed: nothing is echoed
    base = re.sub(r'<input type="hidden" name="next" value="[^"]*">\n', "", pages[0][1])
    for _, body, headers in pages:
        assert re.sub(r'<input type="hidden" name="next" value="[^"]*">\n', "", body) == base
        quiet = {"content-length": "", "referrer-policy": ""}
        assert headers | quiet == pages[0][2] | quiet
    for (_, _body, headers), found in zip(pages, nexts, strict=True):
        # a sign-in page that echoes a next sends strict-origin; the others keep the app's policy
        assert headers["referrer-policy"] == ("strict-origin" if found else "same-origin")


def test_the_bounce_of_an_existing_and_a_missing_code_differ_only_by_next(setup: Setup) -> None:
    client = setup.world.client()
    a = client.get(path(setup.codes["open"]))
    b = client.get(path("ZZZZZZZZZZZZZZZZ"))
    assert a.status_code == b.status_code == 303 and a.content == b.content
    assert a.headers["location"].split("?")[0] == b.headers["location"].split("?")[0]
    assert dict(a.headers) | {"location": ""} == dict(b.headers) | {"location": ""}


def test_sign_in_returns_to_the_card(setup: Setup) -> None:
    code = setup.codes["open"]
    client = setup.world.client()
    bounce = client.get(path(code.lower()))
    form = client.get(bounce.headers["location"])
    assert f'name="next" value="{path(code)}"' in form.text
    done = client.post(
        "/web/sign-in",
        data={"username": "bob", "password": "correct horse battery", "next": path(code)},
        headers={"Origin": "http://127.0.0.1"},
    )
    assert done.status_code == 303 and done.headers["location"] == path(code)


# --- the form, the headers, the card ----------------------------------------------------------


def test_the_form_and_a_typed_malformed_code(setup: Setup) -> None:
    me = setup.world.web("bob")
    form = me.client.get("/web/q")
    assert form.status_code == 200 and 'action="/web/q"' in form.text
    assert form.headers["referrer-policy"] == "strict-origin"  # it hosts a form
    bad = me.client.post("/web/q", data={"code": "nope"}, headers={"Origin": "http://127.0.0.1"})
    miss = me.client.get(path("ZZZZZZZZZZZZZZZZ"))
    assert bad.status_code == 404 and bad.content == miss.content
    refused = me.client.post("/web/q", data={"code": setup.codes["open"]})
    assert refused.status_code == 403  # no origin: no redirect


def test_every_scan_answer_has_no_referrer_and_other_pages_keep_the_app_policy(
    setup: Setup,
) -> None:
    me = setup.world.web("bob")
    assert me.client.get("/web/q").headers["referrer-policy"] == "strict-origin"
    for url in (path(setup.codes["open"]), path("ZZZZZZZZZZZZZZZZ"), "/web/q/x/y"):
        assert me.client.get(url).headers["referrer-policy"] == "no-referrer", url
    assert me.client.get("/web/sign-in").headers["referrer-policy"] == "same-origin"
    assert me.client.get("/web/qx").headers["referrer-policy"] == "same-origin"
    assert me.client.get("/web/p/P123/rfis").headers["referrer-policy"] == "same-origin"


def test_the_card_is_small_has_no_script_and_escapes_its_text(setup: Setup, htmlkit: Any) -> None:
    fake = setup.fakes[OPEN_TYPE]
    planted = '<script>alert(1)</script><i>x</i> & "q"'
    fake.extra = {
        "title": planted, "banner": "<b>STOP</b>", "tone": "stop", "key": "<K>",
        "lines": [ScanLine(label="<l>", value=planted)] * 8,
        "valid_until": datetime(2026, 12, 1, 18, 0, tzinfo=UTC),
        "open_path": "/web/p/P123/rfis",
    }  # fmt: skip
    try:
        response = setup.get("bob", path(setup.codes["open"]))
    finally:
        fake.extra = {}
    text = response.text
    assert response.status_code == 200 and len(response.content) < 30 * 1024
    assert "<script" not in text.lower() and "<i>" not in text and "<b>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text and "&lt;b&gt;STOP&lt;/b&gt;" in text
    assert "tl-tone-stop" in text and "valid until 2026-12-01 18:00 UTC" in text
    assert 'href="/web/p/P123/rfis"' in text and "Open record" in text
    assert text.count("<dt>") == 8
    assert not htmlkit.parse(text).inline_problems()
    assert "http://" not in text.replace("http://www.w3.org", "") and "https://" not in text


def test_no_open_link_without_an_open_path(setup: Setup) -> None:
    assert "Open record" not in setup.get("bob", path(setup.codes["open"])).text


# --- the limits -------------------------------------------------------------------------------


def test_a_session_past_its_limit_gets_429_for_hits_and_misses_alike(setup: Setup) -> None:
    me = setup.world.web("bob")
    for _ in range(scan_limit.MISS_LIMIT_SESSION):
        assert me.client.get(path("ZZZZZZZZZZZZZZZZ")).status_code == 404
    hit = me.client.get(path(setup.codes["open"]))
    miss = me.client.get(path("YYYYYYYYYYYYYYYY"))
    typed = me.client.post(
        "/web/q", data={"code": setup.codes["open"]}, headers={"Origin": "http://127.0.0.1"}
    )
    for response in (hit, miss, typed):
        assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
        assert response.headers["referrer-policy"] == "no-referrer"
        assert scan.LIMITED_TEXT in response.text and "ACTIVE" not in response.text
    assert hit.content == miss.content == typed.content
    # another session of another person from the same address is not limited by this one
    other = setup.world.web("ctl")
    assert other.client.get(path(setup.codes["open"])).status_code == 200


def test_a_hit_below_the_limit_does_not_reset_the_count(setup: Setup) -> None:
    me = setup.world.web("bob")
    for _ in range(scan_limit.MISS_LIMIT_SESSION - 1):
        me.client.get(path("ZZZZZZZZZZZZZZZZ"))
        assert me.client.get(path(setup.codes["open"])).status_code == 200  # hits in between
    assert me.client.get(path("ZZZZZZZZZZZZZZZZ")).status_code == 404  # the tenth miss
    assert me.client.get(path(setup.codes["open"])).status_code == 429


def test_an_address_past_its_limit_is_refused_for_every_session(setup: Setup) -> None:
    setup.world.app.state.scan_misses = scan_limit.MissCounter(session_limit=100, address_limit=3)
    for name in ("bob", "ctl", "boss"):
        assert setup.world.web(name).client.get(path("ZZZZZZZZZZZZZZZZ")).status_code == 404
    fresh = setup.world.web("amy")
    assert fresh.client.get(path(setup.codes["open"])).status_code == 429


def test_the_counter_never_sees_a_token_or_a_code(setup: Setup) -> None:
    me = setup.world.web("bob")
    me.client.get(path("ZZZZZZZZZZZZZZZZ"))
    seen = setup.world.app.state.scan_misses._seen  # pyright: ignore[reportPrivateUsage]
    assert seen and all(me.token not in key and "ZZZZ" not in key for key in seen)


def test_the_real_iwp_provider_reads_through_the_registry(setup: Setup) -> None:
    try:
        providers = REAL_LOAD()
    except registry.ScanCardLoadError:
        pytest.skip("provider entry points not installed")
    if "awp.IWP" not in providers:
        pytest.skip("awp.IWP provider not installed")
    provider = providers["awp.IWP"]
    with open_uow(setup.world.target, readonly=True) as uow:
        assert provider.card(uow.conn(), "01J000000000000000000000", cf.LOWEST, NOW) is None


FORM = re.compile(r'<form[^>]*method="post"[^>]*action="([^"]*)"', re.IGNORECASE)


def test_no_page_that_hosts_a_post_form_sends_no_referrer(setup: Setup) -> None:
    """Under ``no-referrer`` a browser's form POST carries ``Origin: null`` and the origin check
    refuses it: every page with a POST form must send a policy that keeps the real ``Origin``, and
    a POST with the Origin a browser would send from that page must pass the origin check."""
    world = setup.world
    world.app.state.scan_misses = scan_limit.MissCounter(session_limit=1)
    me = world.web("bob")
    me.client.get(path("ZZZZZZZZZZZZZZZZ"))  # one miss: the next lookup is the 429 page
    pages = {
        "form": me.client.get("/web/q"),
        "card": me.client.get(path(setup.codes["open"])),  # 429 now: the limited page
        "sign-in": world.client().get("/web/sign-in"),
        "sign-in next": world.client().get("/web/sign-in", params={"next": path("A" * 16)}),
        "log": me.client.get("/web/p/P123/rfis"),
    }
    world.app.state.scan_misses = scan_limit.MissCounter()
    pages["card ok"] = me.client.get(path(setup.codes["open"]))
    pages["miss"] = me.client.get(path("ZZZZZZZZZZZZZZZZ"))
    seen: set[str] = set()
    for name, response in pages.items():
        policy = response.headers["referrer-policy"]
        forms = FORM.findall(response.text)
        seen.update(forms)
        if forms:
            assert policy != "no-referrer", (name, forms)
        browser_origin = "null" if policy == "no-referrer" else OWN_ORIGIN
        for action in forms:
            data = {"username": "bob", "password": "correct horse battery", "code": "x"}
            data["csrf"] = me.csrf
            sent = me.client.post(action, data=data, headers={"Origin": browser_origin})
            assert sent.status_code != 403, (name, action, sent.status_code)
    assert {"/web/q", "/web/sign-in", "/web/sign-out"} <= seen
    for name in ("card", "card ok", "miss"):
        assert not FORM.findall(pages[name].text), name  # a no-referrer page hosts no form
        assert pages[name].headers["referrer-policy"] == "no-referrer"
