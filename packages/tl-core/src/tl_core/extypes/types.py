"""Extension record type registry v0 contracts for P0-I8 (brief §31).

Frozen for the increment: change only by orchestrator decision.

A type package is a directory ``<root>/<namespace>/<Name>/<version>/`` holding ``type.yaml`` (a
LinkML class with ``is_a: ExtensionRecord``), optional ``workflow.yaml``, ``form.yaml``,
``settings.yaml``, ``examples/``, ``README.md``, and ``type.lock``. Throughline stores metadata
only: the registration is a ledger event; the package files stay where they are.

v0 scope (FANOUT D8–D11):
- discovery by ``tl types sync <root>`` and a polling watcher ``tl types watch <root>``; bucket
  events come later;
- storage modes ``managed`` and ``object-backed`` (written through Throughline only);
  ``directory-backed`` instances and external writers at ``incoming/`` come later;
- instances are generic records: ``CreateRecord.record_type = "<namespace>.<Name>"`` for a
  registered, active type. The 03 §7 signature does not change.

Registrations are events on stream type ``core.TypeRegistration``, stream id
``type:<namespace>.<Name>@<version>``, scope ``company``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# TypeRegistration.Registered: TypeRegistration fields (status "active")
TYPE_REGISTERED = "TypeRegistration.Registered"
# TypeRegistration.Quarantined: {type_ref, location_uri, content_hash, report: list[TypeIssue]}
TYPE_QUARANTINED = "TypeRegistration.Quarantined"
# TypeRegistration.Deprecated: {type_ref, reason}
TYPE_DEPRECATED = "TypeRegistration.Deprecated"
# Record.BodyStored: {stream_id, pointer: BodyPointer, previous_hash: str | None}
#   object-backed instances; the body itself is in the object store, never in the ledger.
RECORD_BODY_STORED = "Record.BodyStored"

StorageMode = Literal["managed", "object-backed", "directory-backed"]
TypeStatus = Literal["active", "quarantined", "deprecated"]


class TypeRegistration(BaseModel):
    namespace: str  # "co.acme"
    name: str  # "LiftPlan"
    version: str  # semver "1.2.0"
    type_ref: str  # "co.acme.LiftPlan@1.2.0"
    location_uri: str  # "file:///…/types/co.acme/LiftPlan/1.2.0" (dev); "s3://…" later
    content_hash: str  # sha256 over type.lock's canonical bytes
    owner: str  # actor that registered it
    status: TypeStatus
    storage_mode: StorageMode  # "directory-backed" is refused in v0
    index_fields: list[str]  # slots with tl:index; the query contract (§31.4)
    schema_hash: str  # hash of the compiled class in the effective schema


class TypeIssue(BaseModel):
    kind: Literal[
        "layout",  # missing type.yaml, bad path segments, bad semver
        "lock",  # type.lock missing, or a file hash differs
        "lint",  # LinkML lint error
        "compile",  # does not compile into the effective schema
        "example",  # an examples/ instance does not validate
        "settings",  # settings.yaml invalid or keys outside the namespace
        "conflict",  # same type_ref already registered with a different content hash
        "unsupported",  # e.g. directory-backed storage in v0
    ]
    path: str | None
    detail: str


class BodyPointer(BaseModel):
    uri: str  # object-store key "records/<type>/<id>/<sha256>.json"
    hash: str  # sha256 of the stored bytes (canonical JSON)
    size: int
    schema_hash: str  # TypeRegistration.schema_hash the body validated against


class TypeView(BaseModel):
    registration: TypeRegistration
    seq: int


# Service signatures (implemented in tl_core.extypes; supervisor-built: validator and registry):
#   scan(root: Path) -> list[Path]                      # package directories, sorted
#   validate_package(path: Path, *, provider) -> tuple[TypeRegistration | None, list[TypeIssue]]
#   sync(uow_factory, root: Path, *, actor, source) -> list[TypeView]
#       Registers new or changed packages (one event each), quarantines invalid ones with the
#       report, and is idempotent: an unchanged package appends nothing.
#   list_types(conn, *, status: TypeStatus | None = None) -> list[TypeView]
#   store_body(uow, store: ObjectStore, *, stream_id, body: dict[str, Any], actor, source)
#       -> BodyPointer        # validates, puts the object (write-once by hash), appends
#                             # Record.BodyStored; index fields are copied into psets
#   load_body(conn, store, *, stream_id) -> dict[str, Any]
#       Verifies the hash on read; a mismatch raises BodyHashMismatchError and records the
#       record as quarantined (§31.4) rather than returning the body.
