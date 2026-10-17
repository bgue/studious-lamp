"""The largest tables the contract allows, written the way Excel writes them, are read (S19).

20 000 rows of 50 columns and 5 000 rows of 200 columns are a million data cells each. Excel writes
a cell as ``<c r="A2" s="1" t="s"><v>n</v></c>``: two elements and three attributes, which the
element budget must not charge as if the file were hostile. These two tests take about ten seconds
each: that is what reading a million cells costs (9 to 9.5 s of it in the reader).
"""

from __future__ import annotations

import time

import pytest
from extractsupport import hand_xlsx, sheet_xml
from tl_extract.options import TableOptions
from tl_extract.xlsxgrid import read_xlsx

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def column_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def excel_table(rows: int, columns: int) -> bytes:
    """A workbook with a header row and ``rows`` data rows of ``columns`` shared-string cells."""
    names = [column_name(i) for i in range(columns)]
    strings = [f"h{n}" for n in names] + [f"v{i}" for i in range(16)]
    sst = (
        f'<sst xmlns="{MAIN}" count="{len(strings)}" uniqueCount="{len(strings)}">'
        + "".join(f"<si><t>{text}</t></si>" for text in strings)
        + "</sst>"
    )
    header = (
        '<row r="1">'
        + "".join(f'<c r="{n}1" s="1" t="s"><v>{i}</v></c>' for i, n in enumerate(names))
        + "</row>"
    )
    body = [header]
    for r in range(2, rows + 2):
        cells = "".join(
            f'<c r="{n}{r}" s="1" t="s"><v>{columns + (r + i) % 16}</v></c>'
            for i, n in enumerate(names)
        )
        body.append(f'<row r="{r}" spans="1:{columns}">{cells}</row>')
    rels = (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships">'
        f'<Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>'
        "</Relationships>"
    )
    return hand_xlsx(
        sheet_xml("".join(body)),
        {"xl/sharedStrings.xml": sst.encode(), "xl/_rels/workbook.xml.rels": rels.encode()},
    )


@pytest.mark.parametrize(("rows", "columns"), [(20_000, 50), (5_000, 200)])
def test_a_table_of_a_million_cells_in_excels_form_is_read(rows: int, columns: int) -> None:
    raw = excel_table(rows, columns)
    started = time.monotonic()
    grid = read_xlsx(raw, TableOptions())
    elapsed = time.monotonic() - started
    assert len(grid.rows) == rows + 1
    assert len(grid.rows[-1]) == columns and grid.rows[0][0] == "hA"
    assert elapsed < 30
