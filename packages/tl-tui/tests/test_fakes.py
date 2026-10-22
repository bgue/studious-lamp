"""The fake behaves like the real client where screens rely on it (P0-I2-T11)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pytest
from fakes import SCOPE, FakeClient, get_path
from tl_core.auth.errors import ForbiddenError
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import RecordNotFoundError, UnknownFileError, UploadVerificationError
from tl_core.services.psets import SetPsetValues
from tl_mod_documents.handlers.revisions import IssueRevision, VoidRevision
from tl_tui.client import ClientInterface


def _cmd(
    record_id: str,
    version: int,
    pset: str,
    layer: Literal["standard", "custom", "project"],
    values: dict[str, Any],
) -> SetPsetValues:
    return SetPsetValues(
        actor="user:t",
        source="tui",
        scope=SCOPE,
        stream_id=record_id,
        expected_version=version,
        pset=pset,
        layer=layer,
        values=values,
    )


def test_fake_satisfies_protocol_and_seeds_three_valves() -> None:
    client: ClientInterface = FakeClient.with_valve_example()
    rows = client.list_records(SCOPE)
    assert [r["key"] for r in rows] == ["FV-1001", "FV-1002", "FV-1003"]
    assert [r["conformance"] for r in rows] == ["ok", "warning", "nonconformant"]


def test_set_pset_values_nests_custom_keys_and_bumps_version() -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1002")
    assert record is not None
    result = client.set_pset_values(
        _cmd(record["id"], record["version"], "valve_data", "custom", {"x.fat_witness_by": "@p"})
    )
    assert result.version == record["version"] + 1
    updated = client.get_record_by_id(record["id"])
    assert updated is not None
    assert get_path(updated["psets"], "valve_data.x.fat_witness_by") == "@p"
    last = client.history(record["id"])[-1]
    assert last.event_type == "Pset.ValuesSet"
    assert last.payload["effective_schema_hash"] == client.metadata.effective_schema_hash


def test_stale_version_raises_concurrency_error() -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    with pytest.raises(ConcurrencyError):
        client.set_pset_values(_cmd(record["id"], 99, "valve_data", "standard", {"size_in": 1.0}))


def test_conformance_levels_follow_the_fake_rules() -> None:
    client = FakeClient.with_valve_example()
    full = client.get_record(SCOPE, "FV-1002")
    bare = client.get_record(SCOPE, "FV-1003")
    assert full is not None and bare is not None
    report = client.conformance(full["id"])
    assert report.status == "warning"
    assert [i.path for i in report.issues] == ["psets.valve_data.seat_leakage"]
    bad = client.conformance(bare["id"])
    assert bad.status == "nonconformant"
    assert {i.rule for i in bad.issues} == {"required_in_state"}


def test_a_stored_record_is_found_by_id_and_by_key() -> None:
    client = FakeClient()
    client.add_stored_record("DOC-1", "ISO-1", "documents.Document", "Sheet one")
    by_id = client.get_record_by_id("DOC-1")
    assert by_id is not None and by_id["type"] == "documents.Document"
    assert client.get_record(SCOPE, "ISO-1") == by_id
    assert client.get_record_by_id("DOC-2") is None


# --- record actions, files and module command runners (P1-UX2-S1) -------------------------------


def test_the_fake_offers_nothing_and_holds_no_files_until_a_test_says_so(tmp_path: Path) -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    found = client.allowed_actions(record["id"])
    assert found.record_id == record["id"] and found.actions == []
    assert client.list_record_files(record["id"]) == []
    client.set_actions(
        record["id"], ("RenameTag", "Rename"), ("MergeTags", "Merge"), state="Active"
    )
    again = client.allowed_actions(record["id"])
    assert [(a.command, a.label) for a in again.actions] == [
        ("RenameTag", "Rename"),
        ("MergeTags", "Merge"),
    ]
    assert again.state == "Active"


def test_a_hidden_record_of_the_fake_reads_like_a_missing_one(tmp_path: Path) -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    client.add_record_file(record["id"], "sheet.pdf", b"%PDF")
    client.hide_record(record["id"])
    with pytest.raises(RecordNotFoundError):
        client.allowed_actions(record["id"])
    assert client.list_record_files(record["id"]) == []
    (info,) = client._record_files[record["id"]]  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(UnknownFileError):
        client.fetch_file(info.file_id, tmp_path)


def test_the_fake_writes_a_verified_file_like_the_real_clients(tmp_path: Path) -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    client.add_record_file(record["id"], "../sheet.pdf", b"%PDF-1.7 sheet")
    (info,) = client.list_record_files(record["id"])
    path = client.fetch_file(info.file_id, tmp_path / "out")
    assert path.parent == (tmp_path / "out").resolve() and path.name == "sheet.pdf"
    assert path.read_bytes() == b"%PDF-1.7 sheet"
    with pytest.raises(UnknownFileError):  # never listed
        client.fetch_file("01FILE-UNKNOWN", tmp_path)
    tampered = client.add_record_file(record["id"], "bad.pdf", b"abc", sha256="0" * 64)
    client.list_record_files(record["id"])
    with pytest.raises(UploadVerificationError):
        client.fetch_file(tampered.file_id, tmp_path / "out")
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["sheet.pdf"]


def test_the_fake_runners_refuse_what_the_real_ones_refuse() -> None:
    client = FakeClient.with_valve_example()
    void = VoidRevision(actor="user:t", source="tui", scope=SCOPE, stream_id="R1", reason="x")
    with pytest.raises(ForbiddenError, match="not a engineering command"):
        client.engineering_command("VoidRevision", void)
    with pytest.raises(ForbiddenError, match="not a documents command"):
        client.document_command("VoidDocument", void)  # the class is not the named command's
    client.document_command("VoidRevision", void)
    assert client.module_commands == [("documents", "VoidRevision", void)]
    issue = IssueRevision(
        actor="user:t", source="tui", scope=SCOPE, stream_id="R1", issue_status="IFR"
    )
    client.is_module_controller = False
    with pytest.raises(ForbiddenError, match="document_controller or admin"):
        client.document_command("IssueRevision", issue)
