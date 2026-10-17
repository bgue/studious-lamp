"""Cost row text comes from an API body as well as from the CSV reader: both are checked (P1-I4)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tl_mod_cost.handlers.snapshots import ImportCostSnapshot
from tl_mod_cost.imports.model import CostRow
from tl_mod_cost.testing import BASE, row

BAD = ["\n", "\r", "\t", "\x00", "\x85", " ", " ", "‮", "‏", "⁦", "\x7f"]
FIELDS = ["code", "parent_code", "description", "uom"]


@pytest.mark.parametrize("char", BAD, ids=[f"U+{ord(c):04X}" for c in BAD])
@pytest.mark.parametrize("field", FIELDS)
def test_a_control_or_direction_character_in_any_text_field_is_refused(
    field: str, char: str
) -> None:
    values = {"code": "4210", "parent_code": "4200", "description": "Piping", "uom": "m"}
    values[field] = f"x{char}y"
    with pytest.raises(ValidationError) as caught:
        CostRow(**values)
    assert "control" in str(caught.value) and field in str(caught.value)
    assert [e["loc"] for e in caught.value.errors()] == [(field,)]
    assert all("x" + char not in e["msg"] for e in caught.value.errors())  # the value is not echoed


@pytest.mark.parametrize("char", BAD, ids=[f"U+{ord(c):04X}" for c in BAD])
def test_the_source_name_is_checked_the_same_way(char: str) -> None:
    with pytest.raises(ValidationError, match="control"):
        ImportCostSnapshot(
            **BASE,
            period="2026-07",
            as_of="2026-07-31",
            source_name=f"a{char}.csv",
            rows=[row("1")],
        )
    ok = ImportCostSnapshot(
        **BASE, period="2026-07", as_of="2026-07-31", source_name="july été.csv", rows=[row("1")]
    )
    assert ok.source_name == "july été.csv"


def test_ordinary_text_in_other_scripts_is_kept() -> None:
    made = CostRow(code="4210-É", description="مرحبا €", uom="m²")
    assert (made.code, made.description, made.uom) == ("4210-É", "مرحبا €", "m²")
