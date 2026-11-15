"""The QR module schema (P2-QR S1): table, unique index, events, offline class, no code slot."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tl_schema.generated.offline_classes import OFFLINE_CLASSES

GENERATED = Path(__file__).resolve().parents[1] / "src" / "tl_schema" / "generated"
SQLITE = GENERATED / "ddl" / "sqlite" / "cur_qr_scan_code.sql"
POSTGRES = GENERATED / "ddl" / "postgres" / "cur_qr_scan_code.sql"
FORBIDDEN = {"code", "token", "url"}
EVENTS = ("ScanCode.Issued", "ScanCode.Revoked")


def schema_of(event: str) -> dict[str, Any]:
    path = GENERATED / "catalog" / "schemas" / f"{event}.v1.json"
    whole = json.loads(path.read_text())
    return whole["properties"]["data"]["properties"]["detail"]


def test_the_table_and_its_unique_index_on_the_hash() -> None:
    for path in (SQLITE, POSTGRES):
        ddl = path.read_text()
        assert "CREATE TABLE IF NOT EXISTS cur_qr_scan_code" in ddl
        assert re.search(
            r"CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_qr_scan_code_code_hash ON cur_qr_scan_code "
            r"\(code_hash\)",
            ddl,
        )
        assert "ON cur_qr_scan_code (target_id)" in ddl


def test_no_column_is_named_code_token_or_url() -> None:
    for path in (SQLITE, POSTGRES):
        columns = set(re.findall(r"^  ([a-z_]+) ", path.read_text(), flags=re.M))
        assert {"id", "code_hash", "target_id", "revoke_reason", "replaced_by_id"} <= columns
        assert not columns & FORBIDDEN


def test_the_two_event_types_exist_and_carry_no_code_slot() -> None:
    for event in EVENTS:
        schema = schema_of(event)
        props = set(schema["properties"])
        assert "record_id" in props and not props & FORBIDDEN, event
        assert "record_id" in schema["required"]
        assert schema["properties"]["feed_policy"]["const"] == "none"
    assert {"code_hash", "target_id", "target_type", "label_text", "size", "expires_on"} <= set(
        schema_of("ScanCode.Issued")["properties"]
    )
    assert {"reason", "replaced_by_id"} <= set(schema_of("ScanCode.Revoked")["properties"])


def test_the_size_enum_keeps_all_three_values() -> None:
    props = schema_of("ScanCode.Issued")["properties"]["size"]
    assert props["enum"] == ["tag", "card", "sheet"]


def test_the_offline_class_is_none() -> None:
    assert OFFLINE_CLASSES["qr.ScanCode"] == "none"
