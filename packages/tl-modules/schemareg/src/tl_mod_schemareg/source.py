"""The registry as the schema provider sees it: published packages, pins, approved waivers.

``LedgerRegistrySource`` implements ``tl_core.schema_provider.RegistrySource`` over the ledger's
current-state tables. The provider asks ``token()`` on every call, so it is cheap: it reads the
newest ``last_seq`` of the three tables and the date, and caches the answer for ``ttl`` seconds
unless this process changed something (``common.changes()``). Another process's publication shows
up within ``ttl``. ``snapshot()`` is read when the token changed.

Whatever goes wrong here (a ledger made before the tables existed, a package whose text no longer
parses, a ledger that is busy) must never take the directory's schema down: the answer is then an
empty state, and a package that does not parse is left out and logged.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import date

from sqlalchemy import text
from tl_core.extypes.registry import UowFactory
from tl_core.schema_provider import RegistryState
from tl_core.util import utcnow
from tl_schema.packages import PackageDoc, WaiverDef
from tl_schema.registry import PackageError, parse_package

from tl_mod_schemareg import common
from tl_mod_schemareg.names import (
    ADOPTION_TABLE,
    IN_FORCE,
    PACKAGE_TABLE,
    WAIVER_APPROVED_STATE,
    WAIVER_TABLE,
)

DEFAULT_TTL_SECONDS = 1.0

log = logging.getLogger("tl_mod_schemareg")
log.addHandler(logging.NullHandler())

_TOKEN_SQL = text(
    f"SELECT (SELECT COALESCE(MAX(last_seq), 0) FROM {PACKAGE_TABLE}) AS p, "
    f"(SELECT COALESCE(MAX(last_seq), 0) FROM {ADOPTION_TABLE}) AS a, "
    f"(SELECT COALESCE(MAX(last_seq), 0) FROM {WAIVER_TABLE}) AS w"
)
_PACKAGES_SQL = text(
    f"SELECT t.package, t.semver, t.content FROM {PACKAGE_TABLE} t "
    "JOIN cur_core_record r ON r.id = t.id "
    f"WHERE r.status IN ({', '.join(repr(s) for s in IN_FORCE)}) ORDER BY t.package, t.semver"
)
_PINS_SQL = text(f"SELECT scope, package, semver FROM {ADOPTION_TABLE} ORDER BY scope, package")
_WAIVERS_SQL = text(
    f"SELECT t.scope, t.path, t.reason, t.approver, t.expires FROM {WAIVER_TABLE} t "
    f"JOIN cur_core_record r ON r.id = t.id WHERE r.status = '{WAIVER_APPROVED_STATE}' "
    "ORDER BY t.scope, t.path, t.number"
)


def _today() -> date:
    return utcnow().date()


class LedgerRegistrySource:
    """Published packages, pins and approved waivers of one ledger. Thread-safe."""

    def __init__(
        self,
        factory: UowFactory,
        *,
        ttl: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = factory
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._token: str | None = None
        self._checked = 0.0
        self._seen_changes = -1

    def token(self) -> str:
        """Changes when the registry changed. Cheap; cached for ``ttl`` seconds."""
        now = self._clock()
        seen = common.changes()
        with self._lock:
            if (
                self._token is not None
                and self._seen_changes == seen
                and now - self._checked < self._ttl
            ):
                return self._token
        token = self._read_token()
        with self._lock:
            self._token, self._checked, self._seen_changes = token, now, seen
        return token

    def _read_token(self) -> str:
        try:
            with self._factory(readonly=True) as uow:
                row = uow.conn().execute(_TOKEN_SQL).one()
                return f"{int(row.p)}:{int(row.a)}:{int(row.w)}:{_today().isoformat()}"
        except Exception as exc:  # noqa: BLE001 - see the module text
            log.debug("schema registry unavailable: %s", exc)
            return "none"

    def snapshot(self) -> RegistryState:
        """The state now. An empty one when the ledger cannot be read."""
        try:
            with self._factory(readonly=True) as uow:
                conn = uow.conn()
                package_rows = conn.execute(_PACKAGES_SQL).all()
                pin_rows = conn.execute(_PINS_SQL).all()
                waiver_rows = conn.execute(_WAIVERS_SQL).all()
        except Exception as exc:  # noqa: BLE001 - see the module text
            log.debug("schema registry unavailable: %s", exc)
            return RegistryState()
        documents: list[PackageDoc] = []
        for row in package_rows:
            try:
                documents.append(
                    parse_package(str(row.content), source=f"{row.package}@{row.semver}")
                )
            except PackageError as exc:
                log.warning(
                    "registry package %s@%s does not parse: %s", row.package, row.semver, exc
                )
        pins: dict[str, dict[str, str]] = {}
        for row in pin_rows:
            pins.setdefault(str(row.scope), {})[str(row.package)] = str(row.semver)
        waivers: dict[str, list[WaiverDef]] = {}
        today = _today()
        for row in waiver_rows:
            try:
                until = date.fromisoformat(str(row.expires))
            except ValueError:
                continue
            if until < today:
                continue  # expired: the evaluator would drop it by date anyway
            waivers.setdefault(str(row.scope), []).append(
                WaiverDef(
                    path=str(row.path),
                    reason=str(row.reason),
                    approver=str(row.approver or "unknown"),
                    expires=until,
                )
            )
        return RegistryState(documents=documents, pins=pins, waivers=waivers)


def schema_source(factory: UowFactory) -> LedgerRegistrySource:
    """The module's schema source factory (``ModuleSpec.schema_source``)."""
    return LedgerRegistrySource(factory)
