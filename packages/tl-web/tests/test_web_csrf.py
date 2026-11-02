"""CSRF on every unsafe ``/web`` route, and no GET that changes state (S1 check e, S5 pin 4).

``test_every_unsafe_web_route_is_csrf_checked`` enumerates ``app.routes``: a route added later
without ``csrf.verify`` fails it with no edit to this file. Sign-in is the one named exemption.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
#: Unsafe routes that carry no CSRF token on purpose. Sign-in has no session yet: there is nothing
#: to forge a request against, and the form is protected by the lockout and the rate limit instead.
EXEMPT = {("POST", "/web/sign-in")}
#: What a path parameter is filled with when the walk calls a route; an unlisted name gets "x".
FILL = {"project": "P123", "command": "CloseTechnical", "rest": "nowhere", "log": "rfis"}
PARAM = re.compile(r"\{(\w+)(?::\w+)?\}")


def fill(template: str, world: Any) -> str:
    values = {
        **FILL,
        "record_id": world.ids["closed"],
        "file_id": world.hidden.extra_ids["open_file"],
        "number": world.numbers["open_rfi"],
    }
    return PARAM.sub(lambda m: values.get(m.group(1), "x"), template)


def test_the_walk_finds_the_unsafe_routes(world: Any, k: Any) -> None:
    routes = k.web_routes(world.app, UNSAFE)
    paths = {path for _, path in routes}
    assert "/web/sign-out" in paths
    assert "/web/p/{project}/records/{record_id}/do/{command}" in paths
    assert ("POST", "/web/sign-in") in routes
    for method in UNSAFE:  # the catch-all answers every unsafe method after the CSRF check
        assert (method, "/web/{rest:path}") in routes


def test_every_unsafe_web_route_is_csrf_checked(fresh_world: Any, k: Any) -> None:
    world = fresh_world
    checked = 0
    for method, template in k.web_routes(world.app, UNSAFE):
        if (method, template) in EXEMPT:
            continue
        url = fill(template, world)
        me, other = world.web("bob"), world.web("ctl")
        own = {"Origin": k.OWN}
        body_of = lambda token: {"csrf": token} if token else None  # noqa: E731
        attempts = {
            "no token": dict(headers=own),
            "wrong token": dict(headers=own, data=body_of("nope")),
            "wrong header token": dict(headers={**own, "X-CSRF-Token": "nope"}),
            "another session": dict(headers=own, data=body_of(other.csrf)),
            "another session, header": dict(headers={**own, "X-CSRF-Token": other.csrf}),
            "foreign Origin": dict(
                headers={"Origin": "http://evil.example"}, data=body_of(me.csrf)
            ),
            "null Origin": dict(headers={"Origin": "null"}, data=body_of(me.csrf)),
            "no Origin, foreign Referer": dict(
                headers={"Referer": "http://evil.example/web/"}, data=body_of(me.csrf)
            ),
            "no Origin, no Referer": dict(headers={}, data=body_of(me.csrf)),
            "own host, other port": dict(
                headers={"Origin": "http://127.0.0.1:9"}, data=body_of(me.csrf)
            ),
        }
        bodies = set()
        for what, kwargs in attempts.items():
            response = me.client.request(method, url, **kwargs)
            assert response.status_code == 403, (
                f"{method} {template}: {what}: {response.status_code}"
            )
            assert response.json()["error"] == "csrf_refused", f"{method} {template}: {what}"
            bodies.add(response.content)
        assert len(bodies) == 1, f"{method} {template}: the refusal says which check failed"
        # the right token and the own origin pass the CSRF stage: the route's own answer follows
        for how in ("form", "header"):
            session = world.web("bob")  # a new session: sign-out ends the one it is called with
            kwargs = (
                dict(headers=own, data=body_of(session.csrf))
                if how == "form"
                else dict(headers={**own, "X-CSRF-Token": session.csrf})
            )
            response = session.client.request(method, url, **kwargs)
            refused = response.status_code == 403 and "csrf_refused" in response.text
            assert not refused, f"{method} {template}: the right token ({how}) was refused"
        checked += 1
    assert checked >= 4  # sign-out, the action route and the catch-all's four methods


def test_a_refusal_never_ends_the_session(fresh_world: Any, k: Any) -> None:
    world = fresh_world
    me = world.web("bob")
    refused = me.client.post("/web/sign-out", headers={"Origin": k.OWN})
    assert refused.status_code == 403
    bearer = {"Authorization": f"Bearer {me.token}"}
    assert world.client().get("/events", headers=bearer).status_code == 200


def test_a_changed_token_does_not_pass(fresh_world: Any, k: Any) -> None:
    me = fresh_world.web("bob")
    changed = me.csrf.rstrip("=") + "x"
    out = me.client.post("/web/sign-out", data={"csrf": changed}, headers={"Origin": k.OWN})
    assert out.status_code == 403


def test_tl_web_origin_replaces_the_requests_own_origin(
    fresh_world: Any, k: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    me, other = fresh_world.web("bob"), fresh_world.web("ctl")
    monkeypatch.setenv("TL_WEB_ORIGIN", "https://tl.example.com/")
    own = me.client.post("/web/sign-out", data={"csrf": me.csrf}, headers={"Origin": k.OWN})
    assert own.status_code == 403  # the request's own origin no longer counts
    set_origin = other.client.post(
        "/web/sign-out", data={"csrf": other.csrf}, headers={"Origin": "https://tl.example.com"}
    )
    assert set_origin.status_code == 303


def test_referer_is_accepted_when_origin_is_absent(fresh_world: Any, k: Any) -> None:
    me = fresh_world.web("bob")
    out = me.client.post(
        "/web/sign-out", data={"csrf": me.csrf}, headers={"Referer": f"{k.OWN}/web/anything?x=1"}
    )
    assert out.status_code == 303


def test_the_right_token_and_own_origin_sign_out(fresh_world: Any, k: Any) -> None:
    header = fresh_world.web("bob")
    out = header.client.post(
        "/web/sign-out", headers={"Origin": k.OWN, "X-CSRF-Token": header.csrf}
    )
    assert out.status_code == 303 and out.headers["location"] == "/web/sign-in"
    form = fresh_world.web("ctl")
    out = form.client.post("/web/sign-out", data={"csrf": form.csrf}, headers={"Origin": k.OWN})
    assert out.status_code == 303


def test_the_pages_carry_the_token_the_spec_computes(
    fresh_world: Any, htmlkit: Any, k: Any
) -> None:
    me = fresh_world.web("bob")
    doc = htmlkit.parse(me.client.get("/web/nowhere").text)
    assert doc.meta("csrf-token") == k.expected_csrf(me.token)
    sign_out_form = [n for n in doc.all() if n.tag == "input" and n.attrs.get("name") == "csrf"]
    assert [n.attrs["value"] for n in sign_out_form] == [k.expected_csrf(me.token)]


def test_no_get_route_changes_state(fresh_world: Any, k: Any) -> None:
    """Walk every GET route under /web as a controller; the ledger holds the same events after."""
    world = fresh_world
    me = world.web("ctl")
    gets = k.web_routes(world.app, {"GET"})
    assert len(gets) >= 10
    before = world.events()
    for _, template in gets:
        url = fill(template, world)
        me.client.get(url, params={"scope": "project:P123"})
    assert world.events() == before
