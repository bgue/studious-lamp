"""How an active registration enters the effective schema (brief 27.3, 31; FANOUT D7).

``LedgerExtensionSource`` reads the registrations of a ledger and hands the schema provider one
``PackageDoc`` per usable type: a company package named for the type, holding one pset (named for
the type) that applies to the type's records. The provider composes those documents with the
packages of its directory, so a pset write, a form, the JSON Schema and the conformance evaluator
all see an extension type like any other, and ``CreateRecord.record_type = "<ns>.<Name>"`` finds its
pset. A type whose files are gone or changed is left out (see ``tl_core.extypes.loader``).

``attach(factory)`` is what a process does once, where it opens its ledger: the CLI, the API app,
the MCP server and the embedded TUI. It is safe to call again (the last ledger wins); a process
that never calls it simply has no extension types.

The source asks the database for a cheap token (how many usable registrations, and the highest
``seq`` among them) at most once per ``ttl`` seconds, plus at once after this process registers or
deprecates something (``registry.changes``). Another process's ``tl types sync`` therefore shows
up within ``ttl`` seconds.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from sqlalchemy import text
from tl_schema.packages import PackageDoc

from tl_core.extypes import registry, settings_link
from tl_core.extypes.loader import LoadedType, TypeLoader, default_loader
from tl_core.extypes.types import TypeView
from tl_core.schema_provider import DirectorySchemaProvider, get_provider

DEFAULT_TTL_SECONDS = 1.0

log = logging.getLogger("tl_core.extypes")
log.addHandler(logging.NullHandler())

_TOKEN_SQL = text(
    "SELECT COUNT(*) AS n, COALESCE(MAX(last_seq), 0) AS top "
    "FROM cur_core_type_registration WHERE status IN ('active', 'deprecated')"
)


class LedgerExtensionSource:
    """Registered types of one ledger, as schema documents. Thread-safe."""

    def __init__(
        self,
        factory: registry.UowFactory,
        *,
        loader: TypeLoader | None = None,
        ttl: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = factory
        self._loader = loader if loader is not None else default_loader()
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._token: str | None = None
        self._checked = 0.0
        self._seen_changes = -1
        self._epoch = 0
        self._unavailable: dict[str, str] = {}

    def invalidate(self) -> None:
        """Make the next ``token()`` differ: the provider reloads every type's files."""
        with self._lock:
            self._token = None
            self._epoch += 1

    def token(self) -> str:
        """Changes when the set of usable registrations changes. Cheap; cached for ``ttl``."""
        now = self._clock()
        with self._lock:
            fresh = (
                self._token is not None
                and self._seen_changes == registry.changes()
                and now - self._checked < self._ttl
            )
            if fresh and self._token is not None:
                return self._token
            seen = registry.changes()
        token = self._read_token()
        with self._lock:
            token = f"{token}:{self._epoch}"
            self._token, self._checked, self._seen_changes = token, now, seen
        return token

    def _read_token(self) -> str:
        # Whatever goes wrong here (no table in a ledger made before the registry existed, a
        # ledger that is gone or busy) must never take the core schema down with it: no types.
        try:
            with self._factory(readonly=True) as uow:
                row = uow.conn().execute(_TOKEN_SQL).one()
                return f"{int(row.n)}:{int(row.top)}"
        except Exception as exc:
            log.debug("extension types unavailable: %s", exc)
            return "none"

    def documents(self) -> list[PackageDoc]:
        """One document per type whose files still match its registration, sorted by type name."""
        try:
            with self._factory(readonly=True) as uow:
                views = registry.usable_types(uow.conn())
        except Exception as exc:
            log.debug("extension types unavailable: %s", exc)
            return []
        documents: list[PackageDoc] = []
        unavailable: dict[str, str] = {}
        for view in views:
            loaded = self._loader.load(view.registration)
            if isinstance(loaded, LoadedType):
                documents.append(loaded.document)
            else:
                unavailable[view.registration.type_ref] = loaded.reason
        with self._lock:
            self._unavailable = unavailable
        self._refresh_settings(views)
        return documents

    def refresh_settings(self) -> None:
        """Make the settings registry hold the keys of this ledger's registered types."""
        settings_link.refresh_from_ledger(self._factory, self._loader.verify)

    def _refresh_settings(self, views: list[TypeView]) -> None:
        try:
            settings_link.refresh(views, self._loader.verify)
        except Exception as exc:  # the schema must never fail because a settings key did
            log.warning("extension type settings not refreshed: %s", exc)

    def unavailable(self) -> dict[str, str]:
        """Type ref to the reason, for registered types left out of the schema at the last read."""
        with self._lock:
            return dict(self._unavailable)


def attach(
    factory: registry.UowFactory, *, ttl: float = DEFAULT_TTL_SECONDS
) -> LedgerExtensionSource | None:
    """Make the process schema provider include the registered types of ``factory``'s ledger.

    Returns the source, or ``None`` when the process provider is not a ``DirectorySchemaProvider``
    (a test double): then there is nothing to attach to and extension types stay unknown.
    """
    provider = get_provider()
    if not isinstance(provider, DirectorySchemaProvider):
        return None
    source = LedgerExtensionSource(factory, ttl=ttl)
    provider.attach_extensions(source)
    source.refresh_settings()  # the settings keys of the registered types, before the first read
    return source
