"""Extension type behaviour of `FakeClient` (P0-I8), kept apart so `fakes.py` stays readable.

The fake holds `TypeDetail`s built from the real example packages (`schema/fixtures/types`) through
the real compiler, so a screen under test sees the same forms the real client returns. It follows
the real rules where they are cheap: an object-backed type needs a body (`BodyRequiredError`), a
body is validated against the compiled class (`BodyValidationError` with the issue list), an
unknown type is `UnsupportedRecordTypeError`, a stale `expected_version` is `ConcurrencyError`,
and an index field is copied into the record's pset. It simplifies the rest: managed values are
not validated, there is no object store, and no quarantine (`damage` makes a body unreadable).
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from tl_core.extypes.compile import body_issues, compile_type
from tl_core.extypes.errors import (
    BodyHashMismatchError,
    BodyNotAllowedError,
    BodyNotFoundError,
    BodyRequiredError,
    BodyValidationError,
    UnknownTypeError,
)
from tl_core.extypes.forms import type_form
from tl_core.extypes.model import CompiledType
from tl_core.extypes.names import parse_type_ref
from tl_core.extypes.service import (
    BodyStoredOut,
    BodyView,
    TypeDetail,
    TypeSummary,
    summarise,
)
from tl_core.extypes.types import BodyPointer, TypeRegistration, TypeStatus, TypeView
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.errors import (
    RecordNotFoundError,
    RecordVoidedError,
    UnsupportedRecordTypeError,
)

TYPES_ROOT = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "types"


class FakeTypeSupport:
    """Mixed into `FakeClient`; uses its `create_record`, `_records`, `_load`, `_next_event`."""

    def _init_types(self) -> None:
        self.types: dict[str, TypeDetail] = {}
        self._compiled: dict[str, CompiledType] = {}
        self.bodies: dict[str, dict[str, Any]] = {}
        self.damaged: set[str] = set()

    # --- seeding -----------------------------------------------------------------------------

    def add_example_type(
        self, namespace_name: str, *, status: TypeStatus = "active", version: str = "1.0.0"
    ) -> TypeDetail:
        """Register an example package, e.g. ``"co.acme.LiftPlan"``, as the fake's type."""
        namespace, name = namespace_name.rsplit(".", 1)
        coords = parse_type_ref(f"{namespace_name}@{version}")
        compiled, issues = compile_type(TYPES_ROOT / namespace / name / "1.0.0", coords, lint=False)
        assert compiled is not None, issues
        registration = TypeRegistration(
            namespace=namespace,
            name=name,
            version=version,
            type_ref=coords.type_ref,
            location_uri=(TYPES_ROOT / namespace / name / "1.0.0").as_uri(),
            content_hash="0" * 64,
            owner="user:ops",
            status=status,
            storage_mode=compiled.storage_mode,
            index_fields=compiled.index_fields,
            schema_hash=compiled.schema_hash(),
        )
        detail = TypeDetail(
            registration=registration,
            seq=len(self.types) + 1,
            form=type_form(compiled),
            report=[],
            unavailable=None,
        )
        self.types[registration.type_ref] = detail
        self._compiled[registration.type_ref] = compiled
        return detail

    def void(self, record_id: str) -> None:
        """Mark ``record_id`` voided (writes to it are then refused)."""
        self._records[record_id]["voided"] = True  # type: ignore[attr-defined]

    def damage(self, record_id: str) -> None:
        """Make the body of ``record_id`` fail verification on its next read."""
        self.damaged.add(record_id)

    # --- ClientInterface ---------------------------------------------------------------------

    def list_types(self, status: TypeStatus | None = None) -> list[TypeSummary]:
        self.calls.append("list_types")  # type: ignore[attr-defined]
        rows = [d for d in self.types.values() if status is None or d.registration.status == status]
        return [
            summarise(TypeView(registration=d.registration, seq=d.seq))
            for d in sorted(rows, key=lambda d: d.registration.type_ref)
        ]

    def get_type(self, type_ref: str) -> TypeDetail:
        self.calls.append("get_type")  # type: ignore[attr-defined]
        detail = self.types.get(type_ref)
        if detail is None:
            raise UnknownTypeError(f"no registration {type_ref!r}")
        return detail

    def _active(self, type_name: str) -> tuple[TypeDetail, CompiledType]:
        for ref, detail in self.types.items():
            reg = detail.registration
            if f"{reg.namespace}.{reg.name}" == type_name and reg.status == "active":
                return detail, self._compiled[ref]
        raise UnsupportedRecordTypeError(f"no extension type {type_name!r} is registered")

    def create_instance(
        self,
        type_name: str,
        *,
        scope: str,
        title: str,
        key: str | None = None,
        description: str | None = None,
        psets: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        numbering: dict[str, str] | None = None,
    ) -> CommandResult:
        self.calls.append("create_instance")  # type: ignore[attr-defined]
        detail, compiled = self._active(type_name)
        backed = detail.registration.storage_mode == "object-backed"
        if backed and body is None:
            raise BodyRequiredError(f"{type_name} is object-backed: give a body")
        if backed and psets:
            raise BodyNotAllowedError(
                f"{type_name} is object-backed: index fields come from the body"
            )
        if not backed and body is not None:
            raise BodyNotAllowedError(f"{type_name} is managed: its values are psets, not a body")
        if body is not None:
            issues = body_issues(compiled, body)
            if issues:
                raise BodyValidationError(f"the body is not a valid {type_name}", issues)
        result = self.create_record(  # type: ignore[attr-defined]
            CreateRecord(
                actor="user:dev",
                source="tui",
                scope=scope,
                record_type=type_name,
                title=title,
                key=key,
                description=description,
                psets=deepcopy(psets or {}),
                numbering=numbering or {},
            )
        )
        if body is not None:
            self._store(result.stream_id, compiled, body)
        return result

    def _store(self, record_id: str, compiled: CompiledType, body: dict[str, Any]) -> None:
        record = self._records[record_id]  # type: ignore[attr-defined]
        self.bodies[record_id] = deepcopy(body)
        index = {n: body[n] for n in compiled.index_fields if n in body}
        record["psets"][compiled.pset] = index
        self._next_event(record, "Record.BodyStored", {"stream_id": record_id}, "user:dev")  # type: ignore[attr-defined]

    @staticmethod
    def _pointer(record_id: str) -> BodyPointer:
        uri = f"records/x/{record_id}/h.json"
        return BodyPointer(uri=uri, hash="h" * 64, size=1, schema_hash="s" * 64)

    def get_record_body(self, record_id: str) -> BodyView:
        self.calls.append("get_record_body")  # type: ignore[attr-defined]
        if record_id not in self.bodies:
            raise BodyNotFoundError(f"record {record_id!r} has no stored body")
        if record_id in self.damaged:
            raise BodyHashMismatchError(
                f"the stored body of {record_id} does not match its recorded hash: hash differs"
            )
        return BodyView(
            record_id=record_id,
            pointer=self._pointer(record_id),
            body=deepcopy(self.bodies[record_id]),
        )

    def put_record_body(
        self,
        record_id: str,
        *,
        scope: str,
        body: dict[str, Any],
        expected_version: int | None = None,
    ) -> BodyStoredOut:
        self.calls.append("put_record_body")  # type: ignore[attr-defined]
        record = self._records.get(record_id)  # type: ignore[attr-defined]
        if record is None or record["scope"] != scope:
            raise RecordNotFoundError(f"no record {record_id!r} in scope {scope!r}")
        if expected_version is not None:
            self._load(record_id, expected_version)  # type: ignore[attr-defined]
        if record.get("voided"):
            raise RecordVoidedError(f"record {record_id!r} is voided")
        detail, compiled = self._active(record["type"])
        if detail.registration.storage_mode != "object-backed":
            raise BodyNotAllowedError(f"{record['type']} is managed: its values are psets")
        issues = body_issues(compiled, body)
        if issues:
            raise BodyValidationError(f"the body is not a valid {record['type']}", issues)
        self._store(record_id, compiled, body)
        self.damaged.discard(record_id)
        return BodyStoredOut(pointer=self._pointer(record_id), version=int(record["version"]))
