"""The egress allow-list setting cannot be used to lift the whole SSRF guard (P0-I8 review)."""

from __future__ import annotations

import pytest
from tl_core.services.errors import InvalidSettingValueError
from tl_core.settings.checks import check_egress_entry
from tl_core.settings.registry import get_definition
from tl_core.settings.values import normalise
from tl_core.webhooks.egress import EgressDenied, EgressPolicy, always_refused


@pytest.mark.parametrize(
    "entry",
    [
        "hub.example.com",
        "Hub.Example.COM",
        "hub.example.com:8443",
        "localhost",
        "127.0.0.1",
        "127.0.0.1:9000",
        "::1",
        "10.0.0.0/8",
        "192.168.10.0/24",
        "10.1.2.3/32",
        "fd12:3456::/32",
        "2001:db8::/32",
    ],
)
def test_a_partner_host_an_address_or_a_network_range_is_accepted(entry: str) -> None:
    check_egress_entry(entry)
    assert normalise(get_definition("webhooks.egress.allowlist"), [entry]) == [entry]


@pytest.mark.parametrize(
    ("entry", "why"),
    [
        ("0.0.0.0/0", "covers too much"),
        ("::/0", "covers too much"),
        ("10.0.0.0/7", "covers too much"),
        ("fd00::/15", "covers too much"),
        ("169.254.169.254", "never allowed"),
        ("169.254.0.0/16", "never allowed"),
        ("169.254.169.254/32", "never allowed"),
        ("169.254.169.254:80", "never allowed"),
        ("fe80::1", "never allowed"),
        ("fe80::/10", "covers too much|never allowed"),
        ("fd00:ec2::254", "never allowed"),
        ("100.100.100.200", "never allowed"),
        ("0.0.0.0", "never allowed"),
        ("::", "never allowed"),
        ("::ffff:169.254.169.254", "never allowed"),
        ("64:ff9b::a9fe:a9fe", "never allowed"),
        ("2002::/16", "tunnels"),
        ("2002:0808::/32", "tunnels"),
        ("2001::/32", "tunnels"),
        ("2001:0:4136:e378::1", "tunnels"),
        ("64:ff9b::/96", "never allowed|tunnels"),
        ("64:ff9b:1::/48", "tunnels"),
        ("metadata.google.internal", "metadata service"),
        ("metadata", "metadata service"),
        ("https://hub.example.com", "port"),
        ("hub.example.com/path", "not a host"),
        ("a b", "not a host"),
        ("-bad.example.com", "not a host"),
        ("[::1]:80", "port|not a host"),
        ("hub.example.com:0", "port"),
        ("hub.example.com:99999", "port"),
        ("hub.example.com:http", "port"),
        ("a:b:c", "port"),
        ("", "non-empty"),
        ("   ", "non-empty"),
    ],
)
def test_an_entry_that_would_lift_the_guard_for_everything_is_refused(entry: str, why: str) -> None:
    with pytest.raises(ValueError, match=why):
        check_egress_entry(entry)
    with pytest.raises(InvalidSettingValueError):
        normalise(get_definition("webhooks.egress.allowlist"), [entry])


def test_a_non_text_entry_is_refused() -> None:
    with pytest.raises(InvalidSettingValueError):
        normalise(get_definition("webhooks.egress.allowlist"), [3])


def test_one_bad_entry_refuses_the_whole_list() -> None:
    defn = get_definition("webhooks.egress.allowlist")
    with pytest.raises(InvalidSettingValueError, match="169.254"):
        normalise(defn, ["hub.example.com", "169.254.169.254"])


# --- the engine's own guard does not trust an allow-list for these addresses --------------------


@pytest.mark.parametrize(
    "address",
    [
        "169.254.169.254",
        "169.254.1.1",
        "fe80::1",
        "fe80::1%eth0",
        "fd00:ec2::254",
        "100.100.100.200",
        "0.0.0.0",
        "::",
        "::ffff:169.254.169.254",
        "64:ff9b::a9fe:a9fe",
        "2002:a9fe:a9fe::1",
    ],
)
def test_the_metadata_and_link_local_addresses_are_always_refused(address: str) -> None:
    assert always_refused(address) is True


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "10.0.0.7", "93.184.216.34", "100.64.0.1"])
def test_other_addresses_are_not_always_refused(address: str) -> None:
    assert always_refused(address) is False


@pytest.mark.parametrize("entry", ["169.254.169.254", "169.254.0.0/16", "fe80::/10", "0.0.0.0/0"])
def test_an_allowed_name_or_address_does_not_reach_the_metadata_service(entry: str) -> None:
    policy = EgressPolicy((entry, "metadata.test"), lambda host, port: ["169.254.169.254"])
    for url in ("http://169.254.169.254/latest/meta-data", "https://metadata.test/"):
        with pytest.raises(EgressDenied, match="never reachable"):
            policy.check(url)


def test_loopback_stays_reachable_when_it_is_allowed() -> None:
    policy = EgressPolicy(("127.0.0.1",), lambda host, port: ["127.0.0.1"])
    assert policy.check("http://127.0.0.1:9000/hook").ip == "127.0.0.1"
