"""The web sign-in, the cookie session and the switches (P2-WEB1-S1; ports of S1 a to h, d2).

The cookie authenticates ``/web/`` only; the JSON API stays bearer-only (its own test is
``packages/tl-api/tests/test_api_cookie_refused.py``). Sign-in is the JSON route's own handler.
"""

from __future__ import annotations

import html
import importlib.util
import json
import os
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from tl_api.ratelimit import SourceLimiter
from tl_api.settings import web_enabled
from tl_web.session import cookie_flags

WRONG = "wrong-password-SENTINEL-4711"
ROOT = Path(__file__).resolve().parents[3]


def test_sign_in_is_a_303_with_a_strict_http_only_cookie(light_world: Any, k: Any) -> None:
    response, token = light_world.sign_in("bob")
    assert response.status_code == 303
    assert response.headers["location"] == "/web/"
    attrs = k.cookie_attrs(response.headers["set-cookie"])
    assert {"HttpOnly", "SameSite=Strict", "Path=/web", "Max-Age=43200"} <= attrs
    assert "Secure" not in attrs  # plain loopback http in test
    assert token and token not in response.text


def test_every_sign_in_gives_a_new_token(light_world: Any) -> None:
    _, first = light_world.sign_in("bob")
    _, second = light_world.sign_in("bob")
    assert first and second and first != second


@pytest.mark.parametrize(
    ("host", "env", "secure"),
    [
        ("203.0.113.5", "test", True),  # a public host
        ("localhost", "prod", True),  # loopback in production
        ("127.0.0.1", "", True),  # an unset environment
        ("127.0.0.1", "dev", False),
        ("localhost", "test", False),
        ("::1", "ci", False),
    ],
)
def test_secure_flag_follows_host_and_environment(host: str, env: str, secure: bool) -> None:
    flags = cookie_flags(host, env)
    assert ("Secure" in flags) is secure
    assert {"HttpOnly", "SameSite=Strict", "Path=/web"} <= set(flags)


def test_secure_flag_on_a_public_host_through_the_app(light_world: Any, k: Any) -> None:
    elsewhere = light_world.client(base="http://tl.example.com")
    moved = elsewhere.post(
        "/web/sign-in",
        data={"username": "bob", "password": k.PASSWORD},
        headers={"Origin": "http://tl.example.com"},
    )
    assert "Secure" in k.cookie_attrs(moved.headers["set-cookie"])


@pytest.mark.parametrize("username", ["bob", "nobody"])
def test_wrong_password_answers_as_the_json_route(light_world: Any, k: Any, username: str) -> None:
    api = light_world.client()
    expected = api.post("/auth/sign-in", json={"username": username, "password": WRONG})
    response = light_world.client().post(
        "/web/sign-in",
        data={"username": username, "password": WRONG},
        headers={"Origin": k.OWN},
    )
    assert response.status_code == expected.status_code == 401
    assert expected.json()["message"] in html.unescape(response.text)
    assert "set-cookie" not in response.headers
    assert WRONG not in response.text + str(dict(response.headers))  # the password is not echoed
    assert f'value="{username}"' in response.text  # the username is


def test_a_hostile_username_is_escaped(light_world: Any, k: Any) -> None:
    evil = "<script>alert(1)</script>"
    response = light_world.client().post(
        "/web/sign-in", data={"username": evil, "password": WRONG}, headers={"Origin": k.OWN}
    )
    assert response.status_code == 401
    assert "&lt;script&gt;" in response.text and evil not in response.text


def test_an_empty_username_is_the_json_routes_422(light_world: Any, k: Any) -> None:
    empty = light_world.client().post(
        "/web/sign-in", data={"username": "", "password": WRONG}, headers={"Origin": k.OWN}
    )
    sent = light_world.client().post("/auth/sign-in", json={"username": "", "password": WRONG})
    assert empty.status_code == sent.status_code == 422


def test_the_lockout_is_the_json_routes(light_world: Any, k: Any) -> None:
    api = light_world.client()
    locked = None
    for _ in range(30):
        locked = api.post("/auth/sign-in", json={"username": "bob", "password": WRONG})
        if locked.status_code == 423:
            break
    assert locked is not None and locked.status_code == 423
    web = light_world.client().post(
        "/web/sign-in",
        data={"username": "bob", "password": k.PASSWORD},
        headers={"Origin": k.OWN},
    )
    assert web.status_code == 423
    assert locked.json()["message"] in html.unescape(web.text)


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://evil.example"},
        {"Origin": "null"},
        {"Referer": "http://evil.example/web/sign-in"},
        {"Origin": "http://127.0.0.1:9"},
        {},  # neither Origin nor Referer
    ],
    ids=["foreign Origin", "null Origin", "foreign Referer", "other port", "no Origin or Referer"],
)
def test_sign_in_from_a_foreign_or_unstated_origin_is_refused_before_it_is_tried(
    fresh_world: Any, k: Any, headers: dict[str, str]
) -> None:
    """A login CSRF: the right password from a foreign page is a 403, not a session."""
    w = fresh_world
    refused = w.client().post(
        "/web/sign-in", data={"username": "bob", "password": k.PASSWORD}, headers=headers
    )
    assert refused.status_code == 403 and refused.json()["error"] == "csrf_refused"
    assert "set-cookie" not in refused.headers
    assert refused.headers["content-security-policy"] == k.CSP
    # the same body as the CSRF check of every other unsafe route
    other = w.web("bob")
    same = other.client.post("/web/sign-out", headers={"Origin": "http://evil.example"})
    assert same.status_code == 403 and same.content == refused.content
    # it was refused before the credentials were looked at: a wrong password is no 401
    wrong = w.client().post(
        "/web/sign-in", data={"username": "bob", "password": WRONG}, headers=headers
    )
    assert wrong.status_code == 403 and "set-cookie" not in wrong.headers


def test_sign_in_needs_the_own_origin_and_no_token(fresh_world: Any, k: Any) -> None:
    w = fresh_world
    form = {"username": "bob", "password": k.PASSWORD}
    by_origin = w.client().post("/web/sign-in", data=form, headers={"Origin": k.OWN})
    assert by_origin.status_code == 303 and "tl_session=" in by_origin.headers["set-cookie"]
    by_referer = w.client().post(
        "/web/sign-in", data=form, headers={"Referer": f"{k.OWN}/web/sign-in"}
    )
    assert by_referer.status_code == 303


def test_failed_web_sign_ins_share_the_json_routes_count_and_answer_429(
    light_world: Any, k: Any
) -> None:
    """Three failures from one source (web and JSON together) stop both routes, with the headers."""
    w = light_world
    app = w.make_app(SourceLimiter(3))
    web = w.client(app=app)
    api = w.client(app=app)
    own = {"Origin": k.OWN}
    wrong = {"username": "bob", "password": WRONG}
    assert web.post("/web/sign-in", data=wrong, headers=own).status_code == 401
    assert api.post("/auth/sign-in", json=wrong).status_code == 401  # counted in the same window
    assert web.post("/web/sign-in", data=wrong, headers=own).status_code == 401
    limited = web.post(
        "/web/sign-in", data={"username": "bob", "password": k.PASSWORD}, headers=own
    )
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.headers["content-security-policy"] == k.CSP
    assert "set-cookie" not in limited.headers
    assert api.post("/auth/sign-in", json=wrong).status_code == 429
    # a fresh source is not limited
    assert (
        w.client(app=w.make_app(SourceLimiter(3)))
        .post("/web/sign-in", data={"username": "bob", "password": k.PASSWORD}, headers=own)
        .status_code
        == 303
    )


def test_the_cookie_authenticates_web_only(light_world: Any) -> None:
    token = light_world.sign_in("bob")[1]
    cookie = light_world.client(token)
    bearer = {"Authorization": f"Bearer {token}"}
    assert cookie.get("/events").status_code == 401
    assert cookie.get("/auth/me").status_code == 401
    assert cookie.post("/commands/PostToFeed", json={}).status_code == 401
    assert light_world.client().get("/events", headers=bearer).status_code == 200
    # look-alike paths are not /web: the cookie is not read there, and no web headers
    for path in ("/webx/", "/webx/sign-in", "/web", "/webs/p/P1"):
        response = cookie.get(path)
        assert response.status_code == 401, path
        if path != "/web":  # "/web" itself is under /web: it has the headers, never the cookie
            assert "content-security-policy" not in response.headers, path
    assert cookie.get("/web/nowhere").status_code == 404  # the cookie does work under /web/


def test_no_cookie_is_a_redirect_to_sign_in_and_a_post_is_401(light_world: Any) -> None:
    anon = light_world.client()
    response = anon.get("/web/")
    assert response.status_code == 303 and response.headers["location"] == "/web/sign-in"
    assert anon.get("/web/p/P123/rfis").status_code == 303  # a deep GET too
    out = anon.post("/web/sign-out")
    assert out.status_code == 401 and out.json()["error"] == "unauthorized"
    assert light_world.client("junk").get("/web/").status_code == 303  # an unknown cookie
    assert light_world.client("junk").post("/web/sign-out").status_code == 401
    assert anon.get("/web/sign-in").status_code == 200  # sign-in and static are open
    assert anon.get("/web/static/tl.css").status_code == 200


def test_an_agent_token_behind_the_cookie_is_401(light_world: Any) -> None:
    agent = light_world.agent_token
    assert light_world.client(agent).get("/web/").status_code == 401
    assert light_world.client(agent).get("/web/nowhere").status_code == 401
    assert light_world.client(agent).post("/web/sign-out").status_code == 401
    bearer = {"Authorization": f"Bearer {agent}"}
    assert light_world.client().get("/web/", headers=bearer).status_code == 401


def test_an_authorization_header_wins_over_the_cookie(light_world: Any) -> None:
    token = light_world.sign_in("bob")[1]
    mixed = light_world.client(token).get("/web/", headers={"Authorization": "Bearer junk"})
    assert mixed.status_code == 303  # the cookie was not read


def test_home_goes_to_the_rfi_log_of_tl_project(
    light_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = light_world.client(light_world.sign_in("bob")[1])
    assert user.get("/web/").status_code == 404  # no TL_PROJECT
    monkeypatch.setenv("TL_PROJECT", "P123")
    response = user.get("/web/")
    assert response.status_code == 303 and response.headers["location"] == "/web/p/P123/rfis"
    monkeypatch.setenv("TL_PROJECT", "P1/../x\r\nSet-Cookie: a=b")
    assert user.get("/web/").status_code == 404  # a hostile value is not followed


def test_sign_out_expires_the_cookie_and_ends_the_session(light_world: Any, k: Any) -> None:
    token = light_world.sign_in("bob")[1]
    bearer = {"Authorization": f"Bearer {token}"}
    assert light_world.client().get("/events", headers=bearer).status_code == 200
    out = light_world.client(token).post(
        "/web/sign-out", data={"csrf": k.expected_csrf(token)}, headers={"Origin": k.OWN}
    )
    assert out.status_code == 303 and out.headers["location"] == "/web/sign-in"
    raw = out.headers["set-cookie"]
    assert raw.startswith("tl_session=;") and "Max-Age=0" in raw
    assert {"Path=/web", "HttpOnly", "SameSite=Strict"} <= k.cookie_attrs(raw)
    assert light_world.client().get("/events", headers=bearer).status_code == 401  # a dead token
    assert light_world.client(token).get("/web/").status_code == 303  # the old cookie is nothing
    again = light_world.client(token).post(
        "/web/sign-out", data={"csrf": k.expected_csrf(token)}, headers={"Origin": k.OWN}
    )
    assert again.status_code == 401


def test_openapi_lists_no_web_route(light_world: Any) -> None:
    committed = json.loads((ROOT / "docs" / "reference" / "openapi.json").read_text())
    assert not [p for p in committed["paths"] if p.startswith("/web")]
    paths = light_world.app.openapi()["paths"]
    assert not [p for p in paths if p.startswith("/web")]
    assert any(getattr(r, "path", "").startswith("/web") for r in light_world.app.routes)


# --- the switches (D6) --------------------------------------------------------------------------


@pytest.mark.parametrize(("env", "kind"), [("prod", "short"), ("prod", "none"), ("test", "short")])
def test_a_short_or_missing_secret_stops_start_up(
    light_world: Any, monkeypatch: pytest.MonkeyPatch, env: str, kind: str
) -> None:
    short = "short-secret"
    monkeypatch.setenv("TL_ENV", env)
    monkeypatch.setenv("TL_WEB", "on")
    if kind == "short":
        monkeypatch.setenv("TL_WEB_SECRET", short)
    else:
        monkeypatch.delenv("TL_WEB_SECRET")
    with pytest.raises(RuntimeError) as caught:
        light_world.make_app()
    assert short not in str(caught.value)  # the secret is never in the error text


def test_a_long_secret_starts_in_prod_and_dev_generates_one(
    light_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_ENV", "prod")
    monkeypatch.setenv("TL_WEB", "on")
    light_world.make_app()
    monkeypatch.setenv("TL_ENV", "dev")
    monkeypatch.delenv("TL_WEB_SECRET")
    monkeypatch.delenv("TL_WEB")
    generated = light_world.make_app()
    assert light_world.client(app=generated).get("/web/sign-in").status_code == 200


def test_tl_web_unset_is_on_in_dev_test_ci_only() -> None:
    for name in ("dev", "test", "ci"):
        assert web_enabled({"TL_ENV": name}) is True
    for name in ("prod", "staging", ""):
        assert web_enabled({"TL_ENV": name}) is False
    assert web_enabled({}) is False
    assert web_enabled({"TL_ENV": "test", "TL_WEB": "off"}) is False
    assert web_enabled({"TL_ENV": "prod", "TL_WEB": "on"}) is True
    with pytest.raises(ValueError):
        web_enabled({"TL_ENV": "test", "TL_WEB": "maybe"})


def test_the_web_is_off_in_prod_and_when_switched_off(
    light_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = light_world.sign_in("bob")[1]
    bearer = {"Authorization": f"Bearer {token}"}
    monkeypatch.setenv("TL_ENV", "prod")
    app = light_world.make_app()  # off by default outside dev, test and ci
    assert light_world.client(app=app).get("/web/sign-in", headers=bearer).status_code == 404
    monkeypatch.setenv("TL_ENV", "test")
    monkeypatch.setenv("TL_WEB", "off")
    app = light_world.make_app()
    for who in (light_world.client(app=app), light_world.client(token, app=app)):
        assert who.get("/web/", headers=bearer).status_code == 404
    assert light_world.client(token, app=app).get("/web/").status_code == 401  # no cookie read
    assert light_world.client(app=app).get("/web/").status_code == 401


def test_tl_web_on_with_tl_web_missing_is_a_start_error(
    light_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = importlib.util.find_spec

    def without_web(name: str, *args: Any) -> Any:
        return None if name == "tl_web" else real(name, *args)

    token = light_world.sign_in("bob")[1]
    bearer = {"Authorization": f"Bearer {token}"}
    with mock.patch("importlib.util.find_spec", without_web):
        monkeypatch.setenv("TL_WEB", "on")
        with pytest.raises(RuntimeError):
            light_world.make_app()
        monkeypatch.delenv("TL_WEB")
        app = light_world.make_app()  # unset: silent, and the web is just not there
        assert light_world.client(app=app).get("/web/", headers=bearer).status_code == 404


def test_the_environment_is_restored_after_the_switch_tests(k: Any) -> None:
    assert os.environ.get("TL_ENV") == "test"
    assert os.environ.get("TL_WEB_SECRET") == k.SECRET
