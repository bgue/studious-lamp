"""The path of construction text and screen (T05c, D49, D50, D54) and the packages log (T05f)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from fakes_awp import PROJECT, seed_awp
from helpers import panel_of, run_pilot, screen_text, settle, static_of
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp.views import PackageRow, PathStep, PathView
from tl_tui.app import TlApp
from tl_tui.display import Labels
from tl_tui.layout import plain_lines
from tl_tui.package_text import package_cells, package_page, package_summary
from tl_tui.path_text import (
    PATH_COLUMNS,
    compare_cells,
    compare_versions,
    mark,
    path_cells,
    path_lines,
    path_page,
)
from tl_tui.widgets.package_log import PackageLogScreen
from tl_tui.widgets.path_screen import NO_EARLIER, PathScreen

WIDTHS = (80, 170)
SECTIONS = ("CWPs", "Steps changed", "Versions")


def need(ok: bool, what: str) -> None:
    assert ok, what


def seeded() -> FakeClient:
    client = FakeClient()
    seed_awp(client)
    return client


def test_lines() -> None:
    client = seeded()
    v2 = client.get_path(PROJECT, version=2)
    cwas, cwps = client.list_cwas(PROJECT), client.list_cwps(PROJECT)
    lines = path_lines(v2, cwas, cwps)
    need(len(lines) == 2, f"two steps expected, got {len(lines)}")
    need(
        path_cells(lines[0]) == ("1", "A1 · Area A1", "—", "2", "65.5"),
        f"step 1 cells {path_cells(lines[0])}",
    )
    need(
        path_cells(lines[1]) == ("2", "A2 · Area A2", "Reorder", "1", "—"),
        f"step 2 cells {path_cells(lines[1])}",
    )
    need(len(PATH_COLUMNS) == 5, "five columns")
    unreadable = path_lines(v2, [], cwps)
    need(path_cells(unreadable[0])[1] == "A1", "an unreadable area reads as its code alone")
    no_cwa = v2.model_copy(update={"steps": [v2.steps[0].model_copy(update={"cwa": None})]})
    need(path_cells(path_lines(no_cwa, cwas, cwps)[0])[1] == "—", "a step with no CWA reads —")


def test_compare() -> None:
    client = seeded()
    v1, v2 = client.get_path(PROJECT, version=1), client.get_path(PROJECT, version=2)
    seed = compare_versions(v1, v2)
    need([mark(m) for m in seed] == ["", "new"], f"seed marks {[mark(m) for m in seed]}")

    def step(cwa: str | None, position: int) -> PathStep:
        return PathStep(
            position=position,
            cwa=cwa,
            reason_code=None,
            actor="user:sue",
            recorded_at="2026-10-15T09:00:00+00:00",
        )

    old = v2.model_copy(update={"steps": [step("A1", 1), step("A2", 2), step("A3", 3)]})
    new = v2.model_copy(
        update={"steps": [step("A3", 1), step("A1", 2), step("A4", 3), step(None, 4)]}
    )
    moves = compare_versions(old, new)
    got = [(m.cwa, mark(m)) for m in moves]
    need(
        got == [("A3", "↑2"), ("A1", "↓1"), ("A4", "new"), ("A2", "gone")],
        f"moved marks {got}",
    )
    need(compare_cells(moves[1]) == ("A1", "1", "2", "↓1"), f"A1 cells {compare_cells(moves[1])}")
    need(compare_cells(moves[3]) == ("A2", "2", "—", "gone"), "gone row reads — after")


def test_page() -> None:
    client = seeded()
    v1, v2 = client.get_path(PROJECT, version=1), client.get_path(PROJECT, version=2)
    versions = client.list_path_versions(PROJECT)
    lines = path_lines(v2, client.list_cwas(PROJECT), client.list_cwps(PROJECT))
    for width in WIDTHS:
        wide = plain_lines(path_page(v2, versions, lines[0], previous=v1), width=width)
        need(all(len(line) <= width for line in wide), f"page wider than {width}")
    page = plain_lines(path_page(v2, versions, lines[0], previous=v1), width=80)
    need(page[0] == "Path of construction · version 2", f"identity {page[0]!r}")
    need(
        page[1] == "Re-sequenced 2026-10-15 by sue · reason Access",
        f"state line for version 2 {page[1]!r}",
    )
    stripped = [line.strip() for line in page]
    order = [stripped.index(name) for name in SECTIONS]
    need(order == sorted(order), f"sections out of order: {order}")
    first = plain_lines(path_page(v1, client.list_path_versions(PROJECT), None), width=80)
    need(first[1] == "Defined 2026-10-01 by sue", f"state line for version 1 {first[1]!r}")
    need("Steps changed" not in first, "no previous: no Steps changed section")
    need("CWPs" not in first, "no line: no CWPs section")
    labelled = path_page(
        v2,
        versions,
        None,
        labels=Labels(code_labels={"PathReason": {"Access": "Access to the site"}}),
    )
    need(
        plain_lines(labelled, width=80)[1].endswith("reason Access to the site"),
        "the reason label comes from the PathReason list",
    )
    empty = plain_lines(path_page(v2, versions, None, previous=v2), width=80)
    need("No steps changed" in empty, "unchanged versions say so")


def open_screen(
    client: FakeClient,
    size: tuple[int, int],
    steps: Callable[[Any, PathScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = PathScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(isinstance(app.screen, PathScreen), "the path screen did not open")
        await steps(pilot, screen)

    run_pilot(app, go, size=size)


def test_keys() -> None:
    async def steps(pilot: Any, screen: PathScreen) -> None:
        need(screen.view is not None and screen.view.version == 2, "opens on version 2")
        await pilot.press("left_square_bracket")
        await settle(pilot)
        need(screen.view is not None and screen.view.version == 1, "[ shows version 1")
        need(len(screen.shown) == 1, f"version 1 has one step: {len(screen.shown)}")
        await pilot.press("right_square_bracket")
        await settle(pilot)
        need(screen.view is not None and screen.view.version == 2, "] shows version 2")
        need(len(screen.shown) == 2, f"version 2 has two steps: {len(screen.shown)}")
        await pilot.press("v")
        await settle(pilot)
        need(screen.compare, "v turns the comparison on")
        compared: list[Any] = list(screen.shown)
        need([row.cwa for row in compared] == ["A1", "A2"], "compare rows in order")
        await pilot.press("v")
        await settle(pilot)
        need(not screen.compare and len(screen.shown) == 2, "v again shows the steps")
        await pilot.press("v")
        await settle(pilot)
        need(screen.compare, "v turns the comparison on again")
        await pilot.press("left_square_bracket")
        await settle(pilot)
        need(
            screen.view is not None and screen.view.version == 1,
            "[ with compare on shows version 1",
        )
        need(not screen.compare, "[ to version 1 turns the comparison off")
        need(len(screen.shown) == 1, f"version 1 shows its steps: {len(screen.shown)}")
        await pilot.press("right_square_bracket")
        await settle(pilot)
        need(screen.view is not None and screen.view.version == 2, "] shows version 2 again")
        need(len(screen.shown) == 2, f"version 2 shows its steps again: {len(screen.shown)}")
        await pilot.press("left_square_bracket")
        await settle(pilot)
        await pilot.press("v")
        await settle(pilot)
        need(not screen.compare, "v at version 1 does not turn the comparison on")
        need(
            NO_EARLIER in static_of(screen, "#log-status"), "v at version 1 says no earlier version"
        )
        await pilot.press("right_square_bracket")
        await settle(pilot)

    open_screen(seeded(), (120, 40), steps)


def check_mount(width: int) -> None:
    async def steps(pilot: Any, screen: PathScreen) -> None:
        lines = screen_text(pilot.app).splitlines()
        too_wide = [line for line in lines if len(line) > width]
        need(not too_wide, f"lines wider than {width}: {too_wide[:1]}")
        header = next((line for line in lines if "Number" in line and "Subject" in line), "")
        need(bool(header), "no header row with Number and Subject")
        need("A1 · Area A1" in "\n".join(lines), "no subject shown")
        if width >= 170:
            panel = panel_of(screen)
            need("Path of construction · version 2" in panel, f"panel {panel!r}")
            need("Re-sequenced 2026-10-15" in panel, "panel has no state line")
            need("Versions" in panel and "current" in panel, "panel has no versions")
            need("P123-CWP-0001" in panel, "panel has no CWPs of the highlighted step")

    open_screen(seeded(), (width, 40), steps)


def test_missing() -> None:
    client = seeded()

    def gone(project: str, version: int | None = None) -> PathView:
        raise RecordNotFoundError(f"no path version {version}")

    client.get_path = gone  # type: ignore[method-assign]

    async def steps(pilot: Any, screen: PathScreen) -> None:
        status = static_of(screen, "#log-status")
        need("no path version" in status, f"no status line: {status!r}")

    open_screen(client, (120, 40), steps)


@pytest.mark.parametrize("width", WIDTHS)
def test_mount(width: int) -> None:
    check_mount(width)


# --- the external packages log (T05f, D51) ----------------------------------------------------

EWP = PackageRow(
    id="PKG-EWP-101",
    kind="EWP",
    package_no="EWP-101",
    status_text="Issued",
    forecast_date="2026-11-20",
    actual_date=None,
    constraint_source=True,
    source_system="Aveva",
    title="Piping spool drawings",
    cwps=["1", "2", "3"],
)
PWP = PackageRow(
    id="PKG-PWP-7",
    kind="PWP",
    package_no="PWP-7",
    status_text="Planned",
    forecast_date=None,
    actual_date=None,
    constraint_source=False,
    source_system=None,
    title="Cable tray route",
    cwps=[],
)
SPARSE = PackageRow(
    id="PKG-PWP-9",
    kind="PWP",
    package_no="PWP-9",
    status_text=None,
    forecast_date=None,
    actual_date=None,
    constraint_source=False,
    source_system=None,
    title="",
    cwps=[],
)


def pkg_client() -> FakeClient:
    client = FakeClient()
    seed_awp(client)
    # the acceptance seed has no packages; this script adds one EWP and one PWP
    client._awp_packages[PROJECT] = [EWP, PWP]  # pyright: ignore[reportPrivateUsage]
    return client


def test_package_cells() -> None:
    need(
        package_cells(EWP) == ("EWP-101", "Piping spool drawings", "EWP", "Issued", "2026-11-20",
                               "—", "Yes", "3"),
        f"EWP cells {package_cells(EWP)}",
    )  # fmt: skip
    need(package_cells(PWP)[6] == "—", "a package that is not a constraint source reads —")
    need(package_cells(PWP)[7] == "0", "a package no CWP requires counts 0")
    need(package_cells(SPARSE)[1:] == ("—", "PWP", "—", "—", "—", "—", "0"), "sparse cells")


def test_package_summary() -> None:
    need(
        package_summary(EWP) == "EWP · forecast 2026-11-20 · required by 3 CWPs",
        f"summary {package_summary(EWP)!r}",
    )
    need(package_summary(PWP) == "PWP", f"summary without facts {package_summary(PWP)!r}")
    one = EWP.model_copy(update={"cwps": ["1"]})
    need(package_summary(one).endswith("required by 1 CWP"), "one CWP is singular")


def test_package_page() -> None:
    text = plain_lines(package_page(EWP, panel=True), width=80)
    for heading in ("Dates", "Source", "CWPs"):
        need(heading in [line.strip() for line in text], f"no heading {heading!r}")
    stripped = [line.strip() for line in text]
    under_cwps: list[str] = []
    for line in stripped[stripped.index("CWPs") + 1 :]:
        if not line:
            break
        under_cwps.append(line)
    need(under_cwps == ["1", "2", "3"], f"CWP numbers under the CWPs heading: {under_cwps}")
    need("EWP-101 · Piping spool drawings" in text[0], "identity line")
    need(any("Source system" in line and "Aveva" in line for line in text), "source system")
    plain_pwp = plain_lines(package_page(PWP), width=80)
    need("No CWPs require it" in plain_pwp, "no note for a package with no CWPs")
    technical = plain_lines(package_page(EWP, technical=True), width=80)
    need(any("PKG-EWP-101" in line for line in technical), "technical mode lacks the id")
    plain = plain_lines(package_page(EWP), width=80)
    need(not any("PKG-EWP-101" in line for line in plain), "plain mode shows the id")
    sparse = plain_lines(package_page(SPARSE, panel=True), width=80)
    dashes = [line for line in sparse if line.strip().startswith("Forecast")]
    need(bool(dashes) and dashes[0].rstrip().endswith("—"), f"missing dates read —: {dashes}")


def check_pkg_keys(client: FakeClient) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    def header(pilot: Any) -> str:
        lines = screen_text(pilot.app).splitlines()
        return next((line for line in lines if "Number" in line and "Subject" in line), "")

    async def steps(pilot: Any, screen: PackageLogScreen) -> None:
        need(len(screen.shown) == 2, f"all packages at first: {len(screen.shown)}")
        need("Type" in header(pilot), "Type column shown with two kinds")
        await pilot.press("t")
        await settle(pilot)
        need(len(screen.shown) == 1 and screen.shown[0].kind == "EWP", "t shows EWP only")
        await pilot.press("t")
        await settle(pilot)
        need(len(screen.shown) == 1 and screen.shown[0].kind == "PWP", "t shows PWP only")
        await pilot.press("t")
        await settle(pilot)
        need(len(screen.shown) == 2, "t again shows all")
        await pilot.press("c")
        await settle(pilot)
        need(len(screen.shown) == 1 and screen.shown[0].constraint_source, "c keeps constraints")
        need("constraint sources only" in static_of(screen, "#log-status"), "c is named")
        await pilot.press("c")
        await settle(pilot)
        need(len(screen.shown) == 2, "c again shows all")

    async def go(pilot: Any) -> None:
        screen = PackageLogScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(isinstance(app.screen, PackageLogScreen), "the package log did not open")
        await steps(pilot, screen)

    run_pilot(app, go, size=(170, 40))


def test_package_one_kind() -> None:
    # LogScreen hides a column that holds one value in every row when there are two or more rows
    # (one row hides nothing). The seed's one EWP and one PWP can show Type only; two EWPs show
    # the one-kind case.
    client = pkg_client()
    second = EWP.model_copy(update={"id": "PKG-EWP-102", "package_no": "EWP-102"})
    client._awp_packages[PROJECT] = [EWP, second]  # pyright: ignore[reportPrivateUsage]
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = PackageLogScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(len(screen.shown) == 2, f"two EWPs listed: {len(screen.shown)}")
        lines = screen_text(pilot.app).splitlines()
        header = next((line for line in lines if "Number" in line and "Subject" in line), "")
        need(bool(header), "no header row")
        need("Type" not in header, "Type column shown with one kind")

    run_pilot(app, go, size=(170, 40))


def check_pkg_mount(client: FakeClient, width: int) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = PackageLogScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(isinstance(app.screen, PackageLogScreen), "the package log did not open")
        lines = screen_text(pilot.app).splitlines()
        too_wide = [line for line in lines if len(line) > width]
        need(not too_wide, f"lines wider than {width}: {too_wide[:1]}")
        header = next((line for line in lines if "Number" in line and "Subject" in line), "")
        need(bool(header), "no header row with Number and Subject")
        need("EWP-101" in "\n".join(lines), "no package number shown")
        if width >= 170:
            panel = panel_of(screen)
            need("EWP-101 · Piping spool drawings" in panel, f"panel {panel!r}")
            need(
                "EWP · forecast 2026-11-20 · required by 3 CWPs" in panel,
                f"panel summary {panel!r}",
            )
        status = static_of(screen, "#log-status")
        need(not status.startswith("!"), f"an error in the status line: {status!r}")

    run_pilot(app, go, size=(width, 40))


def test_package_missing() -> None:
    client = pkg_client()
    client._awp_packages[PROJECT] = [SPARSE]  # pyright: ignore[reportPrivateUsage]
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = PackageLogScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(len(screen.shown) == 1, f"the sparse package is listed: {len(screen.shown)}")
        need(package_cells(screen.shown[0])[1] == "—", "no title reads —")
        panel = panel_of(screen)
        need("PWP-9" in panel and "No CWPs require it" in panel, f"sparse panel {panel!r}")
        status = static_of(screen, "#log-status")
        need(not status.startswith("!"), f"sparse package is an error: {status!r}")

    run_pilot(app, go, size=(120, 40))


@pytest.mark.parametrize("width", WIDTHS)
def test_package_mount(width: int) -> None:
    check_pkg_mount(pkg_client(), width)


def test_package_keys() -> None:
    check_pkg_keys(pkg_client())


def test_package_enter_does_nothing_and_f5_reads_again() -> None:
    client = pkg_client()
    reads: list[str] = []
    read = client.list_packages

    def counted(project: str, *, kind: str | None = None) -> list[PackageRow]:
        reads.append(project)
        return read(project, kind=kind)  # type: ignore[arg-type]

    client.list_packages = counted  # type: ignore[method-assign]
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = PackageLogScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        before = len(reads)
        await pilot.press("enter")
        await settle(pilot)
        assert app.screen is screen
        await pilot.press("f5")
        await settle(pilot)
        assert len(reads) == before + 1
        assert app.screen is screen

    run_pilot(app, go, size=(170, 40))


def test_package_columns_run_type_then_status() -> None:
    client = pkg_client()
    app = TlApp(client, scope=SCOPE, actor="user:kim")
    seen: dict[str, str] = {}

    async def go(pilot: Any) -> None:
        app.push_screen(PackageLogScreen(client, PROJECT))
        await settle(pilot)
        lines = screen_text(app).splitlines()
        seen["header"] = next(line for line in lines if "Type" in line and "Status" in line)

    run_pilot(app, go, size=(170, 40))
    assert seen["header"].index("Type") < seen["header"].index("Status")
