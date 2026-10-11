"""The per-source limit on failed sign-ins (ADR-0009 section 6, re-review condition L)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_api.app import create_app
from tl_api.ratelimit import SourceLimiter, client_key
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core.auth import accounts
from tl_core.auth import password as pw
from tl_core.auth.password import prepare_password

PASSWORD = "correct horse battery"
WRONG = "this is not the password"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_limiter_blocks_the_source_after_the_failures_and_frees_it_with_the_window() -> None:
    clock = Clock()
    limiter = SourceLimiter(3, 60.0, clock=clock)
    assert limiter.retry_after("a") == 0
    for _ in range(2):
        limiter.record_failure("a")
    assert limiter.retry_after("a") == 0
    limiter.record_failure("a")
    assert 59 < limiter.retry_after("a") <= 60
    assert limiter.retry_after("b") == 0  # another source is not affected
    clock.now += 30
    assert 29 < limiter.retry_after("a") <= 30
    clock.now += 31
    assert limiter.retry_after("a") == 0 and limiter.sources() == 0


def test_the_limiter_forgets_the_quietest_sources_beyond_its_bound() -> None:
    limiter = SourceLimiter(1, 60.0, max_sources=3)
    for n in range(10):
        limiter.record_failure(f"s{n}")
    assert limiter.sources() == 3
    assert limiter.retry_after("s9") > 0 and limiter.retry_after("s0") == 0


def test_the_limiter_refuses_nonsense_settings() -> None:
    for bad in ((0, 60.0), (3, 0.0), (3, -1.0)):
        with pytest.raises(ValueError):
            SourceLimiter(*bad)


def scope(peer: str | None, headers: dict[str, str]) -> Any:
    return {
        "client": None if peer is None else (peer, 5000),
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }


def test_the_address_is_the_peer_unless_a_trusted_header_is_configured() -> None:
    spoof = {"X-Forwarded-For": "6.6.6.6"}
    assert client_key(scope("10.0.0.5", spoof), None) == "10.0.0.5"  # ignored when not configured
    assert client_key(scope(None, {}), None) == "unknown"
    assert client_key(scope("10.0.0.5", spoof), "X-Forwarded-For") == "6.6.6.6"
    chain = {"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 203.0.113.9"}
    assert client_key(scope("10.0.0.5", chain), "x-forwarded-for") == "203.0.113.9"  # the last
    assert (
        client_key(scope("10.0.0.5", {"X-Forwarded-For": "2001:db8::1"}), "X-Forwarded-For")
        == "2001:db8::1"
    )
    for junk in ("not an address", "", "1.1.1.1, evil"):
        assert (
            client_key(scope("10.0.0.5", {"X-Forwarded-For": junk}), "X-Forwarded-For")
            == "10.0.0.5"
        )
    assert client_key(scope("10.0.0.5", {}), "X-Forwarded-For") == "10.0.0.5"  # header absent


def make_app(harness: Harness, clock: Clock, **settings: Any) -> TestClient:
    cfg: ApiSettings = replace(harness.settings, **settings)
    app = create_app(
        harness.backend,
        settings=cfg,
        tokens=TokenStore(cfg.tokens_path),
        source_limiter=SourceLimiter(cfg.rate_limit_failures, cfg.rate_limit_window_s, clock=clock),
    )
    client = TestClient(app, raise_server_exceptions=False)
    harness._clients.append(client)  # pyright: ignore[reportPrivateUsage]
    return client


@pytest.fixture
def bob(harness: Harness) -> None:
    with harness.backend() as uow:
        accounts.create_account(
            uow, username="bob", display_name="Bob", kind="person", roles=["user"],
            password=prepare_password(PASSWORD), by="svc:test",
        )  # fmt: skip


def sign_in(client: TestClient, name: str, password: str, **kw: Any) -> Any:
    return client.post("/auth/sign-in", json={"username": name, "password": password}, **kw)


def test_the_21st_failure_from_one_address_is_429_before_any_password_is_hashed(
    harness: Harness, bob: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = make_app(harness, Clock())
    for n in range(20):  # twenty different names: the per-name lockout never trips
        assert sign_in(client, f"name{n}", WRONG).status_code == 401
    calls: list[int] = []
    real = pw._scrypt  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(pw, "_scrypt", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    refused = sign_in(client, "bob", PASSWORD)  # even the right password, from this address
    assert refused.status_code == 429 and refused.json()["error"] == "rate_limited"
    assert int(refused.headers["retry-after"]) in range(590, 601)
    assert PASSWORD not in refused.text and calls == []  # nothing was hashed or looked up


def test_the_limit_ends_with_the_window(harness: Harness, bob: None) -> None:
    clock = Clock()
    client = make_app(harness, clock)
    for n in range(20):
        sign_in(client, f"name{n}", WRONG)
    assert sign_in(client, "bob", PASSWORD).status_code == 429
    clock.now += 601
    assert sign_in(client, "bob", PASSWORD).status_code == 200


def test_successes_and_other_routes_do_not_count(harness: Harness, bob: None) -> None:
    client = make_app(harness, Clock())
    for _ in range(30):
        assert sign_in(client, "bob", PASSWORD).status_code == 200
    for _ in range(30):  # 401s on another route, and 422s on this one, are not sign-in failures
        assert client.get("/auth/me").status_code == 401
        assert client.post("/auth/sign-in", json={}).status_code == 422
    assert sign_in(client, "bob", PASSWORD).status_code == 200


def test_locked_and_disabled_answers_count_like_bad_passwords(harness: Harness, bob: None) -> None:
    client = make_app(harness, Clock(), rate_limit_failures=8)
    for _ in range(5):
        assert sign_in(client, "bob", WRONG).status_code == 401
    for _ in range(3):
        assert sign_in(client, "bob", PASSWORD).status_code == 423  # locked: counted
    assert sign_in(client, "bob", PASSWORD).status_code == 429


def test_the_forwarded_header_is_ignored_unless_a_proxy_is_trusted(
    harness: Harness, bob: None
) -> None:
    client = make_app(harness, Clock(), rate_limit_failures=3)
    for n in range(3):  # the client names a new address each time: it must not help
        sign_in(client, f"name{n}", WRONG, headers={"X-Forwarded-For": f"9.9.9.{n}"})
    spoofed = sign_in(client, "bob", PASSWORD, headers={"X-Forwarded-For": "8.8.8.8"})
    assert spoofed.status_code == 429


def test_behind_a_trusted_proxy_each_client_address_has_its_own_budget(
    harness: Harness, bob: None
) -> None:
    client = make_app(
        harness, Clock(), rate_limit_failures=3, trusted_proxy_header="X-Forwarded-For"
    )
    attacker = {"X-Forwarded-For": "198.51.100.7"}
    for n in range(3):
        sign_in(client, f"name{n}", WRONG, headers=attacker)
    assert sign_in(client, "bob", PASSWORD, headers=attacker).status_code == 429
    other = {"X-Forwarded-For": "203.0.113.20"}  # a different person behind the same proxy
    assert sign_in(client, "bob", PASSWORD, headers=other).status_code == 200
    # a client cannot launder its address by prepending: only the proxy's last entry counts
    forged = {"X-Forwarded-For": "203.0.113.99, 198.51.100.7"}
    assert sign_in(client, "bob", PASSWORD, headers=forged).status_code == 429


def test_a_blocked_source_does_not_grow_its_own_count(harness: Harness, bob: None) -> None:
    clock = Clock()
    client = make_app(harness, clock, rate_limit_failures=3)
    for n in range(3):
        sign_in(client, f"name{n}", WRONG)
    for _ in range(50):
        assert sign_in(client, "bob", WRONG).status_code == 429
    clock.now += 601
    assert sign_in(client, "bob", PASSWORD).status_code == 200  # 50 refusals left no debt


def test_the_proxy_header_comes_from_the_environment() -> None:
    assert ApiSettings.from_env({"TL_TRUSTED_PROXY_HEADER": "X-Forwarded-For"}).trusted_proxy_header
    assert ApiSettings.from_env({}).trusted_proxy_header is None
    assert ApiSettings.from_env({"TL_TRUSTED_PROXY_HEADER": ""}).trusted_proxy_header is None


def test_defaults_are_twenty_in_ten_minutes() -> None:
    cfg = ApiSettings()
    assert (cfg.rate_limit_failures, cfg.rate_limit_window_s) == (20, 600.0)
