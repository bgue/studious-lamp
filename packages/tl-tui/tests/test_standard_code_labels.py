"""The company's code lists reach the plain logs: words in plain mode, codes in technical (D10).

``ClientInterface.list_code_lists`` feeds ``Labels``: the RFI log and the document register show
"Structural", "Isometric", "Piping" instead of STR, ISO, PIP, and the tag register's panel shows the
area as its list label; technical mode keeps the codes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_correspondence import seed_domains
from helpers import run_pilot, screen_text, settle
from textual.pilot import Pilot
from textual.widgets import DataTable
from tl_tui.app import TlApp
from tl_tui.labels_load import load_labels
from tl_tui.widgets.document_register import DocumentRegisterScreen
from tl_tui.widgets.domain_screen import DomainScreen
from tl_tui.widgets.tag_register import TagRegisterScreen

LISTS = {
    "Discipline": {"STR": "Structural", "PIP": "Piping"},
    "DocumentType": {"ISO": "Isometric"},
    "Area": {"47": "Unit 47, Hydrotreater"},
}


def cells(screen: Any, key: str) -> list[str]:
    table = screen.query_one("#log-table", DataTable)
    return [str(cell) for cell in table.get_row(key)]


def coded_world() -> FakeClient:
    client = FakeClient()
    seed_domains(client)
    client.seed_documents("P123")
    client.add_tag("P123", "47-FV-1001", class_code="ControlValve")
    client.code_lists = {name: dict(values) for name, values in LISTS.items()}
    lines = client._rfi_lines["P123"]  # pyright: ignore[reportPrivateUsage]
    client._rfi_lines["P123"] = [  # pyright: ignore[reportPrivateUsage]
        line.model_copy(update={"discipline": "STR"}) for line in lines
    ]
    for number, view in client._rfis["P123"].items():  # pyright: ignore[reportPrivateUsage]
        client._rfis["P123"][number] = view.model_copy(  # pyright: ignore[reportPrivateUsage]
            update={"discipline": "STR"}
        )
    return client


def drive(
    key: str,
    steps: Callable[[Pilot[None], TlApp, Any], Awaitable[None]],
    *,
    technical: bool,
) -> None:
    app = TlApp(coded_world(), scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        app.display_mode.technical = technical
        await pilot.press(key)
        await settle(pilot)
        await steps(pilot, app, app.screen)

    run_pilot(app, go, size=(170, 50))


def test_load_labels_keys_the_lists_by_column_and_by_list_name() -> None:
    labels = load_labels(coded_world(), "project:P123")
    assert labels.code_labels["discipline"]["STR"] == "Structural"
    assert labels.code_labels["Discipline"]["PIP"] == "Piping"
    assert labels.code_labels["doc_type"]["ISO"] == "Isometric"
    assert labels.code_labels["area"]["47"] == "Unit 47, Hydrotreater"


def test_a_failed_code_list_read_leaves_the_codes() -> None:
    client = coded_world()

    def refuse(scope: str) -> dict[str, dict[str, str]]:
        raise RuntimeError("standards.read refused")

    client.list_code_lists = refuse  # type: ignore[method-assign]
    assert load_labels(client, "project:P123").code_labels.get("discipline") is None


def rfi_cell(screen: DomainScreen) -> str:
    table = screen.query_one("#log-table", DataTable)
    columns = [str(column.label) for column in table.columns.values()]
    return str(table.get_row_at(0)[columns.index("Disc")])


def test_the_rfi_log_reads_structural_in_plain_and_str_in_technical() -> None:
    async def plain(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        assert isinstance(screen, DomainScreen)
        assert rfi_cell(screen) == "Structural"

    async def technical(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        assert isinstance(screen, DomainScreen)
        assert rfi_cell(screen) == "STR"

    drive("ctrl+g", plain, technical=False)
    drive("ctrl+g", technical, technical=True)


def test_the_document_register_reads_isometric_and_piping_in_plain_and_codes_in_technical() -> None:
    async def plain(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        assert isinstance(screen, DocumentRegisterScreen)
        row = cells(screen, "ISO-1234")
        assert row[3:5] == ["Isometric", "Piping"]

    async def technical(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        assert isinstance(screen, DocumentRegisterScreen)
        assert cells(screen, "ISO-1234")[3:5] == ["ISO", "PIP"]

    drive("f7", plain, technical=False)
    drive("f7", technical, technical=True)


def test_the_tag_register_panel_reads_the_area_as_its_label_and_technical_keeps_the_code() -> None:
    async def plain(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        assert isinstance(screen, TagRegisterScreen)
        text = screen_text(app)
        assert "Area 47 (Unit 47, Hydrotreater)" in text

    async def technical(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        assert isinstance(screen, TagRegisterScreen)
        text = screen_text(app)
        assert "area=47" in text and "Hydrotreater" not in text

    drive("f8", plain, technical=False)
    drive("f8", technical, technical=True)
