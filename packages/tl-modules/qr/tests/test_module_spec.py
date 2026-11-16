"""The QR module spec (P2-QR S1, S2): three commands, the hooks, the marks."""

from __future__ import annotations

from tl_core.modules import ModuleSpec, hook_failures, load_modules, resolve_hook
from tl_mod_qr import MODULE
from tl_mod_qr.module import COMMANDS, projectors, spec
from tl_mod_qr.names import SCAN_CODE, SCAN_CODE_EVENTS
from tl_mod_qr.projectors import ScanCodeProjector


def test_spec_loads_with_one_record_type_and_one_projector() -> None:
    built = spec()
    assert isinstance(built, ModuleSpec)
    assert built.name == MODULE == "qr"
    assert built.record_types == frozenset({SCAN_CODE})
    assert [type(p) for p in built.projectors()] == [ScanCodeProjector]
    assert [type(p) for p in projectors()] == [ScanCodeProjector]


def test_three_commands_with_their_words_and_no_proposable_row() -> None:
    built = spec()
    assert dict(built.command_words) == {
        "IssueScanCode": "qr.issue",
        "RevokeScanCode": "qr.revoke",
        "RotateScanCode": "qr.issue",
    }
    assert {row.model.__name__ for row in COMMANDS} == set(built.command_words)
    assert tuple(built.proposable) == ()
    assert not built.generic_commands
    assert not built.company_roles


def test_the_marks_are_in_the_rows() -> None:
    marks = {row.model.__name__: row.meta["delegation"] for row in COMMANDS}
    assert marks == {
        "IssueScanCode": "excluded:access",
        "RotateScanCode": "excluded:access",
        "RevokeScanCode": "excluded:reserved",
    }


def test_every_hook_names_the_modules_own_package_and_resolves() -> None:
    built = spec()
    refs = [built.commands, *built.read_routers, *built.tools, *built.cli_groups]
    assert len(refs) == 4 and all(str(r).startswith("tl_mod_qr") for r in refs)
    for kind in ("commands", "read_routers", "tools", "cli_groups"):
        assert resolve_hook(built, kind)
    assert "qr" not in hook_failures()


def test_the_platform_discovers_the_module_through_its_entry_point() -> None:
    by_name = {m.name: m for m in load_modules()}
    assert SCAN_CODE in by_name["qr"].record_types


def test_projector_handles_exactly_the_two_events() -> None:
    assert ScanCodeProjector.handles == SCAN_CODE_EVENTS == {"ScanCode.Issued", "ScanCode.Revoked"}
