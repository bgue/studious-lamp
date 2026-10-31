"""The readiness contract harness (`tl_core.readiness.harness`) on one good and three broken checks.

W0-B1 writes this; the per-check tests of Phase 2 call ``check_readiness_contract`` the same way.
The good sample answers ``n_a`` (its dependency does not exist); the broken ones write, return a
detail over the bound, and watch a record type that does not exist.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.pool import StaticPool
from tl_core.readiness import (
    MAX_DETAIL_CHARS,
    CheckResult,
    ContractViolation,
    ContractWorld,
    IwpFacts,
    check_readiness_contract,
)

TODAY = date(2026, 10, 30)
RECORD_TYPES = frozenset({"awp.IWP", "documents.Revision"})


class Sample:
    """A check with settable behaviour; ``evaluate`` is replaced per case."""

    version = "1"

    def __init__(
        self,
        name: str,
        watches: frozenset[str],
        answer: Callable[[Connection, Sample], CheckResult],
    ) -> None:
        self.name = name
        self.watches = watches
        self._answer = answer

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        return self._answer(conn, self)


def _n_a(_conn: Connection, check: Sample) -> CheckResult:
    return CheckResult(
        name=check.name,
        version=check.version,
        state="n_a",
        detail="the sample module does not exist yet",
    )


def _writes(conn: Connection, check: Sample) -> CheckResult:
    conn.execute(text("INSERT INTO thing (id) VALUES (1)"))
    return _n_a(conn, check)


def _too_long(_conn: Connection, check: Sample) -> CheckResult:
    # model_construct skips validation, as a careless plugin could.
    return CheckResult.model_construct(
        name=check.name,
        version=check.version,
        state="blocked",
        detail="x" * (MAX_DETAIL_CHARS + 1),
        resolve_via=[],
        count_ok=None,
        count_total=None,
    )


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE thing (id INTEGER PRIMARY KEY)"))
    yield engine
    engine.dispose()


def make_world(engine: Engine, *, expect_n_a: bool = False) -> ContractWorld:
    return ContractWorld(
        open_readonly=engine.connect,
        iwp=IwpFacts(record_id="r1", scope="P123", key="P123-IWP-PIP-0001", status="Draft"),
        today=TODAY,
        record_types=RECORD_TYPES,
        expect_n_a=expect_n_a,
    )


def test_a_good_n_a_check_passes(engine: Engine) -> None:
    check = Sample("sample_check", frozenset({"awp.IWP"}), _n_a)
    check_readiness_contract(check, make_world(engine, expect_n_a=True))


def test_a_check_that_answers_ok_when_n_a_is_expected_is_refused(engine: Engine) -> None:
    def ok(_conn: Connection, check: Sample) -> CheckResult:
        return CheckResult(name=check.name, version=check.version, state="ok", detail="fine")

    check = Sample("sample_check", frozenset({"awp.IWP"}), ok)
    check_readiness_contract(check, make_world(engine))
    with pytest.raises(ContractViolation, match="n_a"):
        check_readiness_contract(check, make_world(engine, expect_n_a=True))


def test_a_check_that_writes_is_refused(engine: Engine) -> None:
    check = Sample("writing_check", frozenset({"awp.IWP"}), _writes)
    with pytest.raises(ContractViolation, match="write"):
        check_readiness_contract(check, make_world(engine))


def test_a_detail_over_the_bound_is_refused(engine: Engine) -> None:
    check = Sample("long_check", frozenset({"awp.IWP"}), _too_long)
    # The pydantic bound on `detail` answers first (model_construct skipped it at build time).
    with pytest.raises(ContractViolation, match="does not satisfy the CheckResult model"):
        check_readiness_contract(check, make_world(engine))


def test_watching_a_record_type_that_does_not_exist_is_refused(engine: Engine) -> None:
    check = Sample("watching_check", frozenset({"awp.NoSuchType"}), _n_a)
    with pytest.raises(ContractViolation, match="watches"):
        check_readiness_contract(check, make_world(engine))
