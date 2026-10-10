"""Checks that go beyond a pattern, for the keys that need them (P0-I8 review of S6).

``ITEM_CHECKS`` maps a setting key to a function that raises ``ValueError`` (the message is shown)
for a list item it refuses. ``values.normalise`` runs it for each item of a ``list`` setting,
after the type, the choices and the pattern.

``webhooks.egress.allowlist`` is the one key with a check: every entry lifts the egress guard for a
destination, and one accepted risk must not be able to lift it for everything. An entry must be a
host name, ``host:port``, an IP address or a CIDR range. A range must be at least a /8 (IPv4) or a
/16 (IPv6); link-local and cloud-metadata addresses are never allowed, nor are the names of
metadata services. IPv6 tunnel ranges (6to4, Teredo, NAT64) are refused too.
Loopback stays allowed: the dev receiver, the tests and the demo use it.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from typing import Any

from tl_core.settings.display import shown
from tl_core.webhooks.egress import REFUSED_NAMES, always_refused

MIN_PREFIX_V4 = 8
MIN_PREFIX_V6 = 16
#: IPv6 ranges that tunnel to addresses we cannot see: 6to4, Teredo, NAT64 (well known and local).
TUNNEL_RANGES = tuple(
    ipaddress.IPv6Network(text)
    for text in ("2002::/16", "2001::/32", "64:ff9b::/96", "64:ff9b:1::/48")
)
_HOST = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?")


def check_egress_entry(entry: Any) -> None:
    """Raise ``ValueError`` unless ``entry`` is an acceptable egress allow-list entry."""
    if not isinstance(entry, str) or not entry.strip():
        raise ValueError("an allow-list entry is a non-empty text")
    text = entry.strip().lower()
    try:
        network = ipaddress.ip_network(text, strict=False)
    except ValueError:
        network = None
    if network is not None:
        floor = MIN_PREFIX_V4 if network.version == 4 else MIN_PREFIX_V6
        if network.prefixlen < floor:
            raise ValueError(
                f"{shown(entry)} covers too much: a range must be at least /{floor} "
                f"(an address or a range inside your own network)"
            )
        if always_refused(network):
            raise ValueError(
                f"{shown(entry)} includes link-local or metadata addresses, which are never allowed"
            )
        if isinstance(network, ipaddress.IPv6Network) and any(
            network.overlaps(r) for r in TUNNEL_RANGES
        ):
            raise ValueError(
                f"{shown(entry)} is a 6to4, Teredo or NAT64 range, which tunnels to addresses "
                "that cannot be checked; list the IPv4 address or range instead"
            )
        return
    host, _, port = text.partition(":")
    if port:
        if not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError(f"{shown(entry)}: the port must be a number from 1 to 65535")
    if ":" in port or text.startswith("["):
        raise ValueError(f"{shown(entry)} is not a host, host:port, address or range")
    if not _HOST.fullmatch(host) or len(host) > 253:
        raise ValueError(f"{shown(entry)} is not a host name")
    if host in REFUSED_NAMES:
        raise ValueError(f"{shown(entry)} names a metadata service, which is never allowed")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return
    # host:port whose host is an IP address (an IPv4 literal with a port)
    check_egress_entry(host)


ITEM_CHECKS: dict[str, Callable[[Any], None]] = {
    "webhooks.egress.allowlist": check_egress_entry,
}
