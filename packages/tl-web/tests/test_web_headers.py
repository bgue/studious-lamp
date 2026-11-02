"""The headers of every answer under ``/web``, the body limits, the vendored files (S1, S4).

The policy is written out again in ``conftest.CSP`` (spec web-client-i1 section 5), not read
back from the code under test.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient
from tl_web.app import WebHeadersMiddleware
from tl_web.reads import WebReadClient

WRONG = "wrong-password-SENTINEL-4711"
WEB_SRC = Path(__file__).resolve().parents[1] / "src" / "tl_web"
VENDOR = WEB_SRC / "static" / "vendor"


def other_headers_ok(response: Any, label: str) -> None:
    assert response.headers.get("x-content-type-options") == "nosniff", label
    assert response.headers.get("referrer-policy") == "same-origin", label
    assert "cache-control" in response.headers, label


def test_the_csp_and_the_other_headers_are_on_every_answer(
    light_world: Any, htmlkit: Any, k: Any
) -> None:
    w = light_world
    me = w.web("bob")
    other = w.web("ctl")
    answers = {
        "200": (w.client().get("/web/sign-in"), 200),
        "303": (w.client().get("/web/"), 303),
        "401": (w.client().post("/web/sign-out"), 401),
        "403": (other.client.post("/web/sign-out", headers={"Origin": k.OWN}), 403),
        "404": (me.client.get("/web/nowhere"), 404),
        "static": (w.client().get("/web/static/tl.css"), 200),
        "static 404": (w.client().get("/web/static/none.css"), 404),
        "413": (
            w.client().post("/web/sign-in", data={"username": "a", "password": "p" * 20_000}),
            413,
        ),
        "sign-in 401": (
            w.client().post("/web/sign-in", data={"username": "bob", "password": WRONG}),
            401,
        ),
        "sign-in 303": (
            w.client().post("/web/sign-in", data={"username": "bob", "password": k.PASSWORD}),
            303,
        ),
    }
    for name, (response, status) in answers.items():
        assert response.status_code == status, name
        assert response.headers.get("content-security-policy") == k.CSP, name
        other_headers_ok(response, name)
        assert response.headers["cache-control"] == "no-store" or name.startswith("static"), name
    assert "content-security-policy" not in w.client().get("/health").headers  # the API has none
    for name in ("200", "404", "sign-in 401"):
        problems = htmlkit.parse(answers[name][0].text).inline_problems()
        assert not problems, f"{name}: {problems}"
    assert htmlkit.parse(answers["200"][0].text).meta("htmx-config")  # htmx is set by a meta tag


def test_a_500_page_has_the_headers_too(world: Any, k: Any) -> None:
    me = world.web("bob")
    broken = world.client(me.token, raises=False)

    def boom(self: WebReadClient, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("a read failed")

    with mock.patch.object(WebReadClient, "list_rfis", boom):
        response = broken.get("/web/p/P123/rfis")
    assert response.status_code == 500
    assert response.headers.get("content-security-policy") == k.CSP
    other_headers_ok(response, "500")
    assert "a read failed" not in response.text  # the text of an error is never shown


def test_a_handlers_own_cache_control_is_kept_and_the_csp_cannot_be_weakened(k: Any) -> None:
    def private(_: Any) -> Response:
        return Response(
            "x", headers={"Cache-Control": "private", "Content-Security-Policy": "default-src *"}
        )

    mini = Starlette(routes=[Route("/web/x", private), Route("/other", lambda _: Response("y"))])
    mini.add_middleware(WebHeadersMiddleware)
    client = TestClient(mini)
    inner = client.get("/web/x")
    assert inner.headers["cache-control"] == "private"
    assert inner.headers["content-security-policy"] == k.CSP
    assert "content-security-policy" not in client.get("/other").headers  # nothing outside /web


# --- body limits ------------------------------------------------------------------------------


def test_sign_in_cuts_a_body_over_16_kib(light_world: Any) -> None:
    big = "p" * (17 * 1024)
    response = light_world.client().post("/web/sign-in", data={"username": "bob", "password": big})
    assert response.status_code == 413
    assert big[:50] not in response.text  # the body is not echoed
    chunks = (b"username=bob&password=" + b"p" * 9000, b"p" * 9000)
    chunked = light_world.client().post(
        "/web/sign-in",
        content=iter(chunks),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert chunked.status_code == 413  # declared or chunked
    small = light_world.client().post("/web/sign-in", data={"username": "bob", "password": WRONG})
    assert small.status_code in (401, 423)


def test_other_web_bodies_are_cut_at_64_kib(light_world: Any, k: Any) -> None:
    me = light_world.web("bob")
    headers = {**me.headers(), "Content-Type": "application/x-www-form-urlencoded"}
    big = "a=" + "x" * (100 * 1024)
    response = me.client.post("/web/p/x/records/y/do/z", content=big, headers=headers)
    assert response.status_code == 413 and response.json()["error"] == "payload_too_large"
    assert (
        light_world.client().post("/web/sign-in", content=big, headers=headers).status_code == 413
    )
    middle = "a=" + "x" * (20 * 1024)  # over sign-in's limit, under the web's
    assert (
        light_world.client().post("/web/sign-in", content=middle, headers=headers).status_code
        == 413
    )
    assert (
        me.client.post("/web/p/x/records/y/do/z", content=middle, headers=headers).status_code
        != 413
    )


# --- the pages carry no inline code -----------------------------------------------------------


def test_every_answer_of_a_walk_has_the_csp_and_no_inline_code(
    fresh_world: Any, htmlkit: Any, k: Any
) -> None:
    w = fresh_world
    me = w.web("bob")
    start = len(w.answers)
    base = "/web/p/P123"
    for path in (
        f"{base}/rfis", f"{base}/rfis?sel={w.numbers['waiting']}", f"{base}/correspondence",
        f"{base}/documents", f"{base}/rfis/panel/{w.numbers['open_rfi']}",
        f"{base}/records/{w.ids['waiting']}", f"{base}/records/{w.ids['waiting']}?tab=history",
        f"{base}/records/{w.ids['waiting']}?tab=files", f"{base}/records/{k.NEVER}",
        f"{base}/files/{w.hidden.extra_ids['open_file']}/view", "/web/nowhere", "/web/sign-in",
    ):  # fmt: skip
        me.client.get(path)
    seen = w.answers[start:]
    assert len(seen) >= 12
    for response in seen:
        assert response.headers.get("content-security-policy") == k.CSP, response.url
        if "text/html" in response.headers.get("content-type", ""):
            assert htmlkit.parse(response.text).inline_problems() == [], response.url


def test_tl_js_is_short_and_holds_nothing_dangerous(k: Any) -> None:
    script = (WEB_SRC / "static" / "tl.js").read_text()
    for word in ("eval(", "fetch(", "innerHTML"):
        assert word not in script, word
    assert len(script.splitlines()) <= 200
    assert "htmx:configRequest" in script and "X-CSRF-Token" in script  # it sends the CSRF header


def test_htmx_is_configured_without_eval_or_script_tags(world: Any, htmlkit: Any) -> None:
    page = htmlkit.parse(world.web("bob").client.get("/web/p/P123/rfis").text)
    config = json.loads(page.meta("htmx-config") or "{}")
    assert config["allowEval"] is False
    assert config["allowScriptTags"] is False
    assert config["includeIndicatorStyles"] is False
    assert config["selfRequestsOnly"] is True
    assert page.meta("csrf-token")


# --- the vendored files -----------------------------------------------------------------------


def test_the_manifest_lists_every_vendored_file_and_the_hashes_match(light_world: Any) -> None:
    manifest = tomllib.loads((VENDOR / "VENDORED.toml").read_text(encoding="utf-8"))["file"]
    client = light_world.client()
    listed = set()
    for entry in manifest:
        path = VENDOR / entry["path"]
        listed.add(path.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["path"]
        assert entry["licence"] in ("0BSD", "Apache-2.0", "MIT", "BSD-2-Clause", "ISC")
        assert set(entry) >= {"path", "name", "version", "licence", "url", "sha256"}
        served = client.get(f"/web/static/vendor/{entry['path']}")
        assert served.status_code == 200, entry["path"]
        assert hashlib.sha256(served.content).hexdigest() == entry["sha256"]  # served == committed
        if entry["path"].endswith(".mjs"):
            assert served.headers["content-type"].startswith("text/javascript"), entry["path"]
    on_disk = {p.resolve() for p in VENDOR.rglob("*") if p.is_file() and p.name != "VENDORED.toml"}
    assert on_disk == listed, on_disk ^ listed  # no file outside the manifest


def test_htmx_is_the_pinned_build_and_the_licence_texts_are_there() -> None:
    manifest = tomllib.loads((VENDOR / "VENDORED.toml").read_text(encoding="utf-8"))["file"]
    by_name = {e["name"]: e for e in manifest}
    assert by_name["htmx"]["version"] == "2.0.4"
    assert b'version:"2.0.4"' in (VENDOR / "htmx" / "htmx.min.js").read_bytes()
    assert "Zero-Clause BSD" in (VENDOR / "htmx" / "LICENSE").read_text()
    assert "Apache License" in (VENDOR / "pdfjs" / "LICENSE").read_text()


def test_static_serves_scripts_as_javascript_and_refuses_a_traversal(light_world: Any) -> None:
    client = light_world.client()
    js = client.get("/web/static/tl.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")
    assert client.get("/web/static/..%2f..%2fapp.py").status_code != 200


@pytest.mark.parametrize("path", ["/web/static/tl.css", "/web/static/tl.js"])
def test_static_files_are_same_origin_assets(light_world: Any, path: str) -> None:
    assert light_world.client().get(path).status_code == 200
