"""The awp module schema (P2-I1-S2): record types, tables, events, workflow, lists, numbering.

Written from the module spec (m3-wbs-cwp.md section 2) and the pinned lists of R-P2-4, not read
back from the generated files. The generated files are then checked against those lists.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml
from tl_schema.generated.offline_classes import OFFLINE_CLASSES
from tl_schema.generated.type_labels import TYPE_LABELS

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
AWP = SCHEMA / "modules" / "awp"
GENERATED = ROOT / "packages" / "tl-schema" / "src" / "tl_schema" / "generated"

RECORD_CLASSES = {
    "awp.WBSNode": "none",
    "awp.PathOfConstruction": "none",
    "awp.CWA": "none",
    "awp.CWP": "draft_only",
    "awp.EWPRef": "none",
    "awp.PWPRef": "none",
}
TABLES = [
    "cur_awp_wbs_node",
    "cur_awp_wbs_allocation",
    "cur_awp_path",
    "cur_awp_path_step",
    "cur_awp_cwa",
    "cur_awp_cwp",
    "cur_awp_cwp_allocation",
    "cur_awp_ewp_ref",
    "cur_awp_pwp_ref",
    "cur_awp_rollup",
]
VIEWS = [
    "v_awp_wbsnode",
    "v_awp_path_of_construction",
    "v_awp_cwa",
    "v_awp_cwp",
    "v_awp_ewpref",
    "v_awp_pwpref",
]
COMMODITIES = [
    "piping",
    "structural-steel",
    "concrete",
    "civil-earthworks",
    "electrical",
    "instrumentation",
    "mechanical-equipment",
    "insulation",
    "painting",
]
PATH_REASONS = ["Access", "Procurement", "Engineering", "Weather", "Crew", "Owner-request", "Other"]
CONSTRAINTS = [
    "Engineering",
    "Procurement",
    "Materials",
    "Equipment",
    "Permit",
    "Predecessor",
    "Access",
    "Other",
]
STATES = [
    "Planned",
    "In development",
    "Released for IWP development",
    "Executing",
    "Complete",
    "Closed",
    "Void",
]
NO_CARD = {
    "WBSNode.Defined",
    "WBSNode.Revised",
    "WBSNode.Retired",
    "WBSNode.CostCodesMapped",
    "WBSNode.BudgetRolledUp",
    "PathOfConstruction.Defined",
    "PathOfConstruction.Resequenced",
    "CWP.AllocatedToWbs",
}
CARD = {
    "CWA.Defined",
    "CWA.Revised",
    "CWA.Retired",
    "CWP.Defined",
    "CWP.Revised",
    "CWP.Released",
    "EWPRef.Defined",
    "EWPRef.Updated",
    "PWPRef.Defined",
    "PWPRef.Updated",
}


def _yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# --- record types ----------------------------------------------------------------------------


@pytest.mark.parametrize(("record_type", "offline"), sorted(RECORD_CLASSES.items()))
def test_each_record_type_has_a_label_and_its_offline_class(record_type: str, offline: str) -> None:
    assert record_type in TYPE_LABELS
    assert OFFLINE_CLASSES.get(record_type) == offline


def test_the_module_annotation_names_the_six_record_types() -> None:
    found: set[str] = set()
    for path in AWP.glob("*.yaml"):
        found |= set(re.findall(r'tl:record_types: "([^"]+)"', path.read_text(encoding="utf-8")))
    assert found == set(RECORD_CLASSES)


# --- tables ----------------------------------------------------------------------------------


def test_the_generated_tables_and_views_exist_for_both_dialects() -> None:
    for dialect in ("sqlite", "postgres"):
        for name in [*TABLES, *VIEWS]:
            path = GENERATED / "ddl" / dialect / f"{name}.sql"
            assert path.is_file(), path
    assert not (GENERATED / "ddl" / "sqlite" / "cur_awp_external_package.sql").exists()


def test_the_sqlite_ddl_creates_the_tables_with_the_columns_the_module_reads() -> None:
    conn = sqlite3.connect(":memory:")
    for name in TABLES:
        conn.executescript(
            (GENERATED / "ddl" / "sqlite" / f"{name}.sql").read_text(encoding="utf-8")
        )
    found = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(TABLES) <= found

    def cols(table: str) -> set[str]:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

    assert {"discipline", "budget_hours", "quantities_json", "contractor_text", "last_seq"} <= cols(
        "cur_awp_cwp"
    )
    assert {
        "subject_id",
        "line",
        "cost_code_id",
        "measure",
        "value",
        "as_of_seq",
        "run_id",
    } <= cols("cur_awp_rollup")
    assert {"id", "scope", "code", "parent_id", "depth", "position", "retired"} <= cols(
        "cur_awp_wbs_node"
    )
    assert {"row_id", "node_id", "cost_code_id", "percent"} <= cols("cur_awp_wbs_allocation")
    assert {"path_id", "version", "position", "cwa_id", "reason_code"} <= cols("cur_awp_path_step")
    assert {"package_no", "status_text", "constraint_source", "forecast_date"} <= cols(
        "cur_awp_ewp_ref"
    )


def test_the_depth_bound_and_percent_pattern_are_in_the_schema_source() -> None:
    wbs = _yaml(AWP / "wbs.yaml")
    depth = wbs["classes"]["WBSNode"]["attributes"]["depth"]
    assert (depth["minimum_value"], depth["maximum_value"]) == (0, 7)
    pattern = re.compile(wbs["classes"]["WbsAllocation"]["attributes"]["percent"]["pattern"])
    assert pattern.fullmatch("100.00")
    assert pattern.fullmatch("0.01")
    assert pattern.fullmatch("33.34")
    for bad in ("0.00", "100.01", "100", "5.0", "1e1", "-1.00", "00.50"):
        assert not pattern.fullmatch(bad), bad


# --- code lists ------------------------------------------------------------------------------


def test_the_awp_edition_holds_the_three_lists_in_order() -> None:
    doc = _yaml(FIXTURES / "standards" / "co.acme.awp@1.0.0.yaml")
    assert doc["standards"] == "co.acme.awp"
    lists = doc["code_lists"]
    assert set(lists) == {"Commodity", "PathReason", "ConstraintType"}
    assert [v["code"] for v in lists["Commodity"]["values"]] == COMMODITIES
    assert [v["code"] for v in lists["PathReason"]["values"]] == PATH_REASONS
    assert [v["code"] for v in lists["ConstraintType"]["values"]] == CONSTRAINTS
    assert {lst["value_list_policy"] for lst in lists.values()} == {"extensible"}


# --- workflow and numbering ------------------------------------------------------------------


def test_the_cwp_workflow_has_seven_states_closed_and_void_are_final() -> None:
    wf = _yaml(FIXTURES / "workflows" / "awp-cwp.yaml")
    assert [s["name"] for s in wf["states"]] == STATES
    assert (wf["record_type"], wf["initial_state"]) == ("awp.CWP", "Planned")
    moves = {(f, t["to"]) for t in wf["transitions"] for f in t["from"]}
    assert not any(f in ("Closed", "Void") for f, _ in moves)
    assert ("Closed", "Void") not in moves
    assert {(s, "Void") for s in STATES[:5]} <= moves
    assert ("Released for IWP development", "In development") in moves  # ReturnCwp
    assert ("Complete", "Executing") in moves  # ReopenCwp
    assert ("Complete", "Closed") in moves
    assert all(
        "guards" not in t for t in wf["transitions"]
    )  # the expected link is a report, no guard


def test_the_cwp_number_pattern_counts_each_discipline_gap_free() -> None:
    patterns = _yaml(FIXTURES / "numbering" / "patterns.yaml")["patterns"]
    [cwp] = [p for p in patterns if p["id"] == "awp.CWP"]
    assert cwp["template"] == "{project}-{type}-{discipline}-{seq:4}"
    assert cwp["type_code"] == "CWP"
    assert cwp["gap_free"] is True
    assert cwp["scope"] == "project:*"


# --- events ----------------------------------------------------------------------------------


def _events() -> dict[str, dict[str, Any]]:
    doc = _yaml(AWP / "events.yaml")
    by_type: dict[str, dict[str, Any]] = {}
    for name, cls in doc["classes"].items():
        event_type = (cls.get("annotations") or {}).get("tl:event_type")
        assert event_type is not None, name
        by_type[event_type] = cls
    return by_type


def test_the_eighteen_events_are_the_spec_list() -> None:
    assert set(_events()) == NO_CARD | CARD
    assert len(NO_CARD | CARD) == 18


@pytest.mark.parametrize("event_type", sorted(NO_CARD | CARD))
def test_the_feed_policy_key_is_on_the_no_card_events_only(event_type: str) -> None:
    policy = (_events()[event_type].get("attributes") or {}).get("feed_policy")
    if event_type in NO_CARD:
        assert policy is not None
        assert policy.get("equals_string") == "none"
        assert policy.get("required")
    else:
        assert policy is None


@pytest.mark.parametrize("event_type", sorted(NO_CARD | CARD))
def test_each_event_has_a_catalog_schema_and_a_sample_that_validates(event_type: str) -> None:
    catalog = GENERATED / "catalog"
    schema = json.loads((catalog / "schemas" / f"{event_type}.v1.json").read_text(encoding="utf-8"))
    sample = json.loads((catalog / "samples" / f"{event_type}.v1.json").read_text(encoding="utf-8"))
    jsonschema.validate(sample["envelope"], schema)  # the schema describes the envelope
    assert sample["envelope"]["data"]["detail"] == sample["payload"]
    assert sample["envelope"]["type"].endswith(event_type) or event_type in json.dumps(sample)
    assert f'"{event_type}"' in (catalog / "index.json").read_text(encoding="utf-8")


def test_the_eight_no_card_events_are_in_the_feed_policy_set_and_the_others_are_not() -> None:
    """D6: the feed honours ``feed_policy`` only for the names in POLICY_EVENT_TYPES."""
    from tl_core.feed.cards import POLICY_EVENT_TYPES

    assert NO_CARD <= POLICY_EVENT_TYPES
    assert not CARD & POLICY_EVENT_TYPES
    assert POLICY_EVENT_TYPES - NO_CARD == {
        "Correspondence.Issued",
        "Technical.Answered",
        "Commercial.Assessed",
    }


def test_the_module_constant_lists_the_same_eight() -> None:
    from tl_mod_awp.names import NO_CARD_EVENTS

    assert set(NO_CARD_EVENTS) == NO_CARD


def test_the_rolled_up_event_carries_the_run_and_the_unallocated_line_as_a_null_cost_code() -> None:
    attrs = _events()["WBSNode.BudgetRolledUp"]["attributes"]
    assert {"run_id", "as_of_seq", "total", "by_cost_code", "feed_policy"} <= set(attrs)
    assert "null" in attrs["by_cost_code"]["description"]
    assert "unallocated" in attrs["by_cost_code"]["description"]
