"""A webhook body hides the payload references the subscription's owner may not read (SR-X1 F3).

``Dispatcher.render_body`` redacts ``data.detail`` with the ``PAYLOAD_REFS`` rule that ``/events``
uses (ADR-0016): the field that names a hidden record is null, the keys stay, and the hidden id
is nowhere in the body text. A readable reference leaves the body as it was.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_core.webhooks.dispatch import Dispatcher
from tl_core.webhooks.envelope import build_envelope, to_body
from tl_core.webhooks.rows import OutboxRow
from tl_core.webhooks.uris import UriConfig

B_ID = "01HIDDENB00000000000000000"
SUBJECT = "01SUBJECT0000000000000000"
CLASS_TABLE = "whr_class"
OWNER = cf.Viewer("user:owner", 1, "user:owner")
STAMP = "2026-11-14T00:00:00+00:00"


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DbTarget]:
    target: DbTarget = tmp_path / "whr.db"
    create_schema(target)
    now = datetime(2026, 11, 14, tzinfo=UTC).isoformat()
    with open_uow(target) as uow:
        conn = uow.conn()
        conn.execute(text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)"))
        for rid, key in ((SUBJECT, "S-1"), (B_ID, "B-1")):
            conn.execute(
                text(
                    "INSERT INTO cur_core_record (id, key, type, scope, title, version, last_seq,"
                    " created_at, updated_at) VALUES (:i, :k, 'core.Record', 'project:P1', :k, 1,"
                    " 1, :n, :n)"
                ),
                {"i": rid, "k": key, "n": now},
            )
        conn.execute(text(f"INSERT INTO {CLASS_TABLE} VALUES (:i, 'internal')"), {"i": SUBJECT})
    source = ConfidentialSource(
        record_types=frozenset({"core.Record"}),
        table=CLASS_TABLE,
        id_column="id",
        class_column="cls",
    )
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])
    yield target


def set_class(target: DbTarget, cls: str | None) -> None:
    with open_uow(target) as uow:
        uow.conn().execute(text(f"DELETE FROM {CLASS_TABLE} WHERE id = :i"), {"i": B_ID})
        if cls is not None:
            uow.conn().execute(
                text(f"INSERT INTO {CLASS_TABLE} VALUES (:i, :c)"), {"i": B_ID, "c": cls}
            )


def event_row() -> OutboxRow:
    detail = {"document_id": B_ID, "revision_id": None, "pin_reason": "baseline"}
    return OutboxRow(
        seq=1,
        event_id="01EVENT00000000000000000",
        scope="project:P1",
        event_type="IWP.DocumentPinned",
        stream_id=SUBJECT,
        stream_type="awp.IWP",
        stream_version=1,
        subject_id=SUBJECT,
        actor="user:x",
        recorded_at=STAMP,
        correlation_id="c1",
        data={"origin": {"id": SUBJECT}, "changes": {}, "links": [], "detail": detail},
    )


def render(target: DbTarget, mode: str, viewer: cf.Viewer = OWNER) -> str:
    with open_uow(target) as uow, cf.use_viewer(viewer):
        return Dispatcher(lambda readonly=False: uow).render_body(uow, event_row(), mode)  # type: ignore[arg-type,call-arg]


@pytest.mark.parametrize("mode", ["delta", "full"])
def test_a_hidden_reference_is_null_with_the_same_keys_and_its_id_is_nowhere(
    db: DbTarget, mode: str
) -> None:
    body = render(db, mode)
    assert B_ID not in body
    detail = json.loads(body)["data"]["detail"]
    assert detail == {"document_id": None, "revision_id": None, "pin_reason": "baseline"}


@pytest.mark.parametrize("cls", ["internal", "restricted"])
@pytest.mark.parametrize("mode", ["delta", "full"])
def test_a_readable_reference_leaves_the_body_as_it_was(db: DbTarget, mode: str, cls: str) -> None:
    """The owner (level 1) reads a restricted record too, which the lowest viewer does not."""
    set_class(db, cls)
    body = render(db, mode)
    assert B_ID in body
    before = to_body(build_envelope(event_row(), "delta", UriConfig()))
    if mode == "delta":
        assert body == before  # byte-identical to the unredacted envelope
    assert json.loads(body)["data"]["detail"] == json.loads(before)["data"]["detail"]


def test_a_thin_body_has_no_detail_at_all(db: DbTarget) -> None:
    body = render(db, "thin")
    assert "detail" not in json.loads(body)["data"]
    assert B_ID not in body
