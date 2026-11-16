"""Module tool hooks: `build_server` registers tools from `ModuleSpec.tools` (P2-X4 S3)."""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import McpHarness
from tl_api.auth import Forbidden
from tl_core import modules as core_modules
from tl_core.modules import ModuleSpec, load_modules, resolve_hook, use_modules
from tl_mcp import server as server_module
from tl_mcp.context import McpContext
from tl_mcp.errors import guarded

# Captured before P2-X4 S3 (hand-listed registrars); names only, order is not pinned.
OLD_TOOL_NAMES = frozenset(
    {
        "compare_schedule_snapshots",
        "create_record",
        "get_activity_float_trend",
        "get_addable_properties",
        "get_commercial_item",
        "get_correspondence",
        "get_cost_code",
        "get_cwp",
        "get_derived_document",
        "get_document",
        "get_document_diff",
        "get_evidence_trail",
        "get_iwp",
        "get_iwp_progress",
        "get_iwp_readiness",
        "get_links",
        "get_look_ahead",
        "get_material_lot",
        "get_material_receipt",
        "get_progress_rollup",
        "get_punch_item",
        "get_record",
        "get_record_activity_links",
        "get_record_body",
        "get_record_type",
        "get_requisition",
        "get_rfi",
        "get_schedule",
        "get_schedule_activity",
        "get_settings",
        "get_tag",
        "get_transmittal",
        "get_weekly_plan",
        "get_work_order",
        "lake_query",
        "link_records",
        "list_code_values",
        "list_commercial_items",
        "list_correspondence",
        "list_cost_codes",
        "list_cost_snapshots",
        "list_cwps",
        "list_derived_documents",
        "list_documents",
        "list_iwp_scope",
        "list_iwps",
        "list_kpis",
        "list_material_items",
        "list_material_locations",
        "list_material_movements",
        "list_material_receipts",
        "list_material_stock",
        "list_mto_lines",
        "list_orphaned_links",
        "list_overdue_reviews",
        "list_parties",
        "list_po_lines",
        "list_punch_items",
        "list_record_types",
        "list_requisitions",
        "list_response_clocks",
        "list_rfis",
        "list_schedule_activities",
        "list_schedules",
        "list_stale_links",
        "list_tag_classes",
        "list_transmittals",
        "list_weekly_plans",
        "list_work_orders",
        "path_of_construction",
        "post_feed",
        "post_thread_message",
        "propose_cwp",
        "propose_dispatch",
        "propose_import",
        "propose_iwp_scope",
        "propose_progress",
        "propose_publish_schedule_snapshot",
        "propose_punch_item",
        "propose_requisition",
        "propose_reservation",
        "propose_setting_change",
        "propose_triage",
        "propose_week_commitment",
        "read_thread",
        "resolve_schedule_activity",
        "search_records",
        "start_extraction",
        "suggest_triage",
        "trace",
        "transition_workflow",
        "update_psets",
        "validate_against_schema",
        "wbs_tree",
    }
)


def _names(env: McpHarness) -> set[str]:
    return {t.name for t in asyncio.run(env.server.list_tools())}


def _fake(name: str, tools: tuple[str, ...]) -> ModuleSpec:
    return ModuleSpec(
        name=name,
        record_types=frozenset({f"{name}.Thing"}),
        projectors=list,
        tools=tools,
    )


@pytest.fixture
def probe_package() -> Iterator[str]:
    """An importable ``tl_mcp.fake_probe_tools`` with a registrar adding one tool."""
    mod = types.ModuleType("tl_mcp.fake_probe_tools")
    calls: list[int] = []

    def register_fake_tools(server: MCPServer, ctx: McpContext) -> None:
        calls.append(1)

        @server.tool()
        def fake_probe() -> str:
            with guarded(ctx, "fake_probe", "probe"):
                return "pong"

        @server.tool()
        def fake_other() -> str:
            with guarded(ctx, "fake_other", "probe"):
                return "pong"

    mod.register_fake_tools = register_fake_tools  # type: ignore[attr-defined]
    mod.calls = calls  # type: ignore[attr-defined]
    sys.modules["tl_mcp.fake_probe_tools"] = mod
    try:
        yield "tl_mcp.fake_probe_tools:register_fake_tools"
    finally:
        del sys.modules["tl_mcp.fake_probe_tools"]


def test_the_registered_tool_set_equals_the_set_before_the_hook(
    env: McpHarness,
) -> None:
    assert _names(env) == OLD_TOOL_NAMES


def test_every_installed_tools_ref_resolves_to_a_callable() -> None:
    count = 0
    for spec in load_modules():
        for register in resolve_hook(spec, "tools"):
            assert callable(register)
            count += 1
    # P2-QR S2 and P2-PTW S2 each added a registrar (neither registers a tool yet)
    assert count == 14


def test_a_module_tool_is_closed_until_its_action_is_allowed(
    tmp_path: Path, probe_package: str
) -> None:
    allowed: set[str] = set()

    def authorizer(actor: str, action: str, resource: str) -> None:
        if action not in allowed:
            raise Forbidden("closed")

    with use_modules([_fake("cost", (probe_package,))]):
        env = McpHarness.build(tmp_path, authorize_hook=authorizer)
    try:
        assert {"fake_probe", "fake_other"} <= _names(env)
        with pytest.raises(ToolError, match="not allowed"):
            env.call("fake_probe")
        allowed.add("mcp.fake_probe")
        assert env.call("fake_probe").is_error is not True
        with pytest.raises(ToolError, match="not allowed"):
            env.call("fake_other")
    finally:
        env.close()


def test_a_module_whose_hook_fails_registers_none_and_the_others_still_do(
    tmp_path: Path, probe_package: str, caplog: pytest.LogCaptureFixture
) -> None:
    broken = _fake("x", ("tl_mod_x.no_such_tools:register_missing_tools",))
    good = _fake("cost", (probe_package,))
    with caplog.at_level(logging.DEBUG), use_modules([broken, good]):
        env = McpHarness.build(tmp_path)
    try:
        names = _names(env)
    finally:
        env.close()
    assert "fake_probe" in names
    assert names == {"fake_probe", "fake_other"} | (
        OLD_TOOL_NAMES - _names_of_installed_module_tools()
    )
    messages = [r.getMessage() for r in caplog.records if r.name == "tl_mcp"]
    assert messages == ["module 'x': hook 'tools' cannot be resolved"]
    assert all("no_such_tools" not in r.getMessage() for r in caplog.records)
    assert all("register_missing_tools" not in r.getMessage() for r in caplog.records)
    assert all(r.exc_info is None for r in caplog.records if r.name == "tl_mcp")


def _names_of_installed_module_tools() -> frozenset[str]:
    """Tool names the installed modules add: the full set minus the core-only set."""
    with use_modules([]):
        import tempfile

        env = McpHarness.build(Path(tempfile.mkdtemp()))
        try:
            return OLD_TOOL_NAMES - _names(env)
        finally:
            env.close()


def test_resolution_happens_once_per_build_not_per_tool_call(
    tmp_path: Path, probe_package: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    real = core_modules.resolve_hook

    def counting(spec: ModuleSpec, kind: str) -> tuple[object, ...]:
        seen.append(f"{spec.name}:{kind}")
        return real(spec, kind)

    monkeypatch.setattr(server_module, "resolve_hook", counting)
    specs = [_fake("cost", (probe_package,)), _fake("legacy", ())]
    with use_modules(specs):
        env = McpHarness.build(tmp_path)
    try:
        assert seen == ["cost:tools"] or seen == ["cost:tools", "legacy:tools"]
        assert seen.count("cost:tools") == 1
        before = list(seen)
        env.call("fake_probe")
        env.call("fake_probe")
        assert seen == before
    finally:
        env.close()
