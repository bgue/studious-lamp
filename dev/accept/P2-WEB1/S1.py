"""Acceptance script for P2-WEB1 S1: the web foundation (cookie session, CSRF, headers, vendoring).

Runs on SQLite with a temp ledger and the FastAPI TestClient under ``TL_ENV=test``. Prints one
``PASS <check>`` line per check; exits 0 when every check passes, 1 on the first failure. Expected
values come from the spec text (``docs/build-spec/specs/web-client-i1.md`` sections 4 and 5 and the
S1 ticket), never from the code under test: the CSP string and the CSRF formula are written out
again here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import importlib.util
import os
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from unittest import mock

os.environ["TL_ENV"] = "test"
SECRET = "web-secret-for-acceptance-0123456789abcdef"  # 41 bytes
os.environ["TL_WEB_SECRET"] = SECRET
for _name in ("TL_WEB", "TL_WEB_ORIGIN", "TL_PROJECT"):
    os.environ.pop(_name, None)

from fastapi.testclient import TestClient  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.responses import Response  # noqa: E402
from starlette.routing import Route  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import create_schema  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.ratelimit import SourceLimiter  # noqa: E402
from tl_api.settings import ApiSettings, web_enabled  # noqa: E402
from tl_api.tokens import TokenStore, add_token  # noqa: E402
from tl_core.auth import accounts  # noqa: E402
from tl_core.auth.password import prepare_password  # noqa: E402
from tl_web.app import WebHeadersMiddleware  # noqa: E402
from tl_web.session import cookie_flags  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
VENDOR = ROOT / "packages" / "tl-web" / "src" / "tl_web" / "static" / "vendor"
PASSWORD = "correct horse battery"
WRONG = "wrong-password-SENTINEL-4711"
OWN = "http://127.0.0.1"
#: The policy of the spec (section 5), written out again.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)


def passed(check: str) -> None:
    print(f"PASS {check}")


def expect(condition: bool, what: str) -> None:
    if not condition:
        raise AssertionError(what)


@contextmanager
def env(**changes: str | None) -> Iterator[None]:
    """Set (or, with ``None``, unset) environment variables for the block."""
    saved = {k: os.environ.get(k) for k in changes}
    for key, value in changes.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def expected_csrf(session_token: str, secret: str = SECRET) -> str:
    """base64url(HMAC-SHA256(secret, "csrf|" + sha256(session_token))), no padding (spec 5)."""
    message = b"csrf|" + hashlib.sha256(session_token.encode()).hexdigest().encode()
    mac = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


class Page(HTMLParser):
    """Tags and attributes of one page, for the no-inline-script and no-inline-style rule."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    def inline_problems(self) -> list[str]:
        found: list[str] = []
        for tag, attrs in self.tags:
            if tag == "script" and "src" not in attrs:
                found.append("script without src")
            if tag == "style":
                found.append("style element")
            found.extend(f"{tag}[{a}]" for a in attrs if a == "style" or a.startswith("on"))
        return found

    def meta(self, name: str) -> str | None:
        for tag, attrs in self.tags:
            if tag == "meta" and attrs.get("name") == name:
                return attrs.get("content")
        return None


class World:
    def __init__(self, work: Path) -> None:
        self.db = work / "ledger.db"
        create_schema(self.db)
        self.backend = open_backend(self.db)
        self.tokens_path = work / "tokens.json"
        self.settings = ApiSettings(db_path=self.db, tokens_path=self.tokens_path)
        self.tokens = TokenStore(self.tokens_path)
        with self.backend() as uow:
            accounts.create_account(
                uow, username="alice", display_name="Alice", kind="person", roles=["user"],
                password=prepare_password(PASSWORD, username="alice"), by="svc:accept",
            )  # fmt: skip
        self.agent_token = add_token(self.tokens_path, "agent:bot")
        self.app = self.make_app()

    def make_app(self) -> Any:
        return create_app(
            self.backend,
            settings=self.settings,
            tokens=TokenStore(self.tokens_path),
            source_limiter=SourceLimiter(10_000),  # no check here trips the per-source limit
        )

    def client(self, cookie: str | None = None, app: Any = None) -> TestClient:
        client = TestClient(
            app or self.app, base_url=OWN, follow_redirects=False, raise_server_exceptions=True
        )
        if cookie is not None:
            client.headers["Cookie"] = f"tl_session={cookie}"
        return client

    def sign_in(self, password: str = PASSWORD, username: str = "alice") -> tuple[Any, str]:
        """``(response, token)``; the token is read from the Set-Cookie header, '' when none."""
        response = self.client().post(
            "/web/sign-in", data={"username": username, "password": password}
        )
        raw = response.headers.get("set-cookie", "")
        return response, raw.split(";")[0].partition("=")[2]

    def session(self) -> str:
        response, token = self.sign_in()
        expect(response.status_code == 303 and bool(token), "sign-in did not give a session")
        return token


def cookie_attrs(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(";")[1:]}


def sign_out(world: World, token: str, *, headers: dict[str, str], **form: str) -> Any:
    return world.client(token).post("/web/sign-out", data=form or None, headers=headers)


# --- the checks ----------------------------------------------------------------------------------


def check_sign_in(world: World) -> None:
    response, token = world.sign_in()
    expect(response.status_code == 303, f"sign-in status {response.status_code}")
    expect(response.headers["location"] == "/web/", "sign-in redirect is not /web/")
    attrs = cookie_attrs(response.headers["set-cookie"])
    expect({"HttpOnly", "SameSite=Strict", "Path=/web", "Max-Age=43200"} <= attrs, str(attrs))
    expect("Secure" not in attrs, "Secure on loopback in test")
    expect(token not in response.text, "token in the body")
    again, token2 = world.sign_in()
    expect(token2 != token and bool(token2), "the token is not new at every sign-in")
    expect("Secure" in cookie_flags("203.0.113.5", "test"), "no Secure for a public host")
    expect("Secure" in cookie_flags("localhost", "prod"), "no Secure for loopback in prod")
    expect("Secure" in cookie_flags("127.0.0.1", ""), "no Secure for an unset environment")
    for host, name in (("127.0.0.1", "dev"), ("localhost", "test"), ("::1", "ci")):
        expect("Secure" not in cookie_flags(host, name), f"Secure for {host} in {name}")
    for host in ("127.0.0.1", "example.com"):
        expect(
            {"HttpOnly", "SameSite=Strict", "Path=/web"} <= set(cookie_flags(host, "prod")), host
        )
    elsewhere = TestClient(world.app, base_url="http://tl.example.com", follow_redirects=False)
    moved = elsewhere.post("/web/sign-in", data={"username": "alice", "password": PASSWORD})
    expect("Secure" in cookie_attrs(moved.headers["set-cookie"]), "no Secure on a public host")
    passed("a: sign-in is a 303 to /web/ with an HttpOnly SameSite=Strict Path=/web cookie")


def check_wrong_password(world: World) -> None:
    api = world.client()
    for username in ("alice", "nobody"):
        expected = api.post("/auth/sign-in", json={"username": username, "password": WRONG})
        response = world.client().post(
            "/web/sign-in", data={"username": username, "password": WRONG}
        )
        expect(response.status_code == expected.status_code == 401, f"{response.status_code}")
        message = expected.json()["message"]
        expect(message in html.unescape(response.text), "the JSON error text is not shown")
        expect("set-cookie" not in response.headers, "a cookie on a failed sign-in")
        everything = response.text + str(dict(response.headers))
        expect(WRONG not in everything, "the password is echoed")
        expect(f'value="{username}"' in response.text, "the username is not re-shown")
    evil = "<script>alert(1)</script>"
    response = world.client().post("/web/sign-in", data={"username": evil, "password": WRONG})
    expect(response.status_code == 401, "status for a hostile username")
    expect("&lt;script&gt;" in response.text, "the username is not escaped")
    expect(evil not in response.text, "the username is echoed raw")
    empty = world.client().post("/web/sign-in", data={"username": "", "password": WRONG})
    json_empty = api.post("/auth/sign-in", json={"username": "", "password": WRONG})
    expect(empty.status_code == json_empty.status_code == 422, f"{empty.status_code}")
    # the lockout is the JSON route's: lock a name there, the web form then shows the same answer
    locked = None
    for _ in range(30):
        locked = api.post("/auth/sign-in", json={"username": "alice", "password": WRONG})
        if locked.status_code == 423:
            break
    expect(locked is not None and locked.status_code == 423, "alice was never locked")
    web = world.client().post("/web/sign-in", data={"username": "alice", "password": PASSWORD})
    expect(web.status_code == 423, f"locked name on the web: {web.status_code}")
    expect(locked.json()["message"] in html.unescape(web.text), "the lock text differs")
    passed("b: a failed sign-in answers as the JSON route does; password absent; username escaped")


def check_cookie_only_on_web(world: World, token: str) -> None:
    cookie, bearer = world.client(token), {"Authorization": f"Bearer {token}"}
    expect(cookie.get("/events").status_code == 401, "cookie accepted by GET /events")
    expect(cookie.get("/auth/me").status_code == 401, "cookie accepted by GET /auth/me")
    expect(
        cookie.post("/commands/PostToFeed", json={}).status_code == 401,
        "cookie accepted by POST /commands",
    )
    expect(world.client().get("/events", headers=bearer).status_code == 200, "bearer refused")
    expect(
        world.client().post("/commands/PostToFeed", json={}, headers=bearer).status_code != 401,
        "bearer refused on a command",
    )
    for path in ("/webx/", "/webx/sign-in", "/web", "/webs/p/P1"):
        response = cookie.get(path)
        expect(response.status_code == 401, f"cookie read on {path}: {response.status_code}")
        if path != "/web":  # "/web" itself is under /web: it has the headers, never the cookie
            expect(
                "content-security-policy" not in response.headers,
                f"web headers on look-alike {path}",
            )
    expect(cookie.get("/web/nowhere").status_code == 404, "the cookie does not work on /web/")
    passed("c: the cookie authenticates /web/ only; the JSON API and look-alikes stay bearer-only")


def check_unauthenticated(world: World, token: str) -> None:
    anon = world.client()
    response = anon.get("/web/")
    expect(response.status_code == 303, f"GET /web/ unauthenticated: {response.status_code}")
    expect(response.headers["location"] == "/web/sign-in", "redirect target")
    expect(anon.get("/web/p/P1/rfis").status_code == 303, "deep GET not redirected")
    out = anon.post("/web/sign-out")
    expect(out.status_code == 401, f"POST /web/sign-out unauthenticated: {out.status_code}")
    expect(out.json()["error"] == "unauthorized", "401 body")
    expect(world.client("junk").get("/web/").status_code == 303, "unknown cookie, GET")
    expect(world.client("junk").post("/web/sign-out").status_code == 401, "unknown cookie, POST")
    expect(anon.get("/web/sign-in").status_code == 200, "sign-in is open")
    expect(anon.get("/web/static/tl.css").status_code == 200, "static is open")
    agent = world.agent_token
    expect(world.client(agent).get("/web/").status_code == 401, "agent cookie, GET /web/")
    expect(world.client(agent).get("/web/nowhere").status_code == 401, "agent cookie, deep GET")
    expect(world.client(agent).post("/web/sign-out").status_code == 401, "agent cookie, POST")
    agent_bearer = {"Authorization": f"Bearer {agent}"}
    expect(anon.get("/web/", headers=agent_bearer).status_code == 401, "agent bearer on /web/")
    # a header wins over the cookie: the cookie is not read when Authorization is present
    mixed = world.client(token).get("/web/", headers={"Authorization": "Bearer junk"})
    expect(mixed.status_code == 303, f"cookie read despite an Authorization header: {mixed}")
    passed("d: unauthenticated GET /web/ is 303, POST is 401; an agent token in the cookie is 401")


def check_home(world: World, token: str) -> None:
    user = world.client(token)
    expect(user.get("/web/").status_code == 404, "no TL_PROJECT: not a 404 page")
    with env(TL_PROJECT="P123"):
        response = user.get("/web/")
        expect(response.status_code == 303, f"home with a project: {response.status_code}")
        expect(response.headers["location"] == "/web/p/P123/rfis", "home target")
    with env(TL_PROJECT="P1/../x\r\nSet-Cookie: a=b"):
        expect(user.get("/web/").status_code == 404, "a hostile TL_PROJECT is not refused")
    page = user.get("/web/p/P123/rfis")
    expect(page.status_code == 404 and "Not found" in page.text, "the log page is a 404 for now")
    passed("d2: GET /web/ goes to the RFI log of TL_PROJECT; unset or odd is the 404 page")


def check_csrf(world: World) -> None:
    api = world.client()
    token, other = world.session(), world.session()
    right = expected_csrf(token)
    own = {"Origin": OWN}
    page = world.client(token).get("/web/nowhere")
    parsed = Page(page.text)
    expect(parsed.meta("csrf-token") == right, "the csrf-token meta is not the spec's value")
    expect(any(a.get("name") == "csrf" and a.get("value") == right for _, a in parsed.tags),
           "the sign-out form has no hidden csrf field")  # fmt: skip

    def refused(response: Any, what: str) -> None:
        expect(response.status_code == 403, f"{what}: {response.status_code}")
        expect(response.json()["error"] == "csrf_refused", f"{what}: {response.text}")

    refused(sign_out(world, token, headers=own), "no token")
    refused(sign_out(world, token, headers=own, csrf="nope"), "wrong form token")
    refused(sign_out(world, token, headers={**own, "X-CSRF-Token": "nope"}), "wrong header token")
    refused(sign_out(world, token, headers=own, csrf=expected_csrf(other)), "another session")
    refused(sign_out(world, token, headers={**own, "X-CSRF-Token": expected_csrf(other)}), "other")
    refused(sign_out(world, token, headers={"Origin": "http://evil.example"}, csrf=right), "origin")
    refused(sign_out(world, token, headers={"Origin": "null"}, csrf=right), "null origin")
    refused(sign_out(world, token, headers={}, csrf=right), "no Origin and no Referer")
    refused(sign_out(world, token, headers={"Referer": "http://evil.example/web/"}, csrf=right),
            "foreign Referer")  # fmt: skip
    refused(sign_out(world, token, headers={"Origin": "http://127.0.0.1:9"}, csrf=right), "port")
    expect(api.get("/events", headers={"Authorization": f"Bearer {token}"}).status_code == 200,
           "a refused request ended the session")  # fmt: skip
    expect(
        sign_out(world, token, headers=own, csrf=right.rstrip("=") + "x").status_code == 403,
        "a changed token passes",
    )
    # TL_WEB_ORIGIN replaces the request's own origin
    with env(TL_WEB_ORIGIN="https://tl.example.com/"):
        refused(sign_out(world, token, headers=own, csrf=right), "own origin under TL_WEB_ORIGIN")
        response = sign_out(
            world, other, headers={"Origin": "https://tl.example.com"}, csrf=expected_csrf(other)
        )
        expect(response.status_code == 303, f"TL_WEB_ORIGIN not honoured: {response.status_code}")
    # Referer is accepted when Origin is absent
    response = sign_out(world, token, headers={"Referer": f"{OWN}/web/anything?x=1"}, csrf=right)
    expect(response.status_code == 303, f"Referer refused: {response.status_code}")
    third = world.session()
    response = sign_out(world, third, headers={**own, "X-CSRF-Token": expected_csrf(third)})
    expect(response.status_code == 303, f"header token refused: {response.status_code}")
    fourth = world.session()
    response = sign_out(world, fourth, headers=own, csrf=expected_csrf(fourth))
    expect(response.status_code == 303, f"right token and own origin: {response.status_code}")
    expect(response.headers["location"] == "/web/sign-in", "sign-out redirect")
    # the catch-all answers an unsafe method only after the CSRF check (pin 5: every non-GET route)
    live = world.session()
    live_csrf = expected_csrf(live)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        refused(
            world.client(live).request(method, "/web/nowhere", headers=own),
            f"{method} to an unknown /web path with no token",
        )
        response = world.client(live).request(
            method, "/web/nowhere", headers={**own, "X-CSRF-Token": live_csrf}
        )
        expect(response.status_code == 404, f"{method} with a token: {response.status_code}")
    passed(
        "e: CSRF token, origin and Referer checked on POST /web/sign-out; TL_WEB_ORIGIN honoured"
    )


def check_config(world: World) -> None:
    short = "short-secret"
    for name, kind in (("prod", "short"), ("prod", "none"), ("test", "short")):
        with env(TL_ENV=name, TL_WEB="on", TL_WEB_SECRET=short if kind == "short" else None):
            try:
                world.make_app()
            except RuntimeError as exc:
                expect(short not in str(exc), "the secret is in the error text")
            else:
                raise AssertionError(f"start-up allowed a {kind} secret in {name}")
    with env(TL_ENV="prod", TL_WEB="on", TL_WEB_SECRET=SECRET):
        world.make_app()  # a long secret in prod starts
    with env(TL_ENV="dev", TL_WEB_SECRET=None):
        generated = world.make_app()
        expect(world.client(app=generated).get("/web/sign-in").status_code == 200, "dev, no secret")
    for name in ("dev", "test", "ci"):
        expect(web_enabled({"TL_ENV": name}) is True, f"TL_WEB unset is not on in {name}")
    for name in ("prod", "staging", ""):
        expect(web_enabled({"TL_ENV": name}) is False, f"TL_WEB unset is on in {name!r}")
    expect(web_enabled({}) is False, "TL_WEB and TL_ENV unset is on")
    expect(web_enabled({"TL_ENV": "test", "TL_WEB": "off"}) is False, "TL_WEB=off ignored")
    expect(web_enabled({"TL_ENV": "prod", "TL_WEB": "on"}) is True, "TL_WEB=on ignored")
    try:
        web_enabled({"TL_ENV": "test", "TL_WEB": "maybe"})
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown TL_WEB value was accepted")
    token = world.session()
    bearer = {"Authorization": f"Bearer {token}"}
    with env(TL_ENV="prod", TL_WEB=None):  # off by default outside dev, test and ci
        app = world.make_app()
        expect(world.client(app=app).get("/web/sign-in", headers=bearer).status_code == 404, "prod")
    with env(TL_WEB="off"):
        app = world.make_app()
        for who in (world.client(app=app), world.client(token, app=app)):
            expect(who.get("/web/", headers=bearer).status_code == 404, "TL_WEB=off, /web/")
        expect(world.client(token, app=app).get("/web/").status_code == 401, "cookie read when off")
        expect(world.client(app=app).get("/web/").status_code == 401, "off: not a plain 401")
    real = importlib.util.find_spec

    def without_web(name: str, *args: Any) -> Any:
        return None if name == "tl_web" else real(name, *args)

    with mock.patch("importlib.util.find_spec", without_web):
        with env(TL_WEB="on"):
            try:
                world.make_app()
            except RuntimeError:
                pass
            else:
                raise AssertionError("TL_WEB=on with tl_web missing started")
        with env(TL_WEB=None):
            app = world.make_app()  # silent
            expect(world.client(app=app).get("/web/", headers=bearer).status_code == 404, "silent")
    passed("f: short or missing secret stops start-up outside dev; TL_WEB switch and 404 when off")


def check_headers(world: World, token: str) -> None:
    other = world.session()
    own = {"Origin": OWN}
    answers = {
        "200": world.client().get("/web/sign-in"),
        "303": world.client().get("/web/"),
        "401": world.client().post("/web/sign-out"),
        "403": sign_out(world, other, headers=own),
        "404": world.client(token).get("/web/nowhere"),
        "static": world.client().get("/web/static/tl.css"),
        "static 404": world.client().get("/web/static/none.css"),
        "413": world.client().post(
            "/web/sign-in", data={"username": "a", "password": "p" * 20_000}
        ),
        "sign-in 401": world.client().post(
            "/web/sign-in", data={"username": "alice", "password": WRONG}
        ),
        "sign-in 303": world.client().post(
            "/web/sign-in", data={"username": "alice", "password": PASSWORD}
        ),
    }
    wanted = {"200": 200, "303": 303, "401": 401, "403": 403, "404": 404, "static": 200,
              "static 404": 404, "413": 413, "sign-in 401": 401, "sign-in 303": 303}  # fmt: skip
    for name, response in answers.items():
        expect(response.status_code == wanted[name], f"{name}: status {response.status_code}")
        got = response.headers.get("content-security-policy")
        expect(got == CSP, f"{name}: CSP {got!r}")
        expect(response.headers.get("x-content-type-options") == "nosniff", f"{name}: nosniff")
        expect(response.headers.get("referrer-policy") == "same-origin", f"{name}: referrer")
        expect(response.headers.get("cache-control") == "no-store", f"{name}: cache-control")
    expect("content-security-policy" not in world.client().get("/health").headers, "API headers")
    for name, response in (
        ("sign-in", answers["200"]),
        ("not found", answers["404"]),
        ("sign-in error", answers["sign-in 401"]),
    ):
        problems = Page(response.text).inline_problems()
        expect(not problems, f"{name}: inline code or style: {problems}")
    expect("htmx-config" in answers["200"].text, "htmx is not configured from a meta tag")

    # a handler's own Cache-Control is kept, and a handler cannot weaken the other headers
    def private(_: Any) -> Response:
        return Response(
            "x", headers={"Cache-Control": "private", "Content-Security-Policy": "default-src *"}
        )

    mini = Starlette(routes=[Route("/web/x", private), Route("/other", lambda _: Response("y"))])
    mini.add_middleware(WebHeadersMiddleware)
    mc = TestClient(mini)
    inner = mc.get("/web/x")
    expect(inner.headers["cache-control"] == "private", "a handler's Cache-Control is overridden")
    expect(inner.headers["content-security-policy"] == CSP, "a handler replaced the CSP")
    expect("content-security-policy" not in mc.get("/other").headers, "headers outside /web")
    passed(
        "g: exact CSP and the other headers on 200, 303, 401, 403, 404, 413, static; no inline code"
    )


def check_sign_out(world: World) -> None:
    token = world.session()
    bearer = {"Authorization": f"Bearer {token}"}
    expect(world.client().get("/events", headers=bearer).status_code == 200, "session not valid")
    response = sign_out(world, token, headers={"Origin": OWN}, csrf=expected_csrf(token))
    expect(response.status_code == 303, f"sign-out status {response.status_code}")
    raw = response.headers["set-cookie"]
    expect(raw.startswith("tl_session=;") and "Max-Age=0" in raw, f"cookie not expired: {raw}")
    expect({"Path=/web", "HttpOnly", "SameSite=Strict"} <= cookie_attrs(raw), raw)
    expect(world.client().get("/events", headers=bearer).status_code == 401, "token still works")
    expect(world.client(token).get("/web/").status_code == 303, "old cookie still works")
    again = sign_out(world, token, headers={"Origin": OWN}, csrf=expected_csrf(token))
    expect(again.status_code == 401, f"second sign-out: {again.status_code}")
    passed("h: sign-out expires the cookie and ends the session (old token is 401 as a bearer)")


def check_body_limit(world: World) -> None:
    big = "p" * (17 * 1024)
    response = world.client().post("/web/sign-in", data={"username": "alice", "password": big})
    expect(response.status_code == 413, f"over 16 KiB: {response.status_code}")
    expect(big[:50] not in response.text, "the body is echoed")
    chunks = (b"username=alice&password=" + b"p" * 9000, b"p" * 9000)
    chunked = world.client().post(
        "/web/sign-in",
        content=iter(chunks),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    expect(chunked.status_code == 413, f"chunked over 16 KiB: {chunked.status_code}")
    fine = world.client().post("/web/sign-in", data={"username": "alice", "password": WRONG})
    expect(fine.status_code in (401, 423), "a small body is refused for size")
    passed("i: a body over 16 KiB to /web/sign-in is 413, declared or chunked")


def check_openapi(world: World) -> None:
    paths = world.app.openapi()["paths"]
    expect(not [p for p in paths if p.startswith("/web")], "a /web route is in the OpenAPI")
    expect(any(getattr(r, "path", "").startswith("/web") for r in world.app.routes), "no /web")
    run = subprocess.run(
        [sys.executable, "-m", "tl_api.openapi"], cwd=ROOT, capture_output=True, text=True
    )
    expect(run.returncode == 0, f"openapi generation failed: {run.stderr[-200:]}")
    diff = subprocess.run(
        ["git", "diff", "--exit-code", "--stat", "--", "docs/reference/openapi.json"],
        cwd=ROOT, capture_output=True, text=True,
    )  # fmt: skip
    expect(diff.returncode == 0, f"openapi.json changed:\n{diff.stdout}")
    passed("j: docs/reference/openapi.json is unchanged and lists no /web route")


def check_manifest(world: World) -> None:
    spec = importlib.util.spec_from_file_location(
        "check_licences", ROOT / "dev" / "tools" / "check_licences.py"
    )
    expect(spec is not None and spec.loader is not None, "check_licences.py not found")
    assert spec is not None and spec.loader is not None
    licences = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(licences)
    manifest = tomllib.loads((VENDOR / "VENDORED.toml").read_text(encoding="utf-8"))["file"]
    client = world.client()
    listed = set()
    for entry in manifest:
        path = VENDOR / entry["path"]
        listed.add(path.resolve())
        data = path.read_bytes()
        expect(hashlib.sha256(data).hexdigest() == entry["sha256"], f"hash of {entry['path']}")
        expect(licences.term_ok(entry["licence"], entry["name"]), f"licence of {entry['name']}")
        expect(
            entry["licence"] in ("0BSD", "Apache-2.0", "MIT", "BSD-2-Clause", "ISC"), "permissive"
        )
        expect(set(entry) >= {"path", "name", "version", "licence", "url", "sha256"}, "fields")
        served = client.get(f"/web/static/vendor/{entry['path']}")
        expect(served.status_code == 200, f"{entry['path']} served {served.status_code}")
        expect(hashlib.sha256(served.content).hexdigest() == entry["sha256"], "served bytes differ")
        if entry["path"].endswith(".mjs"):
            expect(served.headers["content-type"].startswith("text/javascript"),
                   f"{entry['path']}: {served.headers['content-type']}")  # fmt: skip
    on_disk = {p.resolve() for p in VENDOR.rglob("*") if p.is_file() and p.name != "VENDORED.toml"}
    expect(on_disk == listed, f"files not in the manifest: {on_disk ^ listed}")
    by_name = {e["name"]: e for e in manifest}
    expect(by_name["htmx"]["version"] == "2.0.4", "htmx version")
    expect(b'version:"2.0.4"' in (VENDOR / "htmx" / "htmx.min.js").read_bytes(), "htmx build")
    pdf = tuple(int(x) for x in by_name["pdfjs-dist"]["version"].split("."))
    expect(pdf >= (4, 2, 67), f"pdfjs-dist {pdf} is open to CVE-2024-4367")
    expect(b"4.10.38" in (VENDOR / "pdfjs" / "pdf.min.mjs").read_bytes(), "pdf.js build")
    expect("Zero-Clause BSD" in (VENDOR / "htmx" / "LICENSE").read_text(), "htmx LICENSE text")
    expect("Apache License" in (VENDOR / "pdfjs" / "LICENSE").read_text(), "pdf.js LICENSE text")
    js = client.get("/web/static/tl.js")
    expect(js.status_code == 200 and js.headers["content-type"].startswith("text/javascript"), "js")
    expect(client.get("/web/static/..%2f..%2fapp.py").status_code != 200, "path traversal")
    passed("k: manifest hashes, licences, htmx 2.0.4, pdf.js >= 4.2.67, .mjs is text/javascript")


def check_no_textual() -> None:
    code = (
        "import sys, tl_web, tl_web.app, tl_web.csrf, tl_web.session;"
        "sys.exit(1 if 'textual' in sys.modules else 0)"
    )
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    expect(run.returncode == 0, f"textual is imported by tl_web: {run.stderr[-200:]}")
    passed("l: importing tl_web does not import textual")


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="web1-s1-"))
    world = World(work)
    try:
        check_sign_in(world)
        token = world.session()
        check_cookie_only_on_web(world, token)
        check_unauthenticated(world, token)
        check_home(world, token)
        check_csrf(world)
        check_config(world)
        check_headers(world, token)
        check_sign_out(world)
        check_body_limit(world)
        check_openapi(world)
        check_manifest(world)
        check_no_textual()
        check_wrong_password(world)  # last: it locks alice
    except AssertionError as exc:
        print(f"FAIL {exc}")
        return 1
    finally:
        world.backend.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
