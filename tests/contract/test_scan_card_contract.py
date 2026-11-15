"""The scan-card contract harness (P2-QR T03) on one good provider and the broken ones it must catch.

P2-QR T04 and T05, P2-INSP T09 and P2-PTW T09 call ``check_scan_card_contract`` on their own provider the same way.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.pool import StaticPool
from tl_core.confidentiality import LOWEST, Viewer
from tl_core.qr.types import ScanCard, ScanLine

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scan_card_harness import ScanCardContractViolation, check_scan_card_contract  # noqa: E402

NOW = datetime(2026, 12, 10, 9, 0, tzinfo=UTC)
VISIBLE = "01HVISIBLE0000000000000001"
HIDDEN = "01HHIDDEN00000000000000001"
PRIVILEGED = Viewer(actor="boss", level=1, account="boss")


def _card(record_type: str = "fake.Thing") -> ScanCard:
    return ScanCard(
        record_type=record_type,
        key="F-0001",
        title="A thing",
        banner="OK",
        tone="go",
        as_of=NOW,
        valid_until=None,
        lines=[ScanLine(label="Area", value="north")],
        open_path="/web/records/F-0001",
    )


class Fake:
    """A provider with settable behaviour; the good one answers a card for VISIBLE only, for any viewer."""

    record_type = "fake.Thing"
    view_word = "fake.view"

    def __init__(self, card: Callable[[Connection, str, Viewer, datetime], ScanCard | None] | None = None) -> None:
        self._card = card or self._good

    def _good(self, conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> ScanCard | None:
        if record_id == HIDDEN and viewer.level == 0:
            return None
        return _card() if record_id in (VISIBLE, HIDDEN) else None

    def card(self, conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> ScanCard | None:
        return self._card(conn, record_id, viewer, now)


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE thing (id INTEGER)"))
    return eng


def run(engine: Engine, provider: object) -> ScanCard:
    with engine.connect() as conn:
        return check_scan_card_contract(
            provider,
            conn,
            visible_id=VISIBLE,
            hidden_id=HIDDEN,
            privileged=PRIVILEGED,
            now=NOW,
        )


def test_good_provider_passes_and_returns_the_card(engine: Engine) -> None:
    assert run(engine, Fake()).key == "F-0001"


def test_provider_without_the_protocol_members_is_refused(engine: Engine) -> None:
    class NoWord:
        record_type = "fake.Thing"

        def card(self, conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> ScanCard | None:
            return None

    with pytest.raises(ScanCardContractViolation, match="protocol"):
        run(engine, NoWord())


def test_view_word_must_be_a_dotted_word(engine: Engine) -> None:
    bad = Fake()
    bad.view_word = "view"
    with pytest.raises(ScanCardContractViolation, match="view_word"):
        run(engine, bad)


def test_card_for_the_wrong_record_type_is_refused(engine: Engine) -> None:
    with pytest.raises(ScanCardContractViolation, match="record_type"):
        run(engine, Fake(lambda c, i, v, n: _card("other.Thing") if i == VISIBLE else None))


def test_a_card_for_a_hidden_record_is_refused(engine: Engine) -> None:
    with pytest.raises(ScanCardContractViolation, match="hidden"):
        run(engine, Fake(lambda c, i, v, n: _card()))


def test_a_miss_for_the_visible_record_is_refused(engine: Engine) -> None:
    with pytest.raises(ScanCardContractViolation, match="visible"):
        run(engine, Fake(lambda c, i, v, n: None))


def test_an_unknown_id_must_answer_none_not_raise(engine: Engine) -> None:
    def boom(conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> ScanCard | None:
        if record_id not in (VISIBLE, HIDDEN):
            raise KeyError(record_id)
        return _card() if record_id == VISIBLE or viewer.level else None

    with pytest.raises(ScanCardContractViolation, match="raised"):
        run(engine, Fake(boom))


def test_garbage_ids_must_answer_none(engine: Engine) -> None:
    seen: list[str] = []

    def spy(conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> ScanCard | None:
        seen.append(record_id)
        return _card() if record_id == VISIBLE or (record_id == HIDDEN and viewer.level) else None

    run(engine, Fake(spy))
    assert "" in seen and any(len(s) > 200 for s in seen)


def test_a_provider_that_writes_is_refused(engine: Engine) -> None:
    def writes(conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> ScanCard | None:
        conn.execute(text("INSERT INTO thing (id) VALUES (1)"))
        return _card() if record_id == VISIBLE or (record_id == HIDDEN and viewer.level) else None

    with pytest.raises(ScanCardContractViolation, match="write"):
        run(engine, Fake(writes))


def test_the_lowest_viewer_is_the_one_used_for_the_hidden_check(engine: Engine) -> None:
    levels: list[int] = []

    def spy(conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> ScanCard | None:
        if record_id == HIDDEN:
            levels.append(viewer.level)
        return _card() if record_id == VISIBLE or (record_id == HIDDEN and viewer.level) else None

    run(engine, Fake(spy))
    assert 0 in levels and 1 in levels
    assert LOWEST.level == 0
