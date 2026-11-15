"""The QR module spec (P2-QR S1)."""

from __future__ import annotations

from tl_core.modules import ModuleSpec, load_modules
from tl_mod_qr import MODULE
from tl_mod_qr.module import projectors, spec
from tl_mod_qr.names import SCAN_CODE, SCAN_CODE_EVENTS
from tl_mod_qr.projectors import ScanCodeProjector


def test_spec_loads_with_one_record_type_and_one_projector() -> None:
    built = spec()
    assert isinstance(built, ModuleSpec)
    assert built.name == MODULE == "qr"
    assert built.record_types == frozenset({SCAN_CODE})
    assert [type(p) for p in built.projectors()] == [ScanCodeProjector]
    assert [type(p) for p in projectors()] == [ScanCodeProjector]


def test_no_commands_no_proposable_no_generic_commands() -> None:
    built = spec()
    assert dict(built.command_words) == {}
    assert tuple(built.proposable) == ()
    assert not built.generic_commands
    assert not built.company_roles


def test_the_platform_discovers_the_module_through_its_entry_point() -> None:
    by_name = {m.name: m for m in load_modules()}
    assert SCAN_CODE in by_name["qr"].record_types


def test_projector_handles_exactly_the_two_events() -> None:
    assert ScanCodeProjector.handles == SCAN_CODE_EVENTS == {"ScanCode.Issued", "ScanCode.Revoked"}
