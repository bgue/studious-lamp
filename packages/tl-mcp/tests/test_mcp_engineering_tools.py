"""The engineering read tools: code-list values, tag classes and tags (P1-I1-T09f)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import McpHarness
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.handlers.standards import AddCodeValue, handle_add_code_value
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    RecordTag,
    handle_create_tag,
    handle_record_tag,
)
from tl_mod_engineering.loader import load_standards

ACME = (
    Path(__file__).resolve().parents[3]
    / "schema"
    / "fixtures"
    / "standards"
    / "co.acme.standards@1.0.0.yaml"
)
PROJECT = "project:P123"
BASE: dict[str, Any] = {"actor": "user:seed", "source": "test"}
NAMES = ("list_code_values", "list_tag_classes", "get_tag")


@pytest.fixture
def h(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[McpHarness]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    with use_provider(DirectorySchemaProvider()):
        harness = McpHarness.build(tmp_path)
        try:
            with harness.factory(False) as uow:
                load_standards(uow, load_standards_file(ACME), actor="user:seed", source="test")
                handle_add_code_value(
                    uow,
                    AddCodeValue(
                        **BASE,
                        scope=PROJECT,
                        code_list="Area",
                        code="T1",
                        label="Temporary",
                        crosswalk="47",
                    ),
                )
                handle_create_tag(
                    uow,
                    CreateTag(
                        **BASE,
                        scope=PROJECT,
                        number="47-FV-1001",
                        class_code="ControlValve",
                        service="Feed gas",
                    ),
                )
                handle_record_tag(uow, RecordTag(**BASE, scope=PROJECT, number="LEGACY-1"))
            yield harness
        finally:
            harness.close()


def test_the_three_tools_are_registered_read_only_and_described(h: McpHarness) -> None:
    tools = {t.name: t for t in asyncio.run(h.server.list_tools())}
    for name in NAMES:
        annotations = tools[name].annotations
        assert annotations is not None and annotations.read_only_hint is True
        assert annotations.destructive_hint is False and tools[name].description
    assert tools["list_code_values"].input_schema["required"] == ["code_list"]
    assert set(tools["list_code_values"].input_schema["properties"]) == {
        "code_list",
        "project",
        "include_all",
    }
    assert set(tools["get_tag"].input_schema["required"]) == {"project", "number"}
    assert set(tools["list_tag_classes"].input_schema["properties"]) == {"include_closed"}


def test_list_code_values_gives_the_company_values_then_the_projects_own(h: McpHarness) -> None:
    company = h.structured("list_code_values", code_list="Area")["result"]
    assert [v["code"] for v in company][:3] == ["10", "20", "30"]
    assert all(v["origin"] == "company" and v["usable"] for v in company)
    mine = h.structured("list_code_values", code_list="Area", project="P123")["result"]
    own = next(v for v in mine if v["code"] == "T1")
    assert (own["origin"], own["company_code"], own["scope"]) == ("project", "47", PROJECT)
    assert "T1" not in [v["code"] for v in company]


def test_list_code_values_says_when_the_list_does_not_exist(h: McpHarness) -> None:
    with pytest.raises(ToolError, match="no active code list 'Nope'"):
        h.call("list_code_values", code_list="Nope")


def test_list_tag_classes_gives_the_required_property_sets(h: McpHarness) -> None:
    classes = h.structured("list_tag_classes")["result"]
    assert [c["code"] for c in classes] == sorted(c["code"] for c in classes)
    safety = next(c for c in classes if c["code"] == "SafetyValve")
    assert (
        safety["required_psets"] == ["valve_data", "safety_data"] and "PSV" in safety["mnemonics"]
    )
    assert safety["lifecycle"] == "active"


def test_get_tag_gives_the_segments_the_class_and_what_is_lacking(h: McpHarness) -> None:
    tag = h.structured("get_tag", project="P123", number="47-FV-1001")
    assert tag["segments"] == {"area": "47", "mnemonic": "FV", "seq": "1001"}
    assert (tag["class_code"], tag["title"], tag["number_status"]) == (
        "ControlValve",
        "Feed gas",
        "ok",
    )
    assert tag["conformance"] == "nonconformant"
    assert any("valve_data" in issue["path"] for issue in tag["issues"])
    legacy = h.structured("get_tag", project="P123", number="LEGACY-1")
    assert legacy["number_status"] == "violation" and legacy["violations"]


def test_get_tag_of_an_unknown_number_is_a_tool_error(h: McpHarness) -> None:
    with pytest.raises(ToolError, match="no tag '47-FV-9999' in project 'P123'"):
        h.call("get_tag", project="P123", number="47-FV-9999")
    with pytest.raises(ToolError):
        h.call("get_tag", project="", number="x")
