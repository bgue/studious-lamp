"""Acceptance for W0-B1 (P2-W0): readiness registry and harness, reserved prefixes, settings keys,
access words. SQLite, exit 0, one ``PASS <check>`` line per check.

Run: ``uv run python dev/accept/P2-W0/W0-B1.py``.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import tempfile
import types
from collections.abc import Callable
from datetime import date
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.pool import StaticPool
from tl_adapters.db import create_schema, open_uow
from tl_core import settings as S
from tl_core.auth.access_words import (
    TABLE_WORDS,
    AccessWordError,
    load_access_words,
    parse_access_words,
    table_word,
)
from tl_core.readiness import (
    MAX_DETAIL_CHARS,
    READINESS_ENTRY_POINT,
    CheckResult,
    ContractViolation,
    ContractWorld,
    IwpFacts,
    ReadinessLoadError,
    check_readiness_contract,
    load_checks,
)
from tl_core.services.errors import ReservedIdentifierError
from tl_core.services.reserved import refuse_reserved_fields

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "packages" / "tl-api" / "tests"))
os.environ.pop("TL_SCHEMA_DIR", None)
os.environ.setdefault("TL_ENV", "dev")  # as the justfile and the root conftest do

from harness import Harness  # noqa: E402  (the test-client pattern of packages/tl-api/tests)

TODAY = date(2026, 10, 30)
RECORD_TYPES = frozenset({"awp.IWP", "documents.Revision"})
failures: list[str] = []


def passed(name: str) -> None:
    print(f"PASS {name}")


def expect_raises(exc: type[BaseException], fn: Callable[[], object], what: str) -> None:
    try:
        fn()
    except exc:
        passed(what)
    except BaseException as other:  # noqa: BLE001
        failures.append(f"{what}: raised {type(other).__name__}, wanted {exc.__name__}")
        print(f"FAIL {what}")
    else:
        failures.append(f"{what}: did not raise")
        print(f"FAIL {what}")


def expect(condition: bool, what: str) -> None:
    if condition:
        passed(what)
    else:
        failures.append(what)
        print(f"FAIL {what}")


# --- readiness registry --------------------------------------------------------------------------


class Sample:
    version = "1"

    def __init__(
        self,
        name: str,
        answer: Callable[[Connection, Sample], CheckResult],
        watches: frozenset[str] = frozenset({"awp.IWP"}),
    ) -> None:
        self.name = name
        self.watches = watches
        self._answer = answer

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        return self._answer(conn, self)


def n_a(_conn: Connection, check: Sample) -> CheckResult:
    return CheckResult(
        name=check.name, version=check.version, state="n_a", detail="no sample module yet"
    )


def writes(conn: Connection, check: Sample) -> CheckResult:
    conn.execute(text("INSERT INTO thing (id) VALUES (1)"))
    return n_a(conn, check)


def too_long(_conn: Connection, check: Sample) -> CheckResult:
    return CheckResult.model_construct(
        name=check.name,
        version=check.version,
        state="blocked",
        detail="x" * (MAX_DETAIL_CHARS + 1),
        resolve_via=[],
        count_ok=None,
        count_total=None,
    )


def plugin(module: str, factory: Callable[[], object], name: str) -> EntryPoint:
    mod = types.ModuleType(module)
    mod.make = factory  # type: ignore[attr-defined]
    sys.modules[module] = mod
    return EntryPoint(name=name, value=f"{module}:make", group=READINESS_ENTRY_POINT)


def broken() -> object:
    raise RuntimeError("/secret/path/to/plugin")


def readiness() -> None:
    expect(
        set(load_checks())
        == {
            "inspections_planned",
            "labour_requested",
            "materials_reserved",
            "model_slice_available",
            "permits_planned",
            "predecessors_handed_over",
            "rfis_answered",
        },
        "load_checks() holds materials_reserved and rfis_answered",
    )
    one = plugin("w0b1_a", lambda: Sample("same_name", n_a), "a")
    two = plugin("w0b1_b", lambda: Sample("same_name", n_a), "b")
    expect_raises(
        ReadinessLoadError, lambda: load_checks([one, two]), "two checks with one name raise"
    )
    expect(set(load_checks([one])) == {"same_name"}, "one injected plugin loads by name")
    bad = plugin("w0b1_c", broken, "c")
    logging.disable(logging.CRITICAL)  # the registry logs the plugin's own error text
    try:
        load_checks([bad])
    except ReadinessLoadError as exc:
        expect("/secret" not in str(exc), "a plugin that fails to load raises ReadinessLoadError")
    else:
        expect(False, "a plugin that fails to load raises ReadinessLoadError")
    finally:
        logging.disable(logging.NOTSET)

    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE thing (id INTEGER PRIMARY KEY)"))
    iwp = IwpFacts(record_id="r1", scope="P123", key="P123-IWP-PIP-0001", status="Draft")

    def world(expect_n_a: bool = False) -> ContractWorld:
        return ContractWorld(engine.connect, iwp, TODAY, RECORD_TYPES, expect_n_a)

    check_readiness_contract(Sample("sample_check", n_a), world(expect_n_a=True))
    passed("harness passes a sample n_a check")
    expect_raises(
        ContractViolation,
        lambda: check_readiness_contract(Sample("writing_check", writes), world()),
        "harness refuses a writing check",
    )
    expect_raises(
        ContractViolation,
        lambda: check_readiness_contract(Sample("long_check", too_long), world()),
        "harness refuses an over-long detail",
    )
    expect_raises(
        ContractViolation,
        lambda: check_readiness_contract(
            Sample("watching_check", n_a, frozenset({"awp.NoSuchType"})), world()
        ),
        "harness refuses an unknown watches type",
    )
    engine.dispose()


# --- reserved identifiers ------------------------------------------------------------------------


def reserved() -> None:
    for field, value in (
        ("correlation_id", "rollup:x"),
        ("correlation_id", "ready:x"),
        ("correlation_id", "progress:x"),
        ("source", "job:x"),
    ):
        expect_raises(
            ReservedIdentifierError,
            lambda field=field, value=value: refuse_reserved_fields(**{field: value}),
            f"refuse_reserved_fields refuses {field}={value}",
        )
    with tempfile.TemporaryDirectory() as tmp:
        harness = Harness.build(Path(tmp))
        try:
            body = {"scope": "project:P123", "number": "ISO-9001", "title": "A document"}
            for extra in (
                {"correlation_id": "rollup:x"},
                {"correlation_id": "ready:x"},
                {"correlation_id": "progress:x"},
                {"source": "job:x"},
            ):
                refused = harness.client.post("/commands/RegisterDocument", json={**body, **extra})
                expect(
                    refused.status_code == 422
                    and refused.json().get("error") == "reserved_identifier",
                    f"API body {extra} is 422",
                )
        finally:
            harness.close()


# --- settings ------------------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "awp.iwp.ready_lead_weeks": 4,
    "awp.backlog.target_weeks": 4,
    "awp.iwp.size_hours": [60, 850],
    "awp.release.signoff_roles": ["superuser"],
    "awp.release.allow_unknown_checks": False,
    "awp.rules_of_credit.set": "",
    "awp.constraint.aging_days": 14,
    "awp.constraint.auto_raise": True,
    "awp.constraint.default_owners": [],
    "materials.receipt.mtr_required_categories": [],
    "scaffold.inspection.interval_days": 7,
}


def settings() -> None:
    expect(len(DEFAULTS) == 11, "eleven Phase 2 keys are expected")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "tl.db"
        create_schema(db)
        with open_uow(db, readonly=True) as uow:
            conn = uow.conn()
            for key, want in DEFAULTS.items():
                got = S.resolve(conn, key)
                expect(
                    got.value == want and got.origin == "default",
                    f"{key} reads {want!r} by default",
                )
            expect(
                len(S.resolve_all(conn)) == 28,
                "the platform file defines 28 keys (17 + 11)",
            )


# --- access words --------------------------------------------------------------------------------


def split_row(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def scan_spec(path: Path, prefix: str) -> dict[str, str]:
    """word -> table word from the §3 table's word and default-role columns."""
    found: dict[str, str] = {}
    in_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_section = line.startswith("## 3.")
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = split_row(line)
        if len(cells) < 3:
            continue
        word = re.fullmatch(rf"`({prefix}\.[a-z.]+)`", cells[1])
        if word is None:
            continue
        role = cells[2]
        table = "read" if "viewer" in role else "controller" if "superuser" in role else "user"
        if "user" not in role and "viewer" not in role and "superuser" not in role:
            raise SystemExit(f"cannot read the default role {role!r} of {word.group(1)}")
        previous = found.setdefault(word.group(1), table)
        if previous != table:
            raise SystemExit(f"{word.group(1)} has two default roles in {path.name}")
    return found


def access_words() -> None:
    specs = REPO / "docs" / "build-spec" / "specs"
    wanted = {
        **scan_spec(specs / "m3-wbs-cwp.md", "awp"),
        **scan_spec(specs / "m4-materials.md", "materials"),
    }
    expect(len(wanted) >= 20, f"the specs' section 3 name {len(wanted)} words")
    loaded = load_access_words()
    expect(set(wanted) <= set(loaded), "every spec word is a row of access-words.yaml")
    expect(
        all(loaded[w] == t for w, t in wanted.items()),
        "every word maps to the table word of its default role",
    )
    expect(set(loaded) == set(wanted), "the file holds no word the specs do not name")
    expect(table_word("user") == "user", 'table_word("user") == "user"')
    expect(
        all(table_word(w) == w for w in TABLE_WORDS)
        and table_word("awp.cwp.release") == "controller",
        "table words return themselves; a fine word returns its table word",
    )
    expect_raises(AccessWordError, lambda: table_word("awp.no.such"), "an unknown word is an error")
    text_ok = (REPO / "schema" / "settings" / "access-words.yaml").read_text(encoding="utf-8")
    expect_raises(
        AccessWordError,
        lambda: parse_access_words(text_ok.replace("awp.view: read", "awp.view: admin")),
        "a copy with an unknown table word raises AccessWordError",
    )
    expect_raises(
        AccessWordError,
        lambda: parse_access_words(text_ok + "  awp.view: user\n"),
        "a copy with a duplicate word raises AccessWordError",
    )


def main() -> int:
    readiness()
    reserved()
    settings()
    access_words()
    if failures:
        print("FAILED:", *failures, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
