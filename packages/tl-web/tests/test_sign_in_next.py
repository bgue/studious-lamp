"""The sign-in return address: used only when it is exactly a scan path (no open redirect)."""

from __future__ import annotations

from typing import Any

import pytest

GOOD = "/web/q/ABCDEFGH23456789"
BAD = [
    "https://x",
    "//x",
    "/web/q/abc",
    "/web/q/abcdefgh23456789",
    "/web/q/ABCDEFGH23456789/..",
    "/web/q/ABCDEFGH23456789\n",
    " /web/q/ABCDEFGH23456789",
    "/web/p/P123/rfis",
    "/web/q/ABCDEFGH23456789?x=1",
    "",
]


def submit(w: Any, k: Any, value: str | None) -> Any:
    data = {"username": "bob", "password": k.PASSWORD}
    if value is not None:
        data["next"] = value
    return w.client().post("/web/sign-in", data=data, headers={"Origin": k.OWN})


def test_a_scan_path_is_the_return_address(light_world: Any, k: Any) -> None:
    response = submit(light_world, k, GOOD)
    assert response.status_code == 303 and response.headers["location"] == GOOD
    assert "tl_session=" in response.headers["set-cookie"]


@pytest.mark.parametrize("value", [*BAD, None])
def test_anything_else_is_dropped_to_the_home(light_world: Any, k: Any, value: str | None) -> None:
    response = submit(light_world, k, value)
    assert response.status_code == 303 and response.headers["location"] == "/web/"


def test_the_form_carries_a_good_next_and_drops_a_bad_one(light_world: Any) -> None:
    client = light_world.client()
    good = client.get("/web/sign-in", params={"next": GOOD})
    assert f'<input type="hidden" name="next" value="{GOOD}">' in good.text
    for value in BAD:
        page = client.get("/web/sign-in", params={"next": value}).text
        assert 'name="next"' not in page, value
    assert 'name="next"' not in client.get("/web/sign-in").text


def test_a_failed_sign_in_keeps_a_good_next(light_world: Any, k: Any) -> None:
    response = light_world.client().post(
        "/web/sign-in",
        data={"username": "bob", "password": "wrong-password-0000", "next": GOOD},
        headers={"Origin": k.OWN},
    )
    assert response.status_code == 401
    assert f'name="next" value="{GOOD}"' in response.text


def test_the_sign_in_page_with_a_next_sends_strict_origin(light_world: Any) -> None:
    client = light_world.client()
    with_next = client.get("/web/sign-in", params={"next": GOOD})
    assert with_next.headers["referrer-policy"] == "strict-origin"
    assert (
        client.get("/web/sign-in", params={"next": "https://x"}).headers["referrer-policy"]
        == "strict-origin"
    )  # the query is there either way
    assert client.get("/web/sign-in").headers["referrer-policy"] == "same-origin"
