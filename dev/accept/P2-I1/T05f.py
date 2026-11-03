"""Acceptance for P2-I1-T05f: the external packages text (``tl_tui.package_text``) and its screen
(``tl_tui.widgets.package_log``), on the ``seed_awp`` fake with one EWP and one PWP added. No
database, no network, no pytest.

Run: ``uv run python dev/accept/P2-I1/T05f.py``. Prints ``PASS <check>`` per check, then
``T05f ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))

from fakes import SCOPE, FakeClient  # noqa: E402
from fakes_awp import PROJECT, seed_awp  # noqa: E402
from helpers import panel_of, run_pilot, screen_text, settle, static_of  # noqa: E402
from tl_mod_awp.views import PackageRow  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.layout import plain_lines  # noqa: E402
from tl_tui.package_text import (  # noqa: E402
    package_cells,
    package_page,
    package_summary,
)
from tl_tui.widgets.package_log import PackageLogScreen  # noqa: E402

WIDTHS = (80, 170)
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


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(check: str) -> None:
    print(f"PASS {check}")


def check_no_textual() -> None:
    code = (
        "import sys; sys.modules['textual'] = None\nimport tl_tui.package_text\nprint('imported')"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    need(done.returncode == 0 and "imported" in done.stdout, f"textual imported: {done.stderr}")
    passed("no textual")


def seeded_client() -> FakeClient:
    client = FakeClient()
    seed_awp(client)
    # the acceptance seed has no packages; this script adds one EWP and one PWP
    client._awp_packages[PROJECT] = [EWP, PWP]  # pyright: ignore[reportPrivateUsage]
    return client


def check_cells() -> None:
    need(
        package_cells(EWP) == ("EWP-101", "Piping spool drawings", "EWP", "Issued", "2026-11-20",
                               "—", "Yes", "3"),
        f"EWP cells {package_cells(EWP)}",
    )  # fmt: skip
    need(package_cells(PWP)[6] == "—", "a package that is not a constraint source reads —")
    need(package_cells(PWP)[7] == "0", "a package no CWP requires counts 0")
    need(package_cells(SPARSE)[1:] == ("—", "PWP", "—", "—", "—", "—", "0"), "sparse cells")
    passed("cells")


def check_summary() -> None:
    need(
        package_summary(EWP) == "EWP · forecast 2026-11-20 · required by 3 CWPs",
        f"summary {package_summary(EWP)!r}",
    )
    need(package_summary(PWP) == "PWP", f"summary without facts {package_summary(PWP)!r}")
    one = EWP.model_copy(update={"cwps": ["1"]})
    need(package_summary(one).endswith("required by 1 CWP"), "one CWP is singular")
    passed("summary")


def check_page() -> None:
    text = plain_lines(package_page(EWP, panel=True), width=80)
    print("\n".join(text))
    for heading in ("Dates", "Source", "CWPs (3)"):
        need(heading in [line.strip() for line in text], f"no heading {heading!r}")
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
    passed("page")


def check_keys(client: FakeClient) -> None:
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
    passed("keys")


def check_one_kind() -> None:
    # LogScreen hides a column that holds one value in every row when there are two or more rows
    # (one row hides nothing). The seed's one EWP and one PWP can show Type only; two EWPs show
    # the one-kind case.
    client = seeded_client()
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
    passed("one kind")


def check_mount(client: FakeClient, width: int) -> None:
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
    passed(f"mount {width}")


def check_missing() -> None:
    client = seeded_client()
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
    passed("missing")


def main() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        ("no textual", check_no_textual),
        ("cells", check_cells),
        ("summary", check_summary),
        ("page", check_page),
        ("keys", lambda: check_keys(seeded_client())),
        ("one kind", check_one_kind),
    ]
    for width in WIDTHS:
        checks.append((f"mount {width}", lambda w=width: check_mount(seeded_client(), w)))
    checks.append(("missing", check_missing))
    try:
        for _, run in checks:
            run()
    except Failed as exc:
        print(f"FAIL {exc}")
        return 1
    print("T05f ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
