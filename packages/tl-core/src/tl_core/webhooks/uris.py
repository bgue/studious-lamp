"""Identifier and URI forms of brief 19.1, and the CloudEvents ``type`` naming of brief 18.3."""

from __future__ import annotations

import re
from dataclasses import dataclass

#: ``Record.Created`` becomes ``tl.core.Record.Created.v1`` (module, class, verb, payload version).
EVENT_TYPE_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*\.[A-Z][A-Za-z0-9_]*$")
URN_PREFIX = "urn:tl:"


def urn(record_id: str) -> str:
    """``urn:tl:<ulid>``: the permanent identity of a record (brief 19.1)."""
    return f"{URN_PREFIX}{record_id}"


def ce_type(event_type: str, schema_version: int = 1, *, module: str = "core") -> str:
    """The CloudEvents ``type`` of a ledger event type: ``tl.<module>.<Class>.<Verb>.v<n>``."""
    if EVENT_TYPE_RE.match(event_type) is None:
        raise ValueError(f"not a ledger event type: {event_type!r}")
    return f"tl.{module}.{event_type}.v{schema_version}"


@dataclass(frozen=True)
class UriConfig:
    """Where this installation's URIs point. Phase 0 default: the documentation host.

    ``base`` has no trailing slash. ``company`` is the company segment of resolvable URIs. Both come
    from deployment settings once about:config exists (P0-I8).
    """

    base: str = "https://tl.example.com"
    company: str = "acme"

    def source(self, scope: str) -> str:
        """The CloudEvents ``source`` for a scope: the company, or one project of it."""
        root = f"{self.base}/c/{self.company}"
        if scope == "company":
            return root
        project = scope.removeprefix("project:")
        return f"{root}/p/{project}"

    def record_uri(
        self,
        scope: str,
        record_type: str | None,
        key: str | None,
        record_id: str,
        version: int | None = None,
    ) -> str:
        """Resolvable URI of a record, versioned (``@v7``) when ``version`` is given.

        A record without a key is addressed by its id.
        """
        project = scope.removeprefix("project:") if scope != "company" else None
        head = f"{self.base}/c/{self.company}" + (f"/p/{project}" if project else "")
        segment = key if key else record_id
        uri = f"{head}/r/{record_type or 'core.Record'}/{segment}"
        return f"{uri}@v{version}" if version is not None else uri

    def api_url(self, scope: str, record_id: str) -> str:
        project = scope.removeprefix("project:") if scope != "company" else None
        head = f"{self.base}/api/v1" + (f"/p/{project}" if project else "")
        return f"{head}/records/{record_id}"

    def dataschema(self, event_type: str, schema_version: int = 1) -> str:
        """Catalog URI of the event type's schema."""
        return f"{self.base}/schema/events/{event_type}/{schema_version}"
