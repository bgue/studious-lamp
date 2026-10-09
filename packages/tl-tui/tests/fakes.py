"""In-memory `ClientInterface` used by every TUI test (P0-I2).

`FakeClient` mimics the embedded client closely enough for screens: the same record envelope keys,
version checks (`ConcurrencyError`), and `Event` objects. Its form metadata and conformance rules
reproduce the brief 6.3 `valve_data` example (company standard pset, project custom section `x.`,
project pset `prj.shutdown_tie_in`, one enrichment pset). Everything is deterministic: ids, times,
and hashes derive from counters, so snapshots do not flake.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from tl_core.ledger import ConcurrencyError, Event
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord
from tl_core.services.errors import DuplicateKeyError, RecordNotFoundError
from tl_core.services.psets import SetPsetValues
from tl_schema.forms import (
    ConformanceIssue,
    ConformanceReport,
    EnumValue,
    FieldMeta,
    FormMetadata,
    PsetGroupMeta,
)

SCOPE = "project:P123"
HASH_V1 = "a91f" + "0" * 56 + "3c"  # shown as #a91f...3c in the record view
_T0 = datetime(2026, 10, 9, 9, 0, 0, tzinfo=UTC)


def _field(path: str, label: str, kind: str, group: str, order: int, **extra: Any) -> FieldMeta:
    base: dict[str, Any] = {
        "path": path,
        "label": label,
        "description": f"{label} (fake metadata)",
        "kind": kind,
        "layer": "standard",
        "group": group,
        "order": order,
    }
    base.update(extra)
    return FieldMeta.model_validate(base)


def valve_form_metadata(effective_schema_hash: str = HASH_V1) -> FormMetadata:
    """Form metadata for the brief 6.3 example as project P123 sees it."""
    material = [
        EnumValue(code="SS316L", label="316L stainless"),
        EnumValue(code="CS", label="Carbon steel"),
        EnumValue(code="SS316L-NACE", label="316L NACE MR0175", crosswalk="SS316L"),
    ]
    valve = PsetGroupMeta(
        name="valve_data",
        label="valve_data",
        package="co.acme.engineering",
        version="3.2.0",
        enforcement="required",
        layer="standard",
        fields=[
            _field(
                "psets.valve_data.size_in",
                "size_in",
                "decimal",
                "valve_data",
                1,
                unit="[in_i]",
                required_in_states=["Design", "Installed"],
                enforcement="required",
            ),
            _field(
                "psets.valve_data.body_material",
                "body_material",
                "enum",
                "valve_data",
                2,
                enum_values=material,
                required_in_states=["Design"],
                enforcement="required",
            ),
            _field(
                "psets.valve_data.fail_action",
                "fail_action",
                "enum",
                "valve_data",
                3,
                enum_values=[
                    EnumValue(code="FC", label="Fail closed"),
                    EnumValue(code="FO", label="Fail open"),
                ],
                enforcement="locked",
            ),
            _field(
                "psets.valve_data.seat_leakage",
                "seat_leakage",
                "string",
                "valve_data",
                4,
                enforcement="advisory",
            ),
            _field(
                "psets.valve_data.x.fat_witness_by",
                "x.fat_witness_by",
                "ref",
                "valve_data",
                5,
                layer="custom",
            ),
            _field(
                "psets.valve_data.x.tie_in_window",
                "x.tie_in_window",
                "string",
                "valve_data",
                6,
                layer="custom",
            ),
        ],
    )
    project = PsetGroupMeta(
        name="prj.shutdown_tie_in",
        label="prj.shutdown_tie_in",
        package="prj.P123",
        version="1.4.0",
        enforcement=None,
        layer="project",
        fields=[
            _field(
                "psets.prj.shutdown_tie_in.window",
                "window",
                "string",
                "prj.shutdown_tie_in",
                1,
                layer="project",
            ),
            _field(
                "psets.prj.shutdown_tie_in.isolation",
                "isolation",
                "string",
                "prj.shutdown_tie_in",
                2,
                layer="project",
            ),
        ],
    )
    enrich = PsetGroupMeta(
        name="enrich.ai_classifier",
        label="enrich.ai_classifier",
        package="enrich.ai_classifier",
        version="0.1.0",
        enforcement=None,
        layer="enrichment",
        fields=[
            _field(
                "psets.enrich.ai_classifier.valve_type",
                "valve_type",
                "string",
                "enrich.ai_classifier",
                1,
                layer="enrichment",
                readonly=True,
            ),
        ],
    )
    return FormMetadata(
        record_type="core.Record",
        effective_schema_hash=effective_schema_hash,
        core_fields=[
            _field("title", "Title", "string", "details", 1, layer="core"),
            _field("description", "Description", "text", "details", 2, layer="core"),
        ],
        psets=[valve, project, enrich],
    )


def get_path(data: dict[str, Any], dotted: str) -> Any:
    """Value at a dotted path inside nested dicts; ``None`` when any step is missing."""
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]  # pyright: ignore[reportUnknownVariableType]
    return node  # pyright: ignore[reportUnknownVariableType]


def set_path(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child  # pyright: ignore[reportUnknownVariableType]
    node[parts[-1]] = value


class FakeClient:
    """Implements `tl_tui.client.ClientInterface` in memory."""

    def __init__(self, scope: str = SCOPE) -> None:
        self.scope = scope
        self.metadata = valve_form_metadata()
        self.calls: list[str] = []  # method names in call order, for assertions
        self.set_pset_commands: list[SetPsetValues] = []
        self._records: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[Event]] = {}
        self._seq = 0
        self._id = 0

    # --- seeding -----------------------------------------------------------------------------

    @classmethod
    def with_valve_example(cls, extra_rows: int = 0) -> FakeClient:
        """Three valve records (conformance ok, warning, nonconformant) plus filler rows."""
        client = cls()
        full = client._seed("FV-1001", "Control valve FCV on 6in discharge", "Design")
        client._apply_psets(
            full,
            "valve_data",
            "standard",
            {
                "size_in": 6.0,
                "body_material": "SS316L",
                "fail_action": "FC",
                "seat_leakage": "IV",
            },
        )
        client._apply_psets(
            full, "valve_data", "custom", {"x.fat_witness_by": "@party:client-acme"}
        )
        client._seed("FV-1002", "Manual valve MV on 4in vent", "Design")
        client._apply_psets(
            client._records_by_key("FV-1002"),
            "valve_data",
            "standard",
            {"size_in": 4.0, "body_material": "CS", "fail_action": "FO"},
        )
        client._seed("FV-1003", "Check valve CV on 2in drain", "Installed")
        for i in range(extra_rows):
            client._seed(f"FV-{2000 + i}", f"Filler valve {i}", "Design")
        return client

    def _records_by_key(self, key: str) -> dict[str, Any]:
        return next(r for r in self._records.values() if r["key"] == key)

    def _next_event(
        self, record: dict[str, Any], event_type: str, payload: dict[str, Any], actor: str
    ) -> Event:
        self._seq += 1
        version = len(self._events.get(record["id"], [])) + 1
        when = _T0 + timedelta(minutes=self._seq)
        digest = hashlib.sha256(f"{self._seq}:{event_type}".encode()).hexdigest()
        event = Event(
            event_type=event_type,
            payload=payload,
            seq=self._seq,
            event_id=f"EV{self._seq:024d}",
            stream_id=record["id"],
            stream_type="core.Record",
            stream_version=version,
            scope=record["scope"],
            actor=actor,
            recorded_at=when,
            effective_at=when,
            correlation_id=f"CO{self._seq:024d}",
            causation_id=None,
            source="tui",
            prev_hash=None,
            hash=digest,
        )
        self._events.setdefault(record["id"], []).append(event)
        record["version"] = version
        record["last_seq"] = self._seq
        record["updated_at"] = when.isoformat()
        return event

    def _seed(self, key: str, title: str, status: str | None) -> dict[str, Any]:
        result = self.create_record(
            CreateRecord(
                actor="user:seed",
                source="tui",
                scope=self.scope,
                record_type="core.Record",
                title=title,
                key=key,
            )
        )
        record = self._records[result.stream_id]
        record["status"] = status
        record["conformance"] = self._report(record).status
        self.calls.clear()
        return record

    def _apply_psets(
        self, record: dict[str, Any], pset: str, layer: str, values: dict[str, Any]
    ) -> Event:
        for rel, value in values.items():
            set_path(record["psets"], f"{pset}.{rel}", value)
        event = self._next_event(
            record,
            "Pset.ValuesSet",
            {
                "pset": pset,
                "layer": layer,
                "values": values,
                "effective_schema_hash": self.metadata.effective_schema_hash,
            },
            "user:seed",
        )
        record["effective_schema_hash"] = self.metadata.effective_schema_hash
        record["conformance"] = self._report(record).status
        return event

    # --- ClientInterface ---------------------------------------------------------------------

    def list_records(
        self,
        scope: str,
        *,
        record_type: str | None = None,
        status: str | None = None,
        include_voided: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.calls.append("list_records")
        rows = [
            r
            for r in self._records.values()
            if r["scope"] == scope
            and (record_type is None or r["type"] == record_type)
            and (status is None or r["status"] == status)
            and (include_voided or not r["voided"])
        ]
        return [deepcopy(r) for r in rows[offset : offset + limit]]

    def get_record(self, scope: str, key: str) -> dict[str, Any] | None:
        self.calls.append("get_record")
        for r in self._records.values():
            if r["scope"] == scope and r["key"] == key:
                return deepcopy(r)
        return None

    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None:
        self.calls.append("get_record_by_id")
        record = self._records.get(record_id)
        return None if record is None else deepcopy(record)

    def history(self, record_id: str) -> list[Event]:
        self.calls.append("history")
        return list(self._events.get(record_id, []))

    def create_record(self, cmd: CreateRecord) -> CommandResult:
        self.calls.append("create_record")
        if any(r["scope"] == cmd.scope and r["key"] == cmd.key for r in self._records.values()):
            raise DuplicateKeyError(f"key {cmd.key!r} is already used in scope {cmd.scope!r}")
        self._id += 1
        record_id = f"REC{self._id:023d}"
        record: dict[str, Any] = {
            "id": record_id,
            "key": cmd.key,
            "type": cmd.record_type,
            "scope": cmd.scope,
            "title": cmd.title,
            "description": cmd.description,
            "status": None,
            "psets": deepcopy(cmd.psets),
            "voided": False,
            "version": 0,
            "last_seq": 0,
            "effective_schema_hash": None,
            "conformance": "ok",
            "created_at": (_T0 + timedelta(minutes=self._seq + 1)).isoformat(),
            "updated_at": "",
        }
        self._records[record_id] = record
        event = self._next_event(
            record,
            "Record.Created",
            {"record_type": cmd.record_type, "key": cmd.key, "title": cmd.title},
            cmd.actor,
        )
        return CommandResult(stream_id=record_id, key=cmd.key, version=1, events=[event])

    def update_record(self, cmd: UpdateRecord) -> CommandResult:
        self.calls.append("update_record")
        record = self._load(cmd.stream_id, cmd.expected_version)
        changes = {f: [record[f], v] for f, v in cmd.changes.items() if record.get(f) != v}
        for field, (_, new) in changes.items():
            record[field] = new
        event = self._next_event(record, "Record.Updated", {"changes": changes}, cmd.actor)
        return CommandResult(
            stream_id=record["id"], key=record["key"], version=record["version"], events=[event]
        )

    def set_pset_values(self, cmd: SetPsetValues) -> CommandResult:
        self.calls.append("set_pset_values")
        self.set_pset_commands.append(cmd)
        record = self._load(cmd.stream_id, cmd.expected_version)
        for rel, value in cmd.values.items():
            set_path(record["psets"], f"{cmd.pset}.{rel}", value)
        event = self._next_event(
            record,
            "Pset.ValuesSet",
            {
                "pset": cmd.pset,
                "layer": cmd.layer,
                "values": cmd.values,
                "effective_schema_hash": self.metadata.effective_schema_hash,
            },
            cmd.actor,
        )
        record["effective_schema_hash"] = self.metadata.effective_schema_hash
        record["conformance"] = self._report(record).status
        return CommandResult(
            stream_id=record["id"], key=record["key"], version=record["version"], events=[event]
        )

    def form_metadata(self, scope: str, record_type: str) -> FormMetadata:
        self.calls.append("form_metadata")
        return self.metadata

    def conformance(self, record_id: str) -> ConformanceReport:
        self.calls.append("conformance")
        record = self._records.get(record_id)
        if record is None:
            raise RecordNotFoundError(f"no record {record_id!r}")
        return self._report(record)

    # --- internals ---------------------------------------------------------------------------

    def _load(self, record_id: str, expected_version: int) -> dict[str, Any]:
        record = self._records.get(record_id)
        if record is None:
            raise RecordNotFoundError(f"no record {record_id!r} in scope {self.scope!r}")
        if record["version"] != expected_version:
            raise ConcurrencyError(
                f"expected version {expected_version}, found {record['version']}"
            )
        return record

    def _report(self, record: dict[str, Any]) -> ConformanceReport:
        """Fake rules: required-in-state missing is nonconformant; advisory missing is a warning."""
        issues: list[ConformanceIssue] = []
        for group in self.metadata.psets:
            for fld in group.fields:
                if fld.readonly:
                    continue
                value = get_path(record["psets"], fld.path.removeprefix("psets."))
                if value in (None, ""):
                    if record["status"] in fld.required_in_states:
                        issues.append(
                            ConformanceIssue(
                                path=fld.path,
                                level="nonconformant",
                                rule="required_in_state",
                                message=f"{fld.label} is required in state {record['status']}",
                            )
                        )
                    elif fld.enforcement == "advisory":
                        issues.append(
                            ConformanceIssue(
                                path=fld.path,
                                level="warning",
                                rule="required_in_state",
                                message=f"{fld.label} is advisory and missing",
                            )
                        )
                elif fld.kind == "enum" and fld.enum_values is not None:
                    codes = {v.code for v in fld.enum_values}
                    if value not in codes:
                        issues.append(
                            ConformanceIssue(
                                path=fld.path,
                                level="nonconformant",
                                rule="value_list",
                                message=f"{value!r} is not in the value list",
                            )
                        )
        if any(i.level == "nonconformant" for i in issues):
            status = "nonconformant"
        elif issues:
            status = "warning"
        else:
            status = "ok"
        return ConformanceReport(
            status=status,  # pyright: ignore[reportArgumentType]
            issues=issues,
            effective_schema_hash=self.metadata.effective_schema_hash,
        )


def keys(rows: Sequence[dict[str, Any]]) -> list[str]:
    return [r["key"] for r in rows]
