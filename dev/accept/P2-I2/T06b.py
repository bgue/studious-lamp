"""Acceptance for P2-I2-T06b: five n_a readiness checks (awp). SQLite, exit 0, one ``PASS <check>``
line per check; ``FAIL <check>`` and exit 1 otherwise.

Run: ``uv run python dev/accept/P2-I2/T06b.py``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool
from tl_core.readiness import (
    CheckResult,
    ContractWorld,
    IwpFacts,
    check_readiness_contract,
    load_checks,
)

TODAY = date(2026, 10, 30)
RECORD_TYPES = frozenset({"awp.IWP", "documents.Revision"})
MATERIALS = "materials_reserved"

EXPECTED: dict[str, str] = {
    "permits_planned": "not applicable yet: permit records are built in Phase 3",
    "inspections_planned": (
        "not applicable yet: inspection and test plan records are built in Phase 3"
    ),
    "labour_requested": (
        "not applicable yet: labour requisitions arrive with the requisitions module"
    ),
    "predecessors_handed_over": "not applicable yet: hand-over of predecessor work is not recorded",
    "model_slice_available": "not applicable yet: model records are built in Phase 3",
}

failures: list[str] = []


def passed(name: str) -> None:
    print(f"PASS {name}")


def check_one(name: str, body: Callable[[], None]) -> None:
    try:
        body()
    except AssertionError as exc:
        failures.append(f"{name}: {exc}")
        print(f"FAIL {name}")
    else:
        passed(name)


def main() -> int:
    checks: dict[str, Any] = load_checks()
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE thing (id INTEGER PRIMARY KEY)"))
    iwp = IwpFacts(record_id="r1", scope="P123", key="P123-IWP-PIP-0001", status="Draft")

    def loaded() -> None:
        missing = sorted(set(EXPECTED) - set(checks))
        assert not missing, f"not loaded: {missing}"
        assert MATERIALS in checks, "materials_reserved is no longer loaded"
        assert not (set(EXPECTED) & {MATERIALS}), "a name collides with materials_reserved"

    check_one("load_checks finds the five names", loaded)

    for name, detail in EXPECTED.items():

        def declared(name: str = name) -> None:
            check = checks[name]
            assert check.version == "1", f"version is {check.version!r}"
            assert check.watches == {"awp.IWP"}, f"watches is {set(check.watches)!r}"
            assert check.name == name, f"name is {check.name!r}"

        check_one(f"{name} declares version 1 and watches awp.IWP", declared)

        def contract(name: str = name) -> None:
            world = ContractWorld(engine.connect, iwp, TODAY, RECORD_TYPES, expect_n_a=True)
            check_readiness_contract(checks[name], world)

        check_one(f"{name} passes check_readiness_contract with n_a", contract)

        def answers(name: str = name, detail: str = detail) -> None:
            with engine.connect() as conn:
                result = checks[name].evaluate(conn, iwp, TODAY)
            assert isinstance(result, CheckResult), "evaluate did not return a CheckResult"
            assert result.state == "n_a", f"state is {result.state!r}"
            assert result.detail == detail, f"detail is {result.detail!r}"
            assert result.resolve_via == [], "resolve_via is not empty"
            assert result.count_ok is None and result.count_total is None, "counts are not None"

        check_one(f"{name} answers n_a with the fixed detail", answers)

        def no_statement(name: str = name) -> None:
            statements: list[str] = []

            def count(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
                statements.append(statement)

            with engine.connect() as conn:
                event.listen(conn, "before_cursor_execute", count)
                try:
                    checks[name].evaluate(conn, iwp, TODAY)
                finally:
                    event.remove(conn, "before_cursor_execute", count)
            assert not statements, f"ran {len(statements)} statement(s)"

        check_one(f"{name} runs no statement on a connection", no_statement)

    engine.dispose()
    if failures:
        print("FAILED:", *failures, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
