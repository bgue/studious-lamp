"""Offline classes (OC-S1, T08): the generated table, its sources and the generator's refusals."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tl_schema import generate
from tl_schema.generated.offline_classes import OFFLINE_CLASSES, OFFLINE_STREAMS
from tl_schema.generated.type_labels import TYPE_LABELS
from tl_schema.generators.offline import OfflineClassError

REPO = Path(__file__).resolve().parents[3]
SCHEMA = REPO / "schema"

# Written from offline-classes.md section 4 (build-spec/specs), not read from the generated file.
SPEC_RECORDS: dict[str, str] = {
    "awp.CWA": "none",
    "awp.IWP": "draft_only",
    "awp.IWPCloseout": "none",
    "awp.ScopeItem": "draft_only",
    "awp.CWP": "draft_only",
    "awp.EWPRef": "none",
    "awp.PWPRef": "none",
    "awp.PathOfConstruction": "none",
    "awp.WBSNode": "none",
    "core.Constraint": "draft_only",
    "core.Record": "full",
    "correspondence.CommercialItem": "none",
    "correspondence.ContractClause": "none",
    "correspondence.Correspondence": "draft_only",
    "correspondence.CorrespondenceThread": "none",
    "correspondence.Party": "none",
    "correspondence.ResponseClock": "none",
    "correspondence.TechnicalItem": "draft_only",
    "cost.CostCode": "none",
    "cost.CostSnapshot": "none",
    "documents.DerivedDocument": "none",
    "documents.Document": "draft_only",
    "documents.DocumentSchema": "none",
    "documents.ProcessingJob": "none",
    "documents.Rendition": "draft_only",
    "documents.ReviewCycle": "none",
    "documents.Revision": "draft_only",
    "documents.Transmittal": "draft_only",
    "engineering.CodeList": "none",
    "engineering.CodeValue": "none",
    "engineering.Mnemonic": "none",
    "engineering.NumberingPattern": "none",
    "engineering.Tag": "full",
    "engineering.TagClass": "none",
    "legacy.LoadRun": "none",
    "materials.InventoryLocation": "none",
    "materials.ItemMaster": "none",
    "materials.MTO": "none",
    "materials.MTOLine": "none",
    "materials.POLineRef": "none",
    "materials.ProjectItem": "none",
    "materials.Receipt": "draft_only",
    "materials.StockLot": "draft_only",
    "schedule.ActivityRef": "none",
    "schedule.Schedule": "none",
    "schedule.ScheduleSnapshot": "none",
    "schemareg.Adoption": "none",
    "schemareg.SchemaPackage": "none",
    "schemareg.Waiver": "none",
}
SPEC_STREAMS: dict[str, str] = {
    "core.Account": "none",
    "core.ActionDefinition": "none",
    "core.ActionInvocation": "none",
    "core.ActivityPost": "full",
    "core.Enricher": "none",
    "core.EnrichmentValue": "none",
    "core.InboundDelivery": "none",  # T08: added after the spec table
    "core.InboundEndpoint": "none",
    "core.IntegrationApp": "none",
    "core.Proposal": "none",
    "core.Rule": "none",
    "core.Setting": "none",
    "core.Thread": "full",
    "core.TypeRegistration": "none",
    "core.WebhookSubscription": "none",
}


def test_every_labelled_record_type_has_a_class_and_nothing_else() -> None:
    assert set(OFFLINE_CLASSES) == set(TYPE_LABELS)
    assert len(OFFLINE_CLASSES) == 49


def test_the_record_table_is_the_spec_table_cell_for_cell() -> None:
    assert dict(OFFLINE_CLASSES) == SPEC_RECORDS
    assert list(OFFLINE_CLASSES) == sorted(OFFLINE_CLASSES)


def test_the_stream_table_holds_the_spec_streams_and_the_inbound_delivery() -> None:
    assert dict(OFFLINE_STREAMS) == SPEC_STREAMS
    assert OFFLINE_STREAMS["core.InboundDelivery"] == "none"
    assert list(OFFLINE_STREAMS) == sorted(OFFLINE_STREAMS)


def test_the_stream_classes_that_are_not_none_are_the_two_field_capture_streams() -> None:
    assert {k for k, v in OFFLINE_STREAMS.items() if v != "none"} == {
        "core.ActivityPost",
        "core.Thread",
    }


def test_the_output_is_deterministic_and_equals_the_committed_files() -> None:
    first = generate.outputs(SCHEMA / "core")
    assert first == generate.outputs(SCHEMA / "core")
    for name in ("offline_classes.py", "docs/offline-classes.md"):
        committed = (generate.GENERATED_DIR / name).read_text(encoding="utf-8")
        assert first[name] == committed, name


def test_the_generated_page_has_one_row_per_record_type_and_stream() -> None:
    page = (generate.GENERATED_DIR / "docs" / "offline-classes.md").read_text(encoding="utf-8")
    rows = [line for line in page.splitlines() if line.startswith("| `")]
    assert len(rows) == len(OFFLINE_CLASSES) + len(OFFLINE_STREAMS)
    assert "| `core.InboundDelivery` | `none` |" in page


def _edited(tmp_path: Path, path: str, old: str, new: str) -> Path:
    """Copy ``schema/`` to ``tmp_path`` and replace ``old`` by ``new`` once in ``path``."""
    shutil.copytree(SCHEMA, tmp_path / "schema")
    target = tmp_path / "schema" / path
    text = target.read_text(encoding="utf-8")
    assert text.count(old) == 1, (path, old, text.count(old))
    target.write_text(text.replace(old, new), encoding="utf-8")
    return tmp_path / "schema" / "core"


def _refused(tmp_path: Path, path: str, old: str, new: str, names: str) -> None:
    schema_dir = _edited(tmp_path, path, old, new)
    with pytest.raises(OfflineClassError, match=names):
        generate.outputs(schema_dir)


def test_a_record_type_without_a_class_is_refused(tmp_path: Path) -> None:
    _refused(tmp_path, "modules/cost/cost_code.yaml", "      tl:offline: none\n", "", "CostCode")


def test_core_record_without_a_class_is_refused(tmp_path: Path) -> None:
    _refused(tmp_path, "core/record.yaml", "      tl:offline: full\n", "", "Record")


def test_an_unknown_class_value_is_refused(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        "modules/cost/cost_code.yaml",
        "tl:offline: none",
        "tl:offline: sometimes",
        "CostCode",
    )


def test_an_unknown_stream_class_value_is_refused(tmp_path: Path) -> None:
    _refused(
        tmp_path, "core/feed.yaml", "tl:offline: full", "tl:offline: sometimes", "ActivityPost"
    )


def test_a_multi_type_parent_that_disagrees_with_its_subclass_is_refused(tmp_path: Path) -> None:
    old = (
        'tl:record_types: "engineering.CodeList,engineering.Mnemonic,engineering.NumberingPattern"'
    )
    _refused(
        tmp_path,
        "modules/engineering/standard.yaml",
        old,
        old + "\n      tl:offline: full",
        "engineering.CodeList",
    )


def test_a_multi_type_subclass_without_a_class_is_refused_by_name(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        "modules/engineering/standard.yaml",
        "    is_a: Standard\n    annotations:\n      tl:offline: none\n"
        "    description: A registry entry of kind `mnemonic`.",
        "    is_a: Standard\n    description: A registry entry of kind `mnemonic`.",
        "Mnemonic",
    )


def test_a_stream_class_without_an_offline_value_is_refused(tmp_path: Path) -> None:
    _refused(tmp_path, "core/threads.yaml", "      tl:offline: full\n", "", "core.Thread")


def test_the_delivery_stream_without_a_class_is_refused(tmp_path: Path) -> None:
    _refused(
        tmp_path,
        "core/integration_ops.yaml",
        "      tl:offline: none\n      tl:stream_type: core.InboundDelivery\n",
        "      tl:stream_type: core.InboundDelivery\n",
        "core.InboundDelivery",
    )


def test_a_core_class_with_record_types_gets_its_offline_class_and_label() -> None:
    assert OFFLINE_CLASSES["core.Constraint"] == "draft_only"
    assert "core.Constraint" in TYPE_LABELS
    assert "awp.Constraint" not in OFFLINE_CLASSES
    assert "awp.Constraint" not in TYPE_LABELS
