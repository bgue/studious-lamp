"""Turn form edits into commands and send them (brief 6.3 layer-aware paths, 10.2 forms).

This is plumbing between widgets and `ClientInterface`, not a rule engine: the schema rules live
in the pset services. A form collects ``edits`` keyed by `FieldMeta.path` (only changed fields; a
cleared field is ``None``) and calls `save_record_edits`. Edits are grouped into one
`SetPsetValues` per (pset, layer), because a command carries one pset and one layer, and the
record version is chained from command to command. If a command fails, earlier ones stay applied;
the outcome says which.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from tl_core.services.commands import UpdateRecord
from tl_core.services.psets import SetPsetValues
from tl_schema.forms import FieldMeta, FormMetadata

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS
from tl_tui.paths import relative_key

WritableLayer = Literal["standard", "custom", "project"]
WRITABLE_LAYERS: tuple[WritableLayer, ...] = ("standard", "custom", "project")
CORE_PATHS = ("title", "description")


@dataclass(frozen=True)
class PsetBatch:
    """One `SetPsetValues` worth of edits: keys are relative to the pset (``x.`` kept)."""

    pset: str
    layer: WritableLayer
    values: dict[str, Any]


@dataclass
class SaveOutcome:
    """Result of `save_record_edits`. ``error`` is ``None`` when everything was applied."""

    version: int
    applied: list[str] = field(default_factory=lambda: [])
    failed: str | None = None
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def pset_batches(meta: FormMetadata, edits: dict[str, Any]) -> list[PsetBatch]:
    """Group pset ``edits`` by (pset, layer) in metadata order.

    Raises ``ValueError`` for a path that is not a pset field of ``meta``, a read-only field, or
    a layer users cannot write (core, enrichment, source).
    """
    fields: dict[str, tuple[str, FieldMeta]] = {
        f.path: (group.name, f) for group in meta.psets for f in group.fields
    }
    order = {path: index for index, path in enumerate(fields)}
    chosen: dict[tuple[str, WritableLayer], dict[str, Any]] = {}
    for path in sorted((p for p in edits if p not in CORE_PATHS), key=lambda p: order.get(p, -1)):
        if path not in fields:
            raise ValueError(f"{path!r} is not a pset field of {meta.record_type}")
        pset, fld = fields[path]
        if fld.readonly or fld.layer not in WRITABLE_LAYERS:
            raise ValueError(f"{path!r} is read-only (layer {fld.layer})")
        layer = cast(WritableLayer, fld.layer)
        chosen.setdefault((pset, layer), {})[relative_key(path, pset)] = edits[path]
    return [PsetBatch(pset, layer, values) for (pset, layer), values in chosen.items()]


def save_record_edits(
    client: ClientInterface,
    *,
    scope: str,
    actor: str,
    record: dict[str, Any],
    meta: FormMetadata,
    edits: dict[str, Any],
    source: str = "tui",
) -> SaveOutcome:
    """Send core edits as one `UpdateRecord`, then pset edits as chained `SetPsetValues`.

    Validation of the edits against the paths happens before anything is sent, so a bad path
    changes nothing. Service failures (``CLIENT_ERRORS``) stop the sequence and are returned.
    """
    batches = pset_batches(meta, edits)
    outcome = SaveOutcome(version=record["version"])
    core = {p: edits[p] for p in CORE_PATHS if p in edits}
    if core:
        try:
            result = client.update_record(
                UpdateRecord(
                    actor=actor,
                    source=source,
                    scope=scope,
                    stream_id=record["id"],
                    expected_version=outcome.version,
                    changes=core,
                )
            )
        except CLIENT_ERRORS as exc:
            outcome.failed, outcome.error = "core", exc
            return outcome
        outcome.version = result.version
        outcome.applied.append("core")
    for batch in batches:
        label = f"{batch.pset}/{batch.layer}"
        try:
            result = client.set_pset_values(
                SetPsetValues(
                    actor=actor,
                    source=source,
                    scope=scope,
                    stream_id=record["id"],
                    expected_version=outcome.version,
                    pset=batch.pset,
                    layer=batch.layer,
                    values=batch.values,
                )
            )
        except CLIENT_ERRORS as exc:
            outcome.failed, outcome.error = label, exc
            return outcome
        outcome.version = result.version
        outcome.applied.append(label)
    return outcome
