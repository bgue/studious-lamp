"""The SSRF defence: what the egress policy allows, refuses and pins."""

from __future__ import annotations

import pytest
from tl_core.webhooks.egress import (
    EgressDenied,
    EgressPolicy,
    ResolutionFailed,
    is_public,
)


def policy(mapping: dict[str, list[str]], allow: tuple[str, ...] = ()) -> EgressPolicy:
    def resolve(host: str, port: int) -> list[str]:
        if host not in mapping:
            raise ResolutionFailed(host)
        return mapping[host]

    return EgressPolicy(allow, resolve)


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.1", "172.16.5.4", "192.168.1.1", "127.0.0.1", "127.1.2.3", "169.254.169.254",
        "100.64.0.1", "0.0.0.0", "224.0.0.1", "255.255.255.255", "::1", "fe80::1", "fc00::1",
        "::", "::ffff:10.0.0.1", "::ffff:127.0.0.1", "192.0.2.1", "198.51.100.7",
        "64:ff9b::7f00:1", "64:ff9b::a00:1", "64:ff9b::a9fe:a9fe", "64:ff9b:1::1",
        "64:ff9b:1::808:808",
        "2001::1", "2001:0:4136:e378:8000:63bf:3fff:fdd2", "2002:7f00:1::1", "2002:a00:1::1",
    ],
)  # fmt: skip
def test_non_public_addresses_are_refused(address: str) -> None:
    assert not is_public(address)
    with pytest.raises(EgressDenied):
        policy({"hook.test": [address]}).check("https://hook.test/x")


@pytest.mark.parametrize(
    "address",
    ["8.8.8.8", "93.184.216.34", "2606:4700:4700::1111", "64:ff9b::808:808", "2002:808:808::1"],
)
def test_public_addresses_are_allowed_and_pinned(address: str) -> None:
    target = policy({"hook.test": [address]}).check("https://hook.test:8443/in?x=1")
    assert (target.scheme, target.host, target.port, target.ip) == (
        "https",
        "hook.test",
        8443,
        address,
    )
    assert target.path_and_query == "/in?x=1"
    assert target.host_header == "hook.test:8443"


def test_a_mixed_answer_is_refused_if_any_address_is_private() -> None:
    with pytest.raises(EgressDenied):
        policy({"hook.test": ["8.8.8.8", "10.0.0.5"]}).check("https://hook.test/")


def test_dns_is_asked_exactly_once_per_check() -> None:
    calls: list[tuple[str, int]] = []

    def resolve(host: str, port: int) -> list[str]:
        calls.append((host, port))
        return ["8.8.8.8"]

    EgressPolicy((), resolve).check("https://hook.test/")
    assert calls == [("hook.test", 443)]


def test_ip_literals_are_judged_without_dns() -> None:
    def boom(host: str, port: int) -> list[str]:
        raise AssertionError("no DNS for a literal")

    with pytest.raises(EgressDenied):
        EgressPolicy((), boom).check("https://10.1.2.3/")
    with pytest.raises(EgressDenied):
        EgressPolicy((), boom).check("https://[::1]/")
    assert EgressPolicy((), boom).check("https://8.8.8.8/").ip == "8.8.8.8"


def test_plain_http_needs_an_allowlist_entry() -> None:
    with pytest.raises(EgressDenied):
        policy({"hook.test": ["8.8.8.8"]}).check("http://hook.test/")
    allowed = policy({"hook.test": ["8.8.8.8"]}, ("hook.test",)).check("http://hook.test/")
    assert allowed.scheme == "http" and allowed.port == 80


@pytest.mark.parametrize(
    "entry", ["localhost", "LOCALHOST", "localhost:8099", "127.0.0.1", "127.0.0.0/8", "::1"]
)
def test_the_allowlist_admits_private_targets_by_name_port_ip_or_cidr(entry: str) -> None:
    mapping = {"localhost": ["127.0.0.1"]}
    p = policy(mapping, (entry,))
    url = "http://localhost:8099/hook" if entry != "::1" else "http://[::1]:8099/hook"
    if entry == "::1":
        assert p.check(url).ip == "::1"
    else:
        assert p.check(url).ip == "127.0.0.1"


def test_an_allowlist_entry_for_another_port_or_host_does_not_widen_anything() -> None:
    mapping = {"localhost": ["127.0.0.1"], "other.test": ["10.0.0.1"]}
    with pytest.raises(EgressDenied):
        policy(mapping, ("localhost:9",)).check("http://localhost:8099/")
    with pytest.raises(EgressDenied):
        policy(mapping, ("localhost",)).check("https://other.test/")


@pytest.mark.parametrize(
    "url",
    [
        "ftp://hook.test/", "file:///etc/passwd", "https://", "//hook.test/", "https://u:p@hook.test/",
        "https://hook.test/#frag", "https://hook.test:99999/", "not a url", "",
    ],
)  # fmt: skip
def test_malformed_or_dangerous_urls_are_refused(url: str) -> None:
    with pytest.raises(EgressDenied):
        policy({"hook.test": ["8.8.8.8"]}).check(url)


def test_dns_failure_is_a_retryable_failure_not_a_denial() -> None:
    with pytest.raises(ResolutionFailed):
        policy({}).check("https://missing.test/")


def test_settings_plug_point_reads_the_allowlist() -> None:
    p = EgressPolicy.from_settings({"webhooks.egress.allowlist": ["localhost"]})
    assert p.allowlist == ("localhost",)
    assert EgressPolicy.from_settings({}).allowlist == ()
