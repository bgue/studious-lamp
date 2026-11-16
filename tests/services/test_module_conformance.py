"""Conformance over ``load_modules()``: one rule set for every module, in tree or added later.

ADR-0029 decision 7 (a Decimal, currency or amount field means ``excluded:money``; a command with no
mark is excluded) and ADR-0027 decision 4 (a command is a proposable row or a listed exclusion).
The rules are functions over rows, so a test can hand them a fake row and watch them fail; the
real tests hand them ``module_commands()``. The marks live in ``tests/tools/delegation_marks.toml``
(P2-X4 D6), and a row's own ``meta["delegation"]`` wins. Nothing here is read at runtime.
"""

from __future__ import annotations

import sys
import tomllib
import types
import typing
from collections.abc import Iterator, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from tl_core.modules import (
    IN_TREE_SURFACES,
    ModuleCommand,
    ModuleLoadError,
    ModuleSpec,
    hook_failures,
    load_modules,
    module_commands,
    use_modules,
)
from tl_core.modules import _table_word as table_word  # pyright: ignore[reportPrivateUsage]
from tl_core.services.commands import Command

TOOLS = Path(__file__).resolve().parents[1] / "tools"
MIN_MODULES, MIN_COMMANDS, MAX_UNDECIDED = 11, 200, 150
REASONS = frozenset(
    {"admin", "money", "access", "schema", "setting", "action", "external", "reserved"}
)
MONEY_NAMES = frozenset({"amount", "currency", "price", "rate", "budget", "cost"})
NOT_DELEGABLE_WORDS = frozenset({"admin", "controller", "company"})


class Marks(typing.NamedTuple):
    eligible: Mapping[str, str]
    excluded: Mapping[str, str]


def load_marks(path: Path = TOOLS / "delegation_marks.toml") -> Marks:
    data = tomllib.loads(path.read_text())
    return Marks(data.get("eligible", {}), data.get("excluded", {}))


def load_exclusions() -> set[str]:
    return set(tomllib.loads((TOOLS / "proposable_exclusions.toml").read_text())["commands"])


def load_undecided(path: Path = TOOLS / "proposable_undecided.txt") -> list[str]:
    return [line for line in path.read_text().splitlines() if line.strip()]


def marks_of(row: ModuleCommand, marks: Marks) -> set[str]:
    """Every distinct mark a row has: its own meta, and the file's tables."""
    found: set[str] = set()
    if "delegation" in row.meta:
        found.add(row.meta["delegation"])
    if row.name in marks.eligible:
        found.add("eligible")
    if row.name in marks.excluded:
        found.add(f"excluded:{marks.excluded[row.name]}")
    return found


# --- money (rule 3) ----------------------------------------------------------------------------


def _parts(annotation: Any) -> Iterator[Any]:
    yield annotation
    for arg in typing.get_args(annotation):
        yield from _parts(arg)


def money_fields(model: type[BaseModel], *, nested: bool = True) -> list[str]:
    """Fields typed ``Decimal`` or named like money, with one level of sub-model fields."""
    found: list[str] = []
    for name, info in model.model_fields.items():
        parts = list(_parts(info.annotation))
        if Decimal in parts or name.lower() in MONEY_NAMES:
            found.append(name)
        if nested:
            for part in parts:
                if isinstance(part, type) and issubclass(part, BaseModel):
                    found += [f"{name}.{sub}" for sub in money_fields(part, nested=False)]
    return found


def money_problems(rows: Sequence[ModuleCommand], marks: Marks) -> list[str]:
    return [
        f"{row.name}: money field {fields} but mark is {sorted(marks_of(row, marks))}"
        for row in rows
        if (fields := money_fields(row.model)) and marks_of(row, marks) != {"excluded:money"}
    ]


# --- words (rule 2) ----------------------------------------------------------------------------


def word_problems(rows: Sequence[ModuleCommand], specs: Sequence[ModuleSpec]) -> list[str]:
    from tl_core.auth.access_words import AccessWordError

    by_name = {spec.name: spec for spec in specs}
    problems: list[str] = []
    for row in rows:
        try:
            table_word(row.access)
        except AccessWordError:
            problems.append(f"{row.name}: access {row.access!r} is not a word the authorizer knows")
        declared = by_name[row.module].command_words
        if declared and row.name not in declared:
            problems.append(f"{row.name}: module {row.module} declares words for others, not this")
        elif row.name in declared and declared[row.name] != row.access:
            problems.append(f"{row.name}: row says {row.access!r}, command_words says another")
    return problems


# --- delegation marks (rule 5) -----------------------------------------------------------------


def mark_problems(
    rows: Sequence[ModuleCommand],
    marks: Marks,
    *,
    agent_rows: set[str],
    exclusions: set[str],
    in_tree: frozenset[str] = IN_TREE_SURFACES,
) -> list[str]:
    names = {row.name for row in rows}
    problems = [
        f"stale mark for {n}" for n in sorted((set(marks.eligible) | set(marks.excluded)) - names)
    ]
    problems += [
        f"{n} is in both tables" for n in sorted(set(marks.eligible) & set(marks.excluded))
    ]
    for row in rows:
        found = marks_of(row, marks)
        if len(found) != 1:
            problems.append(f"{row.name}: needs exactly one mark, has {sorted(found)}")
            continue
        (mark,) = found
        if mark != "eligible" and not (
            mark.startswith("excluded:") and mark.removeprefix("excluded:") in REASONS
        ):
            problems.append(f"{row.name}: bad mark {mark!r}")
        if row.module not in in_tree and "delegation" not in row.meta:
            problems.append(f"{row.name}: module {row.module} must carry the mark in row meta")
        if mark == "eligible":
            if row.name not in agent_rows:
                problems.append(f"{row.name}: eligible but not an agent proposable row")
            if row.name in exclusions:
                problems.append(f"{row.name}: eligible but listed in proposable_exclusions")
            if table_word(row.access) in NOT_DELEGABLE_WORDS:
                problems.append(f"{row.name}: eligible with access {row.access!r}")
    return problems


# --- row or exclusion (rule 4) -----------------------------------------------------------------


def undecided_names(rows: Sequence[ModuleCommand], decided: set[str]) -> set[str]:
    return {row.name for row in rows if row.name not in decided}


def ratchet_problems(
    rows: Sequence[ModuleCommand],
    decided: set[str],
    recorded: Sequence[str],
    in_tree: frozenset[str] = IN_TREE_SURFACES,
) -> list[str]:
    problems: list[str] = []
    if list(recorded) != sorted(set(recorded)):
        problems.append("the undecided list must be sorted, one name per line, no repeats")
    if len(recorded) > MAX_UNDECIDED:
        problems.append(f"more than {MAX_UNDECIDED} undecided names: escalate")
    now = undecided_names(rows, decided)
    problems += [
        f"{n}: undecided and not on the legacy list (the list never grows)"
        for n in sorted(now - set(recorded))
    ]
    outside = {row.name for row in rows if row.module not in in_tree}
    problems += [f"{n}: a command of a new module must be decided" for n in sorted(now & outside)]
    return problems


def proposable_rows(specs: Sequence[ModuleSpec], *, agent_only: bool) -> set[str]:
    return {
        p.model.__name__
        for spec in specs
        for p in spec.proposable
        if p.agent_tool or not agent_only
    }


# --- fakes -------------------------------------------------------------------------------------


def _noop(uow: Any, command: Any) -> Any:
    raise AssertionError("never run")


class Line(BaseModel):
    amount: int = 0


class Pay(Command):
    total: Decimal


class Batch(Command):
    lines: list[Line] = []


class Plain(Command):
    note: str = ""


def fake_row(model: type[Command], *, module: str = "x4fake", **meta: str) -> ModuleCommand:
    return ModuleCommand(module=module, model=model, handler=_noop, access="user", meta=meta)


# --- the tests ---------------------------------------------------------------------------------


def test_the_walk_finds_the_modules_and_the_commands_and_no_hook_failed() -> None:
    assert len(load_modules()) >= MIN_MODULES
    assert len(module_commands()) >= MIN_COMMANDS
    assert hook_failures() == {}


def test_every_row_has_a_word_the_authorizer_knows_and_the_one_its_module_declares() -> None:
    assert word_problems(module_commands(), load_modules()) == []


def test_the_word_check_sees_an_unknown_word_a_disagreement_and_a_partial_declaration() -> None:
    spec = ModuleSpec(
        name="x4fake",
        record_types=frozenset({"x4fake.T"}),
        projectors=list,
        command_words={"Plain": "user"},
    )
    unknown = ModuleCommand("x4fake", Plain, _noop, "no.such.word")
    differs = ModuleCommand("x4fake", Plain, _noop, "controller")
    partial = fake_row(Pay)
    assert len(word_problems([unknown], [spec])) == 2
    assert len(word_problems([differs], [spec])) == 1
    assert len(word_problems([partial], [spec])) == 1
    assert word_problems([ModuleCommand("x4fake", Plain, _noop, "user")], [spec]) == []


def test_money_fields_need_the_money_mark() -> None:
    assert money_problems(module_commands(), load_marks()) == []
    assert money_problems([fake_row(Plain)], Marks({}, {})) == []


def test_the_money_check_sees_a_decimal_a_nested_amount_and_a_name_with_no_mark() -> None:
    nothing = Marks({}, {})
    assert money_fields(Pay) == ["total"]
    assert money_fields(Batch) == ["lines.amount"]
    assert money_fields(Batch, nested=False) == []
    assert len(money_problems([fake_row(Pay)], nothing)) == 1
    assert len(money_problems([fake_row(Batch)], nothing)) == 1
    assert money_problems([fake_row(Pay, delegation="excluded:money")], nothing) == []
    assert money_problems([fake_row(Pay)], Marks({}, {"Pay": "money"})) == []
    # another reason is not the money reason
    assert len(money_problems([fake_row(Pay, delegation="excluded:reserved")], nothing)) == 1
    assert len(money_problems([fake_row(Pay, delegation="eligible")], nothing)) == 1


def test_every_command_is_a_proposable_row_or_an_exclusion_with_the_legacy_ratchet() -> None:
    decided = proposable_rows(load_modules(), agent_only=False) | load_exclusions()
    recorded = load_undecided()
    assert ratchet_problems(module_commands(), decided, recorded) == []
    # the undecided names are real commands that are still undecided or have since been decided
    assert set(recorded) <= {row.name for row in module_commands()}


def test_the_ratchet_refuses_growth_a_new_module_gap_and_an_unsorted_list() -> None:
    old = fake_row(Plain, module="awp")
    new = fake_row(Pay, module="x4fake")
    assert ratchet_problems([old], set(), []) != []  # grew
    assert ratchet_problems([old], set(), ["Plain"]) == []  # recorded: allowed
    assert ratchet_problems([old], {"Plain"}, ["Plain"]) == []  # shrank: allowed
    assert ratchet_problems([new], set(), ["Pay"]) != []  # a new module's gap is never allowed
    assert ratchet_problems([old], set(), ["Plain", "Plain"]) != []
    assert ratchet_problems([old], set(), [f"N{i}" for i in range(MAX_UNDECIDED + 1)]) != []


def test_every_command_has_exactly_one_valid_mark_and_the_file_is_clean() -> None:
    problems = mark_problems(
        module_commands(),
        load_marks(),
        agent_rows=proposable_rows(load_modules(), agent_only=True),
        exclusions=load_exclusions(),
    )
    assert problems == []
    marks = load_marks()
    assert marks.eligible  # the file really holds an eligible set


def test_the_mark_check_sees_stale_double_missing_bad_and_unfit_eligible_marks() -> None:
    plain, pay = fake_row(Plain, module="awp"), fake_row(Pay, module="awp")
    admin = ModuleCommand("awp", Batch, _noop, "admin")

    def check(
        rows: list[ModuleCommand], eligible: dict[str, str], excluded: dict[str, str], **kw: Any
    ) -> list[str]:
        args: dict[str, Any] = {"agent_rows": {"Plain", "Pay", "Batch"}, "exclusions": set()}
        return mark_problems(rows, Marks(eligible, excluded), **{**args, **kw})

    assert check([plain], {"Plain": "n"}, {}) == []
    assert any("stale" in p for p in check([plain], {"Plain": "n"}, {"Gone": "reserved"}))
    assert any("both" in p for p in check([plain], {"Plain": "n"}, {"Plain": "reserved"}))
    assert any("exactly one" in p for p in check([plain], {}, {}))
    assert any("bad mark" in p for p in check([plain], {}, {"Plain": "whim"}))
    assert any(
        "exactly one" in p
        for p in check(
            [fake_row(Plain, module="awp", delegation="eligible")], {}, {"Plain": "reserved"}
        )
    )
    # the same mark in meta and in the file is one mark
    assert check([fake_row(Plain, module="awp", delegation="eligible")], {"Plain": "n"}, {}) == []
    assert any("not an agent" in p for p in check([plain], {"Plain": "n"}, {}, agent_rows=set()))
    assert any("exclusions" in p for p in check([plain], {"Plain": "n"}, {}, exclusions={"Plain"}))
    assert any("admin" in p for p in check([admin], {"Batch": "n"}, {}))
    assert check([pay], {}, {"Pay": "money"}) == []


def test_a_module_outside_the_in_tree_set_carries_its_mark_in_row_meta() -> None:
    outside = fake_row(Plain, module="x4fake")
    kw: dict[str, Any] = {"agent_rows": set(), "exclusions": set()}
    in_file = mark_problems([outside], Marks({}, {"Plain": "reserved"}), **kw)
    assert any("row meta" in p for p in in_file)
    own = fake_row(Plain, module="x4fake", delegation="excluded:reserved")
    assert mark_problems([own], Marks({}, {}), **kw) == []
    bad = fake_row(Plain, module="x4fake", delegation="excluded:whim")
    assert any("bad mark" in p for p in mark_problems([bad], Marks({}, {}), **kw))


def test_the_marks_file_has_the_eligible_set_the_rules_give() -> None:
    marks = load_marks()
    by_name = {row.name: row for row in module_commands()}
    for name in marks.eligible:
        row = by_name[name]
        assert table_word(row.access) == "user", name


@pytest.fixture
def two_packages() -> Iterator[None]:
    for name in ("tl_mod_x4a", "tl_mod_x4b"):
        fake = types.ModuleType(name)
        fake.COMMANDS = (types.SimpleNamespace(model=Plain, handler=_noop, access="user"),)  # type: ignore[attr-defined]
        sys.modules[name] = fake
    try:
        yield
    finally:
        sys.modules.pop("tl_mod_x4a", None)
        sys.modules.pop("tl_mod_x4b", None)


def test_two_modules_declaring_one_command_name_stop_the_process_naming_both_not_a_ref(
    two_packages: None,
) -> None:
    def spec(name: str) -> ModuleSpec:
        return ModuleSpec(
            name=name,
            record_types=frozenset({f"{name}.T"}),
            projectors=list,
            commands=f"tl_mod_{name}:COMMANDS",
        )

    with use_modules([spec("x4a"), spec("x4b")]), pytest.raises(ModuleLoadError) as caught:
        module_commands()
    message = str(caught.value)
    assert "x4a" in message and "x4b" in message and "Plain" in message
    assert "tl_mod_" not in message and ":COMMANDS" not in message
