"""Every migrated log stands on the shared LogScreen layout (P1-UX2-S3).

One table of logs: each is opened as its key opens it, on the fake client, at 170 and at 100
columns. The breadcrumb, the list, the panel (right of the list when wide, below when narrow), the
actions bar and the keys row are the same everywhere; what a log shows in them is tested with the
log (``test_<log>_screen.py``).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
import rows_integration as rows
from fakes import SCOPE, FakeClient
from fakes_correspondence import seed_correspondence, seed_domains
from fakes_schemareg import make_package
from helpers import run_pilot, settle
from textual.pilot import Pilot
from textual.widgets import DataTable, Static
from tl_mod_schemareg.testing import fixture_text
from tl_tui.app import TlApp
from tl_tui.widgets import domain_screen
from tl_tui.widgets.log_screen import LogScreen

WORLD_DAY = date(2026, 10, 20)  # the day `seed_domains` is as of


class _WorldDay(date):
    @classmethod
    def today(cls) -> date:
        return WORLD_DAY


@pytest.fixture(autouse=True)
def world_today(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(domain_screen, "date", _WorldDay)
    yield


def tags() -> FakeClient:
    client = FakeClient()
    client.add_tag("P123", "47-FV-1001", class_code="ControlValve", title="Feed gas control")
    client.add_tag("P123", "47-FV-1002", class_code="ControlValve", title="Vent valve")
    return client


def correspondence() -> FakeClient:
    client = FakeClient()
    seed_correspondence(client)
    return client


def domains() -> FakeClient:
    client = FakeClient()
    seed_domains(client)
    return client


def schedule() -> FakeClient:
    client = FakeClient()
    client.seed_schedule("P123")
    return client


def review() -> FakeClient:
    client = FakeClient()
    client.seed_integration("enrichments", **rows.enrichment())
    return client


def registry() -> FakeClient:
    client = FakeClient()
    client.seed_integration("apps", **rows.app())
    client.seed_integration("endpoints", **rows.endpoint())
    return client


def schema() -> FakeClient:
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
    return client


@dataclass(frozen=True)
class Case:
    name: str
    client: Callable[[], FakeClient]
    keys: tuple[str, ...]  # pressed to open the log (and to pick its view)
    crumb: str  # a pattern for the whole breadcrumb of the first row
    admin: bool = False


NUMBER = r"[\w.-]+"
CASES = [
    Case("tag register", tags, ("f8",), r"P123 › Tags › 47-FV-1001: Feed gas control"),
    Case(
        "correspondence register",
        correspondence,
        ("f5",),
        r"P123 › Correspondence register › P123-COR-0001: \S.*",
    ),
    Case(
        "triage inbox",
        correspondence,
        ("f5", "2"),
        r"P123 › Triage inbox › P123-COR-0001: \S.*",
    ),
    Case(
        "response clocks",
        correspondence,
        ("f5", "3"),
        r"P123 › Response clocks › P123-COR-0003: \S.*",
    ),
    Case("RFI log", domains, ("ctrl+g",), r"P123 › RFI log › P123-RFI-0001: \S.*"),
    Case(
        "Commercial register",
        domains,
        ("ctrl+g", "2"),
        rf"P123 › Commercial register › {NUMBER}: \S.*",
    ),
    Case(  # the trail of seed_domains is the early warning's, so open it from the register
        "evidence trail", domains, ("ctrl+g", "2", "t"), rf"P123 › Evidence › {NUMBER}(: \S.*)?"
    ),
    Case("schedules", schedule, ("f12",), rf"P123 › Schedules › {NUMBER}: \S.*"),
    Case("review queue", review, ("ctrl+r",), r"P123 › Review queue › \S.*: \S.*"),
    Case("integration registry", registry, ("ctrl+e",), r"P123 › Endpoints › \S.*", admin=True),
    Case("schema workbench", schema, ("ctrl+o",), r"P123 › Schema packages › \S.*"),
]


def text_of(screen: LogScreen[Any], ident: str) -> str:
    return str(screen.query_one(ident, Static).render())


def drive(case: Case, width: int, check: Callable[[LogScreen[Any]], None]) -> None:
    app = TlApp(case.client(), scope=SCOPE, actor="user:kim", is_admin=case.admin)

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press(case.keys[0])
        await settle(pilot)
        assert isinstance(app.screen, LogScreen), case.name
        for key in case.keys[1:]:
            await pilot.press(key)
            await settle(pilot)
        check(app.screen)

    run_pilot(app, go, size=(width, 40))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_a_migrated_log_shows_the_crumb_of_the_highlighted_row(case: Case) -> None:
    def check(screen: LogScreen[Any]) -> None:
        crumb = text_of(screen, "#log-crumb")
        assert re.fullmatch(case.crumb, crumb), crumb
        assert screen.query_one("#log-table", DataTable).row_count >= 1

    drive(case, 170, check)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_a_migrated_log_is_wide_at_170_columns_and_stacked_at_100(case: Case) -> None:
    def wide(screen: LogScreen[Any]) -> None:
        table, panel = screen.query_one("#log-table").region, screen.query_one("#log-panel").region
        assert screen.has_class("-wide") and panel.x >= table.right and panel.y == table.y

    def stacked(screen: LogScreen[Any]) -> None:
        table, panel = screen.query_one("#log-table").region, screen.query_one("#log-panel").region
        assert not screen.has_class("-wide") and panel.y >= table.bottom and panel.x == table.x

    drive(case, 170, wide)
    drive(case, 100, stacked)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_a_migrated_log_has_an_actions_bar_a_keys_row_and_a_status_line(case: Case) -> None:
    def check(screen: LogScreen[Any]) -> None:
        bar = text_of(screen, "#log-actions")
        assert bar.startswith("["), bar  # offers, or at least "[Enter] Open record"
        keys = text_of(screen, "#log-keys")
        assert keys == screen.KEY_HINTS and "F5 reload" in keys and "Esc" in keys
        screen.query_one("#log-status", Static)  # the summary line has its place

    drive(case, 120, check)
