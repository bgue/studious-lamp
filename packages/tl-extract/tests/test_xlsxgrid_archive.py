"""An archive needs both the workbook part and the content-types part (P1-I3B-S9)."""

from __future__ import annotations

import io
import zipfile

import pytest
from extractsupport import hand_xlsx, inline_row, sheet_xml
from tl_extract.options import TableOptions
from tl_extract.reading import Refusal
from tl_extract.xlsxgrid import read_xlsx


def without(part: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(hand_xlsx(sheet_xml(inline_row(1, ["A"]))))) as source:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as target:
            for name in source.namelist():
                if name != part:
                    target.writestr(name, source.read(name))
    return buffer.getvalue()


@pytest.mark.parametrize("part", ["xl/workbook.xml", "[Content_Types].xml"])
def test_a_zip_missing_either_part_is_not_a_workbook(part: str) -> None:
    with pytest.raises(Refusal) as caught:
        read_xlsx(without(part), TableOptions())
    assert caught.value.code == "not_xlsx"


def test_a_zip_with_both_parts_is_read() -> None:
    raw = hand_xlsx(sheet_xml(inline_row(1, ["A"])))
    assert read_xlsx(raw, TableOptions()).rows == [["A"]]
