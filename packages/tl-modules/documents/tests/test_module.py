"""The package imports, its schema header names the module, and the platform finds it."""

from __future__ import annotations

from pathlib import Path

import tl_mod_documents
from tl_core.modules import load_modules, module_record_types
from tl_core.projection.defaults import default_registry
from tl_mod_documents.module import projectors, spec
from tl_mod_documents.names import RECORD_TYPES

ROOT = Path(__file__).resolve().parents[4]


def test_the_package_names_its_module() -> None:
    assert tl_mod_documents.MODULE == "documents"


def test_the_schema_header_names_the_module() -> None:
    header = ROOT / "schema" / "modules" / "documents" / "module.yaml"
    assert "tl:module: documents" in header.read_text(encoding="utf-8")


def test_the_platform_loads_the_module_through_its_entry_point() -> None:
    assert "documents" in [m.name for m in load_modules()]
    assert RECORD_TYPES <= module_record_types()


def test_the_module_projectors_are_registered_after_the_core_ones_and_before_the_outbox() -> None:
    names = [p.name for p in default_registry().all()]
    assert names[-1] == "outbox"
    mine = [p.name for p in projectors()]
    assert all(name in names for name in mine)
    assert names.index("documents_document") > names.index("core_record")


def test_the_record_types_match_the_schema_annotations() -> None:
    import re

    found: set[str] = set()
    for path in (ROOT / "schema" / "modules" / "documents").glob("*.yaml"):
        found |= set(re.findall(r'tl:record_types: "([^"]+)"', path.read_text(encoding="utf-8")))
    assert found == set(spec().record_types) == set(RECORD_TYPES)


def test_every_document_event_type_is_handled_by_exactly_one_projector() -> None:
    owners: dict[str, list[str]] = {}
    for projector in projectors():
        for event_type in projector.handles:
            owners.setdefault(event_type, []).append(projector.name)
    assert all(len(names) == 1 for names in owners.values())
    catalogued = set()
    for path in (ROOT / "schema" / "modules" / "documents").glob("events.yaml"):
        import re

        catalogued = set(re.findall(r"tl:event_type: (\S+)", path.read_text(encoding="utf-8")))
    assert catalogued == set(owners)


def test_no_runtime_module_imports_the_test_world() -> None:
    """``tl_mod_documents.testing`` (``forge``, ``DocumentsWorld``) is for tests only."""
    src = ROOT / "packages" / "tl-modules" / "documents" / "src" / "tl_mod_documents"
    offenders = [
        path.name
        for path in src.rglob("*.py")
        if path.name != "testing.py"
        and (
            "tl_mod_documents.testing" in path.read_text(encoding="utf-8")
            or "from tl_mod_documents import testing" in path.read_text(encoding="utf-8")
        )
    ]
    assert offenders == []
    for other in ("tl-api", "tl-cli", "tl-mcp", "tl-tui", "tl-sim", "tl-core"):
        for path in (ROOT / "packages" / other / "src").rglob("*.py"):
            assert "tl_mod_documents.testing" not in path.read_text(encoding="utf-8"), path
