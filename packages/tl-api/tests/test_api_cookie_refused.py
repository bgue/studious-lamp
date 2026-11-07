"""The session cookie of the web client is read under ``/web/`` and nowhere else (P2-WEB1-S1).

``tl_api.auth.AuthenticationMiddleware`` reads the ``tl_session`` cookie only when the path starts
with ``/web/``. The JSON API stays bearer-only: the same token in the cookie is 401 on a sample of
routes (GET and POST), the same token as a bearer works, and look-alike prefixes (``/webx/``,
``/webs/``, ``/web`` itself) do not read the cookie either.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password

PASSWORD = "correct horse battery"


@pytest.fixture
def session_token(harness: Harness) -> str:
    with harness.backend(False) as uow:
        accounts.create_account(
            uow, username="cora", display_name="Cora", kind="person", roles=["user"],
            password=prepare_password(PASSWORD, username="cora"), by="svc:test",
        )  # fmt: skip
    return sessions.sign_in(harness.backend, username="cora", password=PASSWORD)[1]


def client_with(harness: Harness, *, cookie: str | None = None, bearer: str | None = None) -> Any:
    client = TestClient(harness.app, base_url="http://127.0.0.1", follow_redirects=False)
    if cookie is not None:
        client.headers["Cookie"] = f"tl_session={cookie}"
    if bearer is not None:
        client.headers["Authorization"] = f"Bearer {bearer}"
    return client


GET_SAMPLE = ("/events", "/auth/me", "/records/01J000000000000000000000", "/projects/P123/rfis")
POST_SAMPLE = ("/commands/PostToFeed", "/commands/CreateRecord", "/auth/sign-out")


@pytest.mark.parametrize("path", GET_SAMPLE)
def test_the_cookie_is_401_on_a_get_route(harness: Harness, session_token: str, path: str) -> None:
    assert client_with(harness, cookie=session_token).get(path).status_code == 401


@pytest.mark.parametrize("path", POST_SAMPLE)
def test_the_cookie_is_401_on_a_post_route(harness: Harness, session_token: str, path: str) -> None:
    response = client_with(harness, cookie=session_token).post(path, json={})
    assert response.status_code == 401


def test_the_same_token_as_a_bearer_is_accepted(harness: Harness, session_token: str) -> None:
    client = client_with(harness, bearer=session_token)
    assert client.get("/events").status_code == 200
    assert client.get("/auth/me").status_code == 200
    assert client.post("/commands/PostToFeed", json={}).status_code != 401  # past authentication


@pytest.mark.parametrize("path", ["/webx/", "/webx/sign-in", "/web", "/webs/p/P1"])
def test_look_alike_prefixes_do_not_read_the_cookie(
    harness: Harness, session_token: str, path: str
) -> None:
    response = client_with(harness, cookie=session_token).get(path)
    assert response.status_code == 401
    if path != "/web":  # `/web` is under the web's headers, but it never reads the cookie
        assert "content-security-policy" not in response.headers


def test_under_web_the_cookie_is_read(harness: Harness, session_token: str) -> None:
    """The other half of the rule: the same cookie works under /web/ (the 404 page is a page)."""
    response = client_with(harness, cookie=session_token).get("/web/nowhere")
    assert response.status_code == 404
