"""The permits module spec (P2-PTW S1): loads, three record types, no commands, no proposable."""

from __future__ import annotations

from tl_core.modules import ModuleSpec, load_modules
from tl_mod_permits import MODULE
from tl_mod_permits.module import projectors, spec
from tl_mod_permits.names import (
    GAS_TEST,
    GAS_TEST_EVENTS,
    ISOLATION,
    ISOLATION_EVENTS,
    PERMIT,
    PERMIT_EVENTS,
    RECORD_TYPES,
    WORDS,
)
from tl_mod_permits.projectors import GasTestProjector, IsolationProjector, PermitProjector


def test_the_module_loads_with_three_record_types() -> None:
    built = spec()
    assert isinstance(built, ModuleSpec)
    assert built.name == MODULE == "permits"
    assert built.record_types == frozenset({PERMIT, ISOLATION, GAS_TEST}) == RECORD_TYPES
    assert [type(p) for p in built.projectors()] == [
        PermitProjector,
        IsolationProjector,
        GasTestProjector,
    ]
    assert [type(p) for p in projectors()] == [
        PermitProjector,
        IsolationProjector,
        GasTestProjector,
    ]


def test_no_commands_no_proposable_no_generic_rows_no_hooks() -> None:
    built = spec()
    assert dict(built.command_words) == {}
    assert built.proposable == ()
    assert not built.generic_commands and not built.generic_guards
    assert not built.actions and not built.offline_drafts and not built.company_roles


def test_the_platform_discovers_the_module_through_its_entry_point() -> None:
    by_name = {m.name: m for m in load_modules()}
    assert by_name["permits"].record_types == RECORD_TYPES


def test_the_projectors_handle_seventeen_events_between_them() -> None:
    handled = PermitProjector.handles | IsolationProjector.handles | GasTestProjector.handles
    assert handled == PERMIT_EVENTS | ISOLATION_EVENTS | GAS_TEST_EVENTS
    assert len(PERMIT_EVENTS) == 13 and len(ISOLATION_EVENTS) == 3 and len(GAS_TEST_EVENTS) == 1
    assert len(handled) == 17


def test_twelve_words() -> None:
    assert len(WORDS) == 12
