"""Egress policy: the SSRF defence of outbound webhooks (brief 18.4, 30.5).

The setting ``webhooks.egress.allowlist`` feeds :class:`EgressPolicy`.

Every attempt resolves the target host **once**, checks every address it returned and then connects
to that exact address (DNS pinning), so a hostname that changes its answer between check and connect
(DNS rebinding) cannot reach an internal address.

Rules:

* By default only globally routable addresses are allowed. Private (10/8, 172.16/12, 192.168/16,
  fc00::/7),
  loopback, link-local (including the cloud metadata address 169.254.169.254), carrier-grade NAT,
  multicast, reserved and unspecified addresses are refused. An IPv4-mapped IPv6 address is judged
  as the
  IPv4 address it wraps.
* The **allow-list** (``webhooks.egress.allowlist``, default empty; "dangerous to widen") names
  hosts that
  may resolve to refused ranges: a host name, ``host:port``, an IP address or a CIDR network. It
  never
  needs to name public hosts.
* The scheme must be ``https``. ``http`` is accepted only for an allow-listed host, which is how the
  dev
  receiver on 127.0.0.1 is reached in dev and tests.
* A URL with credentials, a fragment, or no host is refused. Redirects are never followed (the
  transport's job), so a 3xx is a failed attempt.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from tl_core.webhooks.rows import as_list

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
SETTING_ALLOWLIST = "webhooks.egress.allowlist"

#: Resolve ``(host, port)`` to address strings. Replaced in tests.
Resolver = Callable[[str, int], list[str]]


class EgressDenied(Exception):
    """The target is not allowed. The delivery is dead-lettered (``egress_denied``), not retried."""


class ResolutionFailed(Exception):
    """DNS gave no answer. Treated as a failed attempt and retried."""


def system_resolver(host: str, port: int) -> list[str]:
    """Addresses from the system resolver, in its order, without duplicates."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ResolutionFailed(f"cannot resolve {host}") from exc
    seen: dict[str, None] = {}
    for info in infos:
        seen.setdefault(str(info[4][0]), None)
    return list(seen)


@dataclass(frozen=True)
class ResolvedTarget:
    """A checked destination: connect to ``ip``, present ``host`` in ``Host`` and SNI."""

    scheme: Literal["http", "https"]
    host: str
    port: int
    ip: str
    path_and_query: str

    @property
    def host_header(self) -> str:
        default = 443 if self.scheme == "https" else 80
        host = f"[{self.host}]" if ":" in self.host else self.host
        return host if self.port == default else f"{host}:{self.port}"


def _normalise(address: str) -> IpAddress:
    parsed = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        return parsed.ipv4_mapped
    return parsed


_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")
_TEREDO = ipaddress.ip_network("2001::/32")
_SIX_TO_FOUR = ipaddress.ip_network("2002::/16")


def is_public(address: str) -> bool:
    """Whether the address is globally routable (and so allowed without an allow-list entry).

    IPv6 forms that wrap an IPv4 address are judged by the address inside: IPv4-mapped
    (``::ffff:a.b.c.d``), NAT64 (``64:ff9b::/96``) and 6to4 (``2002::/16``). Local-use NAT64
    (``64:ff9b:1::/48``) and Teredo (``2001::/32``) are refused: they tunnel to addresses we
    cannot see.
    """
    parsed = _normalise(address)
    if isinstance(parsed, ipaddress.IPv6Address):
        if parsed in _NAT64_LOCAL or parsed in _TEREDO:
            return False
        if parsed in _NAT64:
            return _is_public_v4(ipaddress.IPv4Address(parsed.packed[-4:]))
        if parsed in _SIX_TO_FOUR:
            return _is_public_v4(ipaddress.IPv4Address(parsed.packed[2:6]))
    return parsed.is_global and not parsed.is_multicast


def _is_public_v4(inner: ipaddress.IPv4Address) -> bool:
    return inner.is_global and not inner.is_multicast


@dataclass(frozen=True)
class EgressPolicy:
    allowlist: tuple[str, ...] = ()
    resolver: Resolver = system_resolver

    @staticmethod
    def from_settings(
        settings: dict[str, object], *, resolver: Resolver = system_resolver
    ) -> EgressPolicy:
        raw = settings.get(SETTING_ALLOWLIST, [])
        entries = tuple(str(item) for item in as_list(raw)) if isinstance(raw, list) else ()
        return EgressPolicy(entries, resolver)

    def _entries(self) -> tuple[set[str], set[str], list[IpNetwork]]:
        hosts: set[str] = set()
        host_ports: set[str] = set()
        networks: list[IpNetwork] = []
        for entry in self.allowlist:
            text = entry.strip().lower()
            if not text:
                continue
            try:
                networks.append(ipaddress.ip_network(text, strict=False))
                continue
            except ValueError:
                pass
            (host_ports if ":" in text and not text.startswith("[") else hosts).add(text)
        return hosts, host_ports, networks

    def is_allowlisted(self, host: str, port: int, addresses: Iterable[str] = ()) -> bool:
        """Whether the host (by name, ``host:port``, literal IP or CIDR) is explicitly allowed."""
        hosts, host_ports, networks = self._entries()
        name = host.lower()
        if name in hosts or f"{name}:{port}" in host_ports:
            return True
        candidates = [_normalise(a) for a in ([name] if _is_ip(name) else addresses)]
        return bool(candidates) and all(
            any(addr in network for network in networks) for addr in candidates
        )

    def check(self, url: str) -> ResolvedTarget:
        """Validate ``url`` and resolve it once. Raises :class:`EgressDenied` or
        :class:`ResolutionFailed`."""
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError as exc:
            raise EgressDenied("the target URL is not valid") from exc
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").lower()
        if scheme not in ("http", "https") or not host:
            raise EgressDenied("the target must be an http(s) URL with a host")
        if parts.username is not None or parts.password is not None or parts.fragment:
            raise EgressDenied("the target URL must not carry credentials or a fragment")
        port = port or (443 if scheme == "https" else 80)
        addresses = [host] if _is_ip(host) else self.resolver(host, port)
        if not addresses:
            raise ResolutionFailed(f"cannot resolve {host}")
        allowed = self.is_allowlisted(host, port, addresses)
        if scheme == "http" and not allowed:
            raise EgressDenied("plain http is only allowed for allow-listed hosts")
        if not allowed:
            for address in addresses:
                if not is_public(address):
                    raise EgressDenied(f"{host} resolves to a non-public address")
        path = parts.path or "/"
        return ResolvedTarget(
            scheme="https" if scheme == "https" else "http",
            host=host,
            port=port,
            ip=str(_normalise(addresses[0])),
            path_and_query=path + (f"?{parts.query}" if parts.query else ""),
        )


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return False
    return True
