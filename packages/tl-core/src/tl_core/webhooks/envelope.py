"""The CloudEvents 1.0 envelope of a webhook (brief 18.3) and the payload modes.

``build_envelope`` is pure: it turns an :class:`OutboxRow` into the dict that is serialised and
signed. The caller (the dispatcher) supplies what needs the database: the subject's immediate links
and its record projection. The LinkML model is ``CloudEvent`` in ``schema/core/integration.yaml``;
the per-event-type JSON Schemas the contract tests check against come from the catalog generator.

Payload modes (per subscription):

* ``thin``: envelope and ``data.origin`` only. The receiver fetches what it needs.
* ``delta``: thin plus ``data.changes``, ``data.links`` (immediate links) and ``data.detail`` (the
  ledger
  payload; an addition to the brief's example, because events such as ``File.Uploaded`` or
  ``Workflow.Transitioned`` carry facts that are not field changes).
* ``full``: delta plus ``data.record``, the record projection as of delivery preparation. It carries
  its
  own ``version``, which can be newer than ``data.origin.version`` when the record moved on first.

Every mode carries the originating record URI, ``tlseq`` and ``tlstreamversion`` (brief 18.3).

**Confidentiality hook.** Brief 18.3: a record under restricted confidentiality only ever emits
``thin`` payloads, and only to subscriptions whose owner is cleared. Confidentiality classes are not
modelled before Phase 1, so :class:`ConfidentialityPolicy` is a seam: ``forced_mode`` may lower the
requested mode per row, and ``allows`` may veto delivery to a subscription. The default policy
allows everything and changes nothing. A real policy must lower ``full`` and ``delta`` to ``thin``
for restricted rows; the dispatcher applies it before building any body.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, Protocol

from tl_core.webhooks.rows import OutboxRow
from tl_core.webhooks.uris import UriConfig, ce_type, urn

PayloadMode = Literal["thin", "delta", "full"]
PAYLOAD_MODES: tuple[PayloadMode, ...] = ("thin", "delta", "full")
_RANK = {"thin": 0, "delta": 1, "full": 2}


class ConfidentialityPolicy(Protocol):
    """Decides what a row may carry and to whom (see the module docstring)."""

    def forced_mode(self, row: OutboxRow, requested: PayloadMode) -> PayloadMode:
        """The mode to use for ``row``: ``requested`` or a lower one. Never raise it."""
        ...

    def allows(self, row: OutboxRow, owner: str) -> bool:
        """Whether a subscription owned by ``owner`` may receive ``row`` at all."""
        ...


class OpenPolicy:
    """No restricted rows exist yet: allow everything, change nothing."""

    def forced_mode(self, row: OutboxRow, requested: PayloadMode) -> PayloadMode:
        return requested

    def allows(self, row: OutboxRow, owner: str) -> bool:
        return True


def effective_mode(policy: ConfidentialityPolicy, row: OutboxRow, requested: str) -> PayloadMode:
    """``requested`` after the policy; refuses a policy that raises the mode."""
    if requested not in _RANK:
        raise ValueError(f"unknown payload mode: {requested!r}")
    asked: PayloadMode = requested  # type: ignore[assignment]
    forced = policy.forced_mode(row, asked)
    if _RANK[forced] > _RANK[asked]:
        raise ValueError("a confidentiality policy may lower the payload mode, never raise it")
    return forced


def rfc3339(stamp: str) -> str:
    """``2026-10-09T03:14:07.000000+00:00`` becomes ``2026-10-09T03:14:07.000000Z``."""
    moment = datetime.fromisoformat(stamp)
    return moment.isoformat(timespec="microseconds").replace("+00:00", "Z")


def build_envelope(
    row: OutboxRow,
    mode: PayloadMode,
    uris: UriConfig,
    *,
    links: Sequence[Mapping[str, Any]] = (),
    record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The envelope for ``row`` in ``mode``.

    ``links`` are the subject's immediate links as ``{"rel", "id", "type", "key"}`` (``id`` a bare
    record id); they are rendered with URIs. ``record`` is the projection for ``full`` mode.
    """
    origin_raw = row.data.get("origin", {})
    version = row.subject_version if row.subject_version is not None else row.stream_version
    origin: dict[str, Any] = {
        "id": urn(row.subject_id),
        "key": origin_raw.get("key"),
        "type": origin_raw.get("type"),
        "uri": uris.record_uri(
            row.scope, origin_raw.get("type"), origin_raw.get("key"), row.subject_id, version
        ),
        "version": version,
        "api": uris.api_url(row.scope, row.subject_id),
    }
    data: dict[str, Any] = {"origin": origin}
    if mode in ("delta", "full"):
        data["changes"] = dict(row.data.get("changes", {}))
        data["links"] = [_render_link(link, row, uris) for link in links]
        data["detail"] = dict(row.data.get("detail", {}))
    if mode == "full":
        data["record"] = None if record is None else dict(record)
    return {
        "specversion": "1.0",
        "id": row.event_id,
        "source": uris.source(row.scope),
        "type": ce_type(row.event_type, row.schema_version),
        "time": rfc3339(row.recorded_at),
        "subject": urn(row.subject_id),
        "dataschema": uris.dataschema(row.event_type, row.schema_version),
        "datacontenttype": "application/json",
        "tlseq": row.seq,
        "tlstreamversion": row.stream_version,
        "tlcorrelationid": row.correlation_id,
        "tlactor": row.actor,
        "data": data,
    }


def _render_link(link: Mapping[str, Any], row: OutboxRow, uris: UriConfig) -> dict[str, Any]:
    other = link.get("id")
    return {
        "rel": link["rel"],
        "id": None if other is None else urn(str(other)),
        "type": link.get("type"),
        "key": link.get("key"),
        "uri": None
        if other is None
        else uris.record_uri(row.scope, link.get("type"), link.get("key"), str(other)),
    }


def to_body(envelope: Mapping[str, Any]) -> str:
    """The exact text that is signed and sent: canonical JSON (sorted keys, no spaces, UTF-8)."""
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
