"""Acceptance for OC-S1 (P2-W0): the ``tl:offline`` annotation, its values and the generator.
Exit 0, one ``PASS <check>`` line per check, then the table.

Run: ``uv run python dev/accept/P2-W0/OC-S1.py``.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from tl_schema import generate
from tl_schema.generated.offline_classes import OFFLINE_CLASSES, OFFLINE_STREAMS
from tl_schema.generated.type_labels import TYPE_LABELS
from tl_schema.generators.offline import OfflineClassError

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"

# Written from offline-classes.md section 4, not read from the generated module.
EXPECTED_RECORDS: dict[str, str] = {
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
EXPECTED_STREAMS: dict[str, str] = {
    "core.Account": "none",
    "core.ActionDefinition": "none",
    "core.ActionInvocation": "none",
    "core.ActivityPost": "full",
    "core.Enricher": "none",
    "core.EnrichmentValue": "none",
    "core.InboundEndpoint": "none",
    "core.IntegrationApp": "none",
    "core.Proposal": "none",
    "core.Rule": "none",
    "core.Setting": "none",
    "core.Thread": "full",
    "core.TypeRegistration": "none",
    "core.WebhookSubscription": "none",
}


def check_keys() -> None:
    assert set(OFFLINE_CLASSES) == set(TYPE_LABELS), sorted(set(OFFLINE_CLASSES) ^ set(TYPE_LABELS))


def check_table() -> None:
    assert dict(OFFLINE_CLASSES) == EXPECTED_RECORDS, {
        key: (OFFLINE_CLASSES.get(key), EXPECTED_RECORDS.get(key))
        for key in set(OFFLINE_CLASSES) | set(EXPECTED_RECORDS)
        if OFFLINE_CLASSES.get(key) != EXPECTED_RECORDS.get(key)
    }
    assert list(OFFLINE_CLASSES) == sorted(OFFLINE_CLASSES)


def check_streams() -> None:
    assert dict(OFFLINE_STREAMS) == EXPECTED_STREAMS
    assert list(OFFLINE_STREAMS) == sorted(OFFLINE_STREAMS)


def check_deterministic() -> None:
    first = generate.outputs(SCHEMA / "core")
    second = generate.outputs(SCHEMA / "core")
    assert first == second
    for name in ("offline_classes.py", "docs/offline-classes.md"):
        committed = (generate.GENERATED_DIR / name).read_text(encoding="utf-8")
        assert first[name] == committed, f"{name} differs from the committed file"


def _copy_edit(path: str, old: str, new: str) -> Path:
    """Copy ``schema/`` to a temp dir and replace ``old`` by ``new`` once in ``path``."""
    temp = Path(tempfile.mkdtemp(prefix="oc-s1-"))
    shutil.copytree(SCHEMA, temp / "schema")
    target = temp / "schema" / path
    text = target.read_text(encoding="utf-8")
    assert text.count(old) == 1, (path, old, text.count(old))
    target.write_text(text.replace(old, new), encoding="utf-8")
    return temp / "schema" / "core"


def _refuses(path: str, old: str, new: str, names: str) -> None:
    schema_dir = _copy_edit(path, old, new)
    try:
        try:
            generate.outputs(schema_dir)
        except OfflineClassError as error:
            assert names in str(error), f"{names!r} not named in {str(error)!r}"
            return
        raise AssertionError("generator accepted the edited schema")
    finally:
        shutil.rmtree(schema_dir.parent.parent, ignore_errors=True)


def check_missing() -> None:
    _refuses("modules/cost/cost_code.yaml", "      tl:offline: none\n", "", "CostCode")
    _refuses("core/record.yaml", "      tl:offline: full\n", "", "Record")


def check_unknown() -> None:
    _refuses("modules/cost/cost_code.yaml", "tl:offline: none", "tl:offline: sometimes", "CostCode")
    _refuses("core/feed.yaml", "tl:offline: full", "tl:offline: sometimes", "ActivityPost")


def check_multi_type() -> None:
    # The parent of a multi-type class disagrees with its subclass CodeList.
    standard = (SCHEMA / "modules/engineering/standard.yaml").read_text(encoding="utf-8")
    old = (
        'tl:record_types: "engineering.CodeList,engineering.Mnemonic,engineering.NumberingPattern"'
    )
    assert old in standard
    _refuses(
        "modules/engineering/standard.yaml",
        old,
        old + "\n      tl:offline: full",
        "engineering.CodeList",
    )
    # A subclass without the tag is refused, naming the subclass.
    _refuses(
        "modules/engineering/standard.yaml",
        "    is_a: Standard\n    annotations:\n      tl:offline: none\n"
        "    description: A registry entry of kind `mnemonic`.",
        "    is_a: Standard\n    description: A registry entry of kind `mnemonic`.",
        "Mnemonic",
    )


def check_stream_tag() -> None:
    _refuses("core/threads.yaml", "      tl:offline: full\n", "", "core.Thread")


CHECKS: list[tuple[str, Callable[[], None]]] = [
    ("every TYPE_LABELS type has a class and nothing else", check_keys),
    ("record table equals the spec table cell for cell", check_table),
    ("OFFLINE_STREAMS holds the spec streams", check_streams),
    ("output deterministic and equal to the committed files", check_deterministic),
    ("missing tl:offline raises OfflineClassError naming the class", check_missing),
    ("unknown value raises OfflineClassError naming the class", check_unknown),
    ("multi-type class: parent/subclass disagreement and missing subclass raise", check_multi_type),
    ("stream class without tl:offline raises", check_stream_tag),
]


def main() -> int:
    for name, check in CHECKS:
        try:
            check()
        except AssertionError as error:
            print(f"FAIL {name}: {error}")
            return 1
        print(f"PASS {name}")
    print()
    print(f"{'record type':<40}{'label':<26}class")
    for record_type, value in OFFLINE_CLASSES.items():
        print(f"{record_type:<40}{TYPE_LABELS[record_type]:<26}{value}")
    print()
    for stream, value in OFFLINE_STREAMS.items():
        print(f"{stream:<40}{'(stream)':<26}{value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
