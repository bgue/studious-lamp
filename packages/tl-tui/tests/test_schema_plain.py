"""The schema workbench and review in plain language, and the technical toggle (P1-UX-T09c).

Plain mode is the default: a package shows as `Engineering, version 3.2.0`, the joined
`name@version` form and the `Digest` line are hidden. Technical mode shows them. The screen test
drives the workbench with a pilot and redraws it when the mode changes.
"""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from fakes_schemareg import make_package
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable
from tl_mod_schemareg.impact_types import ImpactReport
from tl_mod_schemareg.testing import fixture_text
from tl_mod_schemareg.views import SampleExample, SampleTestView
from tl_schema.classify import Change, build_report
from tl_tui.app import TlApp
from tl_tui.display import DisplayMode, find_technical
from tl_tui.schema_review_text import (
    classification_lines,
    impact_lines,
    sample_lines,
    title_line,
)
from tl_tui.schema_text import header_lines, plain_ref
from tl_tui.widgets.schema_screen import SchemaWorkbenchScreen


def test_plain_ref_forms() -> None:
    assert plain_ref("name@1.2.3") == "Name, version 1.2.3"
    assert plain_ref("x.P123@1.2.3") == "P123, version 1.2.3"
    assert plain_ref("co.acme.engineering@3.2.0") == "Engineering, version 3.2.0"
    assert plain_ref("co.acme.engineering") == "Engineering"
    assert plain_ref("ControlValve") == "Control valve"
    assert plain_ref("") == ""


def test_plain_header_and_title_have_no_joined_package_ref() -> None:
    report = build_report(
        "co.acme.engineering@3.2.0",
        "co.acme.engineering@3.3.0",
        [Change(cls="additive", code="property_added", path="psets.a.b", detail="b is new.")],
    )
    detail = make_package(
        "co.acme.engineering",
        "3.3.0",
        "Approved",
        worst_class="additive",
        analysed=True,
        classification=report,
        submitted_by="user:kim",
        approved_by="user:boss",
    )
    view = SampleTestView(
        package="co.acme.engineering@3.3.0",
        scope="company",
        sample=10,
        checked=4,
        newly_nonconformant=0,
        newly_warning=0,
        fixed=0,
        examples=[SampleExample(key="V-1", path="psets.a.b", rule="required", message="No.")],
    )
    plain = "\n".join(
        [
            *header_lines(detail),
            title_line(detail),
            *classification_lines(detail),
            *sample_lines(view),
        ]
    )
    assert find_technical(plain) == []
    assert "Engineering, version 3.3.0  Approved" in plain
    assert "Base Engineering, version 3.2.0" in plain
    assert "Tested Engineering, version 3.3.0  scope company" in plain

    technical = "\n".join(
        [
            *header_lines(detail, technical=True),
            title_line(detail, technical=True),
            *classification_lines(detail, technical=True),
            *sample_lines(view, technical=True),
        ]
    )
    assert "co.acme.engineering@3.3.0" in find_technical(technical)
    assert "Base co.acme.engineering@3.2.0" in technical


def test_digest_line_only_in_technical_mode() -> None:
    report = ImpactReport(
        scope="company",
        old_hash="a" * 64,
        new_hash="b" * 64,
        changed_paths=(),
        entries=(),
        counts={},
        truncated=False,
    )
    plain = impact_lines(report)
    assert plain == ["Scope company", "Counts -"]
    assert not any(line.startswith("Digest") for line in plain)
    technical = impact_lines(report, technical=True)
    assert technical == ["Scope company", f"Digest {report.digest}", "Counts -"]


def test_screen_toggle_refresh() -> None:
    client = FakeClient()
    client.seed_schema_package(
        make_package(
            "co.acme.engineering",
            "3.2.0",
            "Published",
            content=fixture_text("co.acme.engineering"),
            worst_class="additive",
            analysed=True,
        )
    )
    client.seed_schema_package(
        make_package("x.P123", "1.4.0", kind="extension", scope="project:P123", project="P123")
    )
    app = TlApp(client, scope=SCOPE, actor="user:boss", is_admin=False)

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("ctrl+o")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SchemaWorkbenchScreen)
        text = screen_text(app)
        assert "P123, version 1.4.0  Draft" in text  # the first row is highlighted
        assert "x.P123@1.4.0" not in text

        await pilot.press("down")  # the second row is the 3.2.0 version
        await pilot.pause()
        text = screen_text(app)
        assert "Engineering, version 3.2.0  Published" in text
        assert "co.acme.engineering@3.2.0" not in text.split("Properties")[0]
        mode = DisplayMode()
        mode.technical = True
        app.display_mode = mode  # pyright: ignore[reportAttributeAccessIssue]  # App does not declare it
        screen.refresh_for_display_mode()
        await pilot.pause()
        assert "co.acme.engineering@3.2.0  Published" in screen_text(app)
        assert screen.query_one("#schema-table", DataTable).cursor_row == 1  # the cursor is kept

        mode.technical = False
        screen.refresh_for_display_mode()
        await pilot.pause()
        assert "co.acme.engineering@3.2.0  Published" not in screen_text(app)
        assert "Engineering, version 3.2.0  Published" in screen_text(app)
        assert screen.query_one("#schema-table", DataTable).cursor_row == 1

    run_pilot(app, go)
