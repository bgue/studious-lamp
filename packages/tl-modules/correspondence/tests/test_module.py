"""The module package imports and its schema header names the module."""

from __future__ import annotations

from pathlib import Path

import tl_mod_correspondence

ROOT = Path(__file__).resolve().parents[4]


def test_the_package_names_its_module() -> None:
    assert tl_mod_correspondence.MODULE == "correspondence"


def test_the_schema_header_names_the_module() -> None:
    header = ROOT / "schema" / "modules" / "correspondence" / "module.yaml"
    assert "tl:module: correspondence" in header.read_text(encoding="utf-8")
