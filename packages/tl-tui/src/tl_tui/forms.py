"""Turn form edits into commands and send them (brief 6.3 layer-aware paths, 10.2 forms).

This is plumbing between widgets and `ClientInterface`, not a rule engine: the schema rules live
in the pset services. A form collects ``edits`` keyed by `FieldMeta.path` (only changed fields; a
cleared field is ``None``) and calls `save_record_edits`. Edits are grouped into one
`PsetEdit` per (pset, layer), because an edit part carries one pset and one layer, and sent as one
`EditRecord` with the field changes. The save is atomic: if any part is refused, nothing is saved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from tl_core.services.edit import EditRecord, PsetEdit
from tl_schema.forms import FieldMeta, FormMetadata

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS
from tl_tui.paths import relative_key

WritableLayer = Literal["standard", "custom", "project"]
WRITABLE_LAYERS: tuple[WritableLayer, ...] = ("standard", "custom", "project")
CORE_PATHS = ("title", "description")


@dataclass(frozen=True)
class PsetBatch:
    """One `PsetEdit` worth of edits: keys are relative to the pset (``x.`` kept)."""

    pset: str
    layer: WritableLayer
    values: dict[str, Any]


@dataclass
class SaveOutcome:
    """Result of `save_record_edits`. ``error`` is ``None`` when the whole save was applied.

    ``version`` is the record version after the save (unchanged on failure).
    """

    version: int
    applied: list[str] = field(default_factory=lambda: [])
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
    """Send all edits as one `EditRecord`: every part is saved or none is.

    Validation of the edits against the paths happens before anything is sent, so a bad path
    changes nothing. A service failure (``CLIENT_ERRORS``) is returned in the outcome with nothing
    saved. ``applied`` lists the parts of a successful save (``core``, then ``pset/layer``).
    """
    batches = pset_batches(meta, edits)
    core = {p: edits[p] for p in CORE_PATHS if p in edits}
    outcome = SaveOutcome(version=record["version"])
    try:
        result = client.edit_record(
            EditRecord(
                actor=actor,
                source=source,
                scope=scope,
                stream_id=record["id"],
                expected_version=outcome.version,
                changes=core,
                pset_edits=[PsetEdit(pset=b.pset, layer=b.layer, values=b.values) for b in batches],
            )
        )
    except CLIENT_ERRORS as exc:
        outcome.error = exc
        return outcome
    outcome.version = result.version
    outcome.applied = (["core"] if core else []) + [f"{b.pset}/{b.layer}" for b in batches]
    return outcome
