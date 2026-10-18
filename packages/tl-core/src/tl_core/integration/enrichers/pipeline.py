"""Running an enricher on one record and deciding what happens to its values (brief §18.9; D6).

``run_enricher`` is the one path every trigger shares (the dispatcher following the ledger, and
``RunEnricher`` on one record): it builds the read-only subject, asks the plugin, and turns each
proposed value into an ``Enrichment.Proposed`` event on a stream of its own, by the enricher's
service actor with the source ``enricher:<name>@<code_version>``. What happens next is the
property's policy:

* ``shadow``: stored and shown to admins and the evaluation report only; never accepted.
* ``propose`` (the default): waits in the review queue for a person.
* ``auto``: a value at or above the threshold is accepted at once (``Enrichment.Accepted`` with
  ``automatic``) and written to the layer; a lower one waits like ``propose``.

A newer value for the same property replaces an open one (the old one is ``Rejected`` by the
service actor); the same value again, a value already in the layer, and a value a person rejected
are not proposed twice. A plugin that raises, answers ``failed`` or proposes a property it did not
declare produces nothing for that value. A suggested link is a ``Link.Suggested`` with the link
source ``enricher``, for a person to accept or decline.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

from tl_core.integration.contract import (
    ENRICHMENT_PSET_PREFIX,
    AutomationAccess,
    Enricher,
    EnrichmentFile,
    EnrichmentInput,
    EnrichmentSubject,
    ProposedValue,
    RecordRef,
)
from tl_core.integration.enrichers.layer import write_enrichment_layer
from tl_core.integration.enrichers.service import EnricherProperty
from tl_core.integration.errors import IntegrationNotFoundError, IntegrationStateError
from tl_core.integration.streams import (
    ENRICHMENT_ACCEPTED,
    ENRICHMENT_PROPOSED,
    ENRICHMENT_REJECTED,
    ENRICHMENT_STREAM_TYPE,
)
from tl_core.ledger import Event, NewEvent
from tl_core.services.errors import ServiceError
from tl_core.services.links import SuggestLink, handle_suggest_link
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid
from tl_core.webhooks.base import iso_z
from tl_core.webhooks.filters import WebhookFilter
from tl_core.webhooks.rows import as_list, as_object, dumps, load_json

log = logging.getLogger(__name__)

_KINDS: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "boolean": (bool,),
    "list": (list,),
}


@dataclass(frozen=True)
class StoredEnricher:
    """A row of ``cur_enricher`` as the engine needs it."""

    enricher_id: str
    name: str
    scope: str
    version: int
    code_version: str
    when: WebhookFilter
    properties: dict[str, EnricherProperty]
    service_actor: str
    access: AutomationAccess
    enabled: bool
    enabled_from_seq: int
    integration_app: str | None

    @property
    def source(self) -> str:
        return f"enricher:{self.name}@{self.code_version}"


@dataclass
class RunStats:
    """What one run did. ``skipped`` counts values that were not proposed (see the log)."""

    proposed: int = 0
    auto_accepted: int = 0
    shadow: int = 0
    replaced: int = 0
    skipped: int = 0
    links: int = 0
    failed: int = 0

    def add(self, other: RunStats) -> None:
        self.proposed += other.proposed
        self.auto_accepted += other.auto_accepted
        self.shadow += other.shadow
        self.replaced += other.replaced
        self.skipped += other.skipped
        self.links += other.links
        self.failed += other.failed


_COLUMNS = (
    "e.enricher_id, e.name, e.scope, e.version, e.code_version, e.when_json, e.properties_json, "
    "e.service_actor, e.access, e.enabled, e.enabled_from_seq, e.integration_app"
)
_LIVE = (
    "e.enabled = :on AND (e.integration_app IS NULL OR e.integration_app IN "
    "(SELECT a.name FROM cur_integration_app a WHERE a.enabled = :on))"
)


def stored_enricher(row: Any) -> StoredEnricher:
    properties = [
        EnricherProperty.model_validate(p) for p in as_list(load_json(row["properties_json"]))
    ]
    return StoredEnricher(
        enricher_id=row["enricher_id"],
        name=row["name"],
        scope=row["scope"],
        version=int(row["version"]),
        code_version=row["code_version"],
        when=WebhookFilter.from_dict(as_object(load_json(row["when_json"]))),
        properties={p.name: p for p in properties},
        service_actor=row["service_actor"],
        access=row["access"],
        enabled=bool(row["enabled"]),
        enabled_from_seq=int(row["enabled_from_seq"]),
        integration_app=row["integration_app"],
    )


def load_live_enrichers(conn: Connection) -> list[StoredEnricher]:
    """The enabled enrichers whose app (when they have one) is enabled, in name order."""
    found = conn.execute(
        text(f"SELECT {_COLUMNS} FROM cur_enricher e WHERE {_LIVE} ORDER BY e.name"),  # noqa: S608
        {"on": True},
    ).mappings()
    return [stored_enricher(row) for row in found]


def load_live_enricher(conn: Connection, name: str) -> StoredEnricher | None:
    found = (
        conn.execute(
            text(
                f"SELECT {_COLUMNS} FROM cur_enricher e WHERE e.name = :n AND {_LIVE}"  # noqa: S608
            ),
            {"n": name, "on": True},
        )
        .mappings()
        .first()
    )
    return None if found is None else stored_enricher(found)


def in_scope(enricher: StoredEnricher, scope: str) -> bool:
    return enricher.scope == "company" or enricher.scope == scope


# --- the subject ----------------------------------------------------------------------------------

_RECORD_SQL = text(
    "SELECT id, key, type, title, status, psets_json, voided, version, scope "
    "FROM cur_core_record WHERE id = :id"
)
_FILE_SQL = text(
    "SELECT file_id, filename, content_type, size, sha256, report_json FROM cur_files "
    "WHERE record_id = :r AND status = 'available' AND superseded_by IS NULL "
    "ORDER BY uploaded_at DESC, file_id DESC LIMIT 1"
)


def load_subject(conn: Connection, record_id: str) -> EnrichmentSubject | None:
    """What an enricher may read about a record; ``None`` for a record that is gone or voided."""
    row = conn.execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or row.voided:
        return None
    file: EnrichmentFile | None = None
    found = conn.execute(_FILE_SQL, {"r": record_id}).first()
    if found is not None:
        report = as_object(load_json(found.report_json)) if found.report_json else {}
        pages = report.get("page_count")
        title = report.get("title")
        author = report.get("author")
        file = EnrichmentFile(
            file_id=found.file_id,
            filename=found.filename,
            content_type=found.content_type,
            size=int(found.size),
            sha256=found.sha256,
            page_count=pages if isinstance(pages, int) and not isinstance(pages, bool) else None,
            title=title if isinstance(title, str) else None,
            author=author if isinstance(author, str) else None,
        )
    return EnrichmentSubject(
        record=RecordRef(id=row.id, key=row.key, record_type=row.type, version=int(row.version)),
        title=row.title or "",
        status=row.status,
        psets=as_object(load_json(row.psets_json)),
        file=file,
    )


# --- values ---------------------------------------------------------------------------------------


def _kind_ok(kind: str, value: Any) -> bool:
    if kind == "number" and isinstance(value, bool):
        return False
    return isinstance(value, _KINDS[kind])


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _layer_value(subject: EnrichmentSubject, enricher: str, prop: str) -> Any:
    layer = as_object(as_object(subject.psets.get("enrich", {})).get(enricher, {}))
    return layer.get(prop)


_OPEN_SQL = text(
    "SELECT value_id, value_json, enricher_version, acceptance_state, decided_by, version "
    "FROM cur_enrichment_value WHERE target_id = :t AND property_path = :p "
    "AND acceptance_state IN ('proposed', 'shadow', 'rejected')"
)


def _reject_row(
    uow: UnitOfWork,
    row: Any,
    *,
    by: str,
    reason: str,
    scope: str,
    source: str,
    correlation_id: str | None,
    causation_id: str | None,
) -> Event:
    result = uow.append(
        stream_id=row["value_id"],
        stream_type=ENRICHMENT_STREAM_TYPE,
        scope=scope,
        expected_version=int(row["version"]),
        events=[
            NewEvent(
                event_type=ENRICHMENT_REJECTED,
                payload={"value_id": row["value_id"], "by": by, "reason": reason},
            )
        ],
        actor=by,
        source=source,
        correlation_id=correlation_id or new_ulid(),
        causation_id=causation_id,
    )
    return result.events[0]


def accept_row(
    uow: UnitOfWork,
    row: Any,
    *,
    by: str,
    automatic: bool,
    source: str,
    correlation_id: str | None,
    causation_id: str | None,
) -> list[Event]:
    """Write one stored value into its layer and mark it accepted (``row`` is a mapping of
    ``cur_enrichment_value``). Nothing is appended when the layer refuses."""
    path = str(row["property_path"]).removeprefix(ENRICHMENT_PSET_PREFIX)
    enricher, _, prop = path.partition(".")
    value = None if row["value_json"] is None else load_json(row["value_json"])
    events = write_enrichment_layer(
        uow,
        record_id=str(row["target_id"]),
        scope=str(row["scope"]),
        enricher=enricher,
        values={prop: value},
        actor=by,
        source=source,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    result = uow.append(
        stream_id=row["value_id"],
        stream_type=ENRICHMENT_STREAM_TYPE,
        scope=str(row["scope"]),
        expected_version=int(row["version"]),
        events=[
            NewEvent(
                event_type=ENRICHMENT_ACCEPTED,
                payload={"value_id": row["value_id"], "by": by, "automatic": automatic},
            )
        ],
        actor=by,
        source=source,
        correlation_id=correlation_id or new_ulid(),
        causation_id=causation_id,
    )
    return [*events, *result.events]


def run_enricher(
    uow: UnitOfWork,
    enricher: StoredEnricher,
    plugin: Enricher,
    subject: EnrichmentSubject,
    *,
    now: datetime,
    correlation_id: str | None,
    causation_id: str | None,
) -> tuple[RunStats, list[Event]]:
    """Ask ``plugin`` about ``subject`` and store what it proposes. Returns the stats and events."""
    stats = RunStats()
    events: list[Event] = []
    if not plugin.accepts(subject):
        return stats, events
    try:
        result = plugin.enrich(subject)
    except Exception:  # a plugin must not raise; if it does, it produced nothing
        log.warning("enricher %s raised on a subject; nothing stored", enricher.name)
        stats.failed += 1
        return stats, events
    if result.status != "ok":
        if result.status == "failed":
            stats.failed += 1
        return stats, events
    correlation = correlation_id or new_ulid()
    inputs = [
        EnrichmentInput(
            record=subject.record, file_sha256=None if subject.file is None else subject.file.sha256
        ).model_dump(mode="json")
    ]
    for proposed in result.values:
        _one_value(
            uow, enricher, subject, proposed, inputs, now, correlation, causation_id, stats, events
        )
    for link in result.links:
        _one_link(uow, enricher, subject, link.to_key, link.relation, link.confidence,
                  correlation, causation_id, stats, events)  # fmt: skip
    return stats, events


def _one_value(
    uow: UnitOfWork,
    enricher: StoredEnricher,
    subject: EnrichmentSubject,
    proposed: ProposedValue,
    inputs: list[dict[str, Any]],
    now: datetime,
    correlation: str,
    causation_id: str | None,
    stats: RunStats,
    events: list[Event],
) -> None:
    prop = enricher.properties.get(proposed.property)
    if prop is None or not _kind_ok(prop.kind, proposed.value):
        stats.skipped += 1  # not declared, or not of the declared kind
        return
    scope = uow.conn().execute(_RECORD_SQL, {"id": subject.record.id}).first()
    assert scope is not None
    path = f"{ENRICHMENT_PSET_PREFIX}{enricher.name}.{prop.name}"
    wanted = _canonical(proposed.value)
    if _canonical(_layer_value(subject, enricher.name, prop.name)) == wanted:
        stats.skipped += 1  # the layer already says it
        return
    older: list[Any] = []
    for row in uow.conn().execute(_OPEN_SQL, {"t": subject.record.id, "p": path}).mappings():
        same = (
            row["value_json"] is not None
            and _canonical(load_json(row["value_json"])) == wanted
            and row["enricher_version"] == enricher.code_version
        )
        if row["acceptance_state"] == "rejected":
            if same and not str(row["decided_by"]).startswith("svc:"):
                stats.skipped += 1  # a person said no to exactly this
                return
        elif same:
            stats.skipped += 1  # already waiting
            return
        else:
            older.append(row)
    for row in older:
        events.append(
            _reject_row(
                uow,
                row,
                by=enricher.service_actor,
                reason="replaced by a newer proposal",
                scope=str(scope.scope),
                source=enricher.source,
                correlation_id=correlation,
                causation_id=causation_id,
            )  # fmt: skip
        )
        stats.replaced += 1
    shadow = prop.policy == "shadow"
    value_id = new_ulid()
    payload = {
        "value_id": value_id,
        "target": subject.record.model_dump(mode="json"),
        "property_path": path,
        "value": proposed.value,
        "enricher": enricher.name,
        "enricher_version": enricher.code_version,
        "confidence": proposed.confidence,
        "inputs": inputs,
        "model_ref": None,
        "produced_at": iso_z(now),
        "acceptance_state": "shadow" if shadow else "proposed",
    }
    made = uow.append(
        stream_id=value_id,
        stream_type=ENRICHMENT_STREAM_TYPE,
        scope=str(scope.scope),
        expected_version=0,
        events=[NewEvent(event_type=ENRICHMENT_PROPOSED, payload=payload)],
        actor=enricher.service_actor,
        source=enricher.source,
        correlation_id=correlation,
        causation_id=causation_id,
    )
    events.extend(made.events)
    if shadow:
        stats.shadow += 1
        return
    stats.proposed += 1
    if prop.policy == "auto" and proposed.confidence >= prop.threshold:
        row = {
            "value_id": value_id,
            "target_id": subject.record.id,
            "scope": str(scope.scope),
            "property_path": path,
            "value_json": dumps(proposed.value),
            "version": made.new_version,
        }
        events.extend(
            accept_row(
                uow,
                row,
                by=enricher.service_actor,
                automatic=True,
                source=enricher.source,
                correlation_id=correlation,
                causation_id=causation_id,
            )  # fmt: skip
        )
        stats.auto_accepted += 1


def _one_link(
    uow: UnitOfWork,
    enricher: StoredEnricher,
    subject: EnrichmentSubject,
    to_key: str,
    relation: str,
    confidence: float,
    correlation: str,
    causation_id: str | None,
    stats: RunStats,
    events: list[Event],
) -> None:
    scope = uow.conn().execute(_RECORD_SQL, {"id": subject.record.id}).first()
    assert scope is not None
    target = (
        uow.conn()
        .execute(
            text("SELECT id FROM cur_core_record WHERE key = :k AND scope = :s AND voided = :v"),
            {"k": to_key, "s": scope.scope, "v": False},
        )
        .first()
    )
    if target is None or target.id == subject.record.id:
        stats.skipped += 1
        return
    try:
        made = handle_suggest_link(
            uow,
            SuggestLink(
                actor=enricher.service_actor,
                source=enricher.source,
                scope=str(scope.scope),
                correlation_id=correlation,
                causation_id=causation_id,
                from_id=subject.record.id,
                to_id=target.id,
                relation=relation,
                link_source="enricher",
                confidence=confidence,
            ),  # fmt: skip
            system_source="enricher",
        )
    except ServiceError:
        stats.skipped += (
            1  # unknown relation, declined before, already linked: not an enricher's call
        )
        return
    events.extend(made.events)
    stats.links += 1


def accept_value_by_person(
    uow: UnitOfWork, value_id: str, scope: str, *, by: str, source: str,
    correlation_id: str | None, causation_id: str | None,
) -> list[Event]:  # fmt: skip
    row = _value_row(uow, value_id, scope)
    if row["acceptance_state"] != "proposed":
        raise IntegrationStateError(f"the value is {row['acceptance_state']}, not waiting")
    return accept_row(
        uow, row, by=by, automatic=False, source=source,
        correlation_id=correlation_id, causation_id=causation_id,
    )  # fmt: skip


def reject_value_by_person(
    uow: UnitOfWork, value_id: str, scope: str, *, by: str, reason: str, source: str,
    correlation_id: str | None, causation_id: str | None,
) -> list[Event]:  # fmt: skip
    row = _value_row(uow, value_id, scope)
    if row["acceptance_state"] != "proposed":
        raise IntegrationStateError(f"the value is {row['acceptance_state']}, not waiting")
    return [
        _reject_row(
            uow,
            row,
            by=by,
            reason=reason,
            scope=scope,
            source=source,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )  # fmt: skip
    ]


def _value_row(uow: UnitOfWork, value_id: str, scope: str) -> Any:
    row = (
        uow.conn()
        .execute(text("SELECT * FROM cur_enrichment_value WHERE value_id = :i"), {"i": value_id})
        .mappings()
        .first()
    )
    if row is None or row["scope"] != scope:
        raise IntegrationNotFoundError(f"no enrichment value {value_id} in {scope}")
    return row


__all__ = [
    "RunStats",
    "StoredEnricher",
    "accept_row",
    "accept_value_by_person",
    "in_scope",
    "load_live_enricher",
    "load_live_enrichers",
    "load_subject",
    "reject_value_by_person",
    "run_enricher",
    "stored_enricher",
]
