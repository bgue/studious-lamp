"""The IWP work pack: data, escaping, drawings, the optional QR codes (P2-I5-T07a)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
from awp_world import SCOPE, World
from progress_world import ProgressWorld
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp import iwp_views
from tl_mod_awp.names import DOCUMENT_TYPE
from tl_mod_awp.pack import Rendered, build_pack_data, render_html

GENERATED = date(2026, 11, 9)
ISO = ("ISO-1", "ISO-2")


def pack(w: World, number: str, viewer: cf.Viewer | None = None) -> Rendered:
    with open_uow(w.db, readonly=True) as uow:
        data = build_pack_data(uow.conn(), SCOPE, number, viewer, generated_on=GENERATED)
    return render_html(data)


def number_of(w: World, iwp: str) -> str:
    return str(w.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=iwp))


@contextmanager
def hidden_documents(w: World, *docs: str) -> Iterator[None]:
    """The documents are restricted: the lowest viewer cannot read them (a test source)."""
    with open_uow(w.db) as uow:
        conn = uow.conn()
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS pk_doc_class (id TEXT PRIMARY KEY, cls TEXT)")
        )
        conn.execute(text("DELETE FROM pk_doc_class"))
        for row in w.rows("SELECT id FROM cur_core_record WHERE type = :t", t=DOCUMENT_TYPE):
            cls = "restricted" if row["id"] in docs else "internal"
            conn.execute(
                text("INSERT INTO pk_doc_class VALUES (:i, :c)"), {"i": row["id"], "c": cls}
            )
    source = ConfidentialSource(
        record_types=frozenset({DOCUMENT_TYPE}),
        table="pk_doc_class",
        id_column="id",
        class_column="cls",
    )
    real = core_modules.confidential_sources
    cf.confidential_sources = lambda: [*real(), source]  # type: ignore[attr-defined]
    try:
        yield
    finally:
        cf.confidential_sources = real  # type: ignore[attr-defined]


class Plant:
    def __init__(self, w: World, tmp: Path) -> None:
        self.w = w
        self.pw = ProgressWorld(w)
        self.iwp, self.items = self.pw.package(["10.0", "30.0"])
        self.docs: dict[str, str] = w.documents(tmp / "objects", *ISO)

    def pin(self, doc: str, pin: str | None = None) -> None:
        self.w.call("uma", "PinIwpDocument", iwp=self.iwp, document=self.docs[doc], pin=pin)

    @property
    def number(self) -> str:
        return number_of(self.w, self.iwp)


@pytest.fixture
def plant(world: World, tmp_path: Path) -> Plant:
    return Plant(world, tmp_path)


def test_cover_and_scope_rows_equal_the_views(plant: Plant) -> None:
    with open_uow(plant.w.db, readonly=True) as uow:
        conn = uow.conn()
        detail = iwp_views.iwp_detail(conn, SCOPE, plant.number)
        scope = iwp_views.iwp_scope(conn, SCOPE, plant.number)
        data = build_pack_data(conn, SCOPE, plant.number, None, generated_on=GENERATED)
    assert detail is not None and scope is not None
    assert (data.cover.number, data.cover.title, data.cover.state) == (
        detail.number,
        detail.title,
        detail.state,
    )
    assert [line.key for line in data.scope] == [s.number for s in scope]


def test_a_recorded_step_is_shown_on_its_scope_item(plant: Plant) -> None:
    plant.pw.manual(plant.iwp, plant.items[0])
    assert "Material received" in pack(plant.w, plant.number).html


def test_a_pinned_document_is_a_drawing_and_an_unpinned_link_is_not(plant: Plant) -> None:
    plant.pin("ISO-1", "A")
    plant.pin("ISO-2")
    with open_uow(plant.w.db, readonly=True) as uow:
        data = build_pack_data(uow.conn(), SCOPE, plant.number, None)
    assert [(d.key, d.pin) for d in data.drawings] == [("ISO-1", "A")]


def test_a_hidden_document_is_absent_and_nothing_of_it_is_in_the_html(plant: Plant) -> None:
    plant.pin("ISO-1", "A")
    plant.pin("ISO-2", "A")
    with hidden_documents(plant.w, plant.docs["ISO-2"]):
        page = pack(plant.w, plant.number).html
    assert "ISO-1" in page
    assert "ISO-2" not in page


def test_a_missing_iwp_is_a_record_not_found(plant: Plant) -> None:
    with open_uow(plant.w.db, readonly=True) as uow, pytest.raises(RecordNotFoundError):
        build_pack_data(uow.conn(), SCOPE, "NO-SUCH-IWP", None)


def test_titles_are_escaped_and_no_record_id_reaches_the_page(plant: Plant) -> None:
    iwp = plant.w.iwp('<script>x</script> "&')
    items = plant.w.items(["5.0"])
    plant.w.call("uma", "AddIwpScope", iwp=iwp, items=items)
    page = pack(plant.w, number_of(plant.w, iwp)).html
    assert "<script>x</script>" not in page
    assert "&lt;script&gt;x&lt;/script&gt; &quot;&amp;" in page
    ids = [iwp, *items, plant.iwp, *plant.items, *plant.docs.values()]
    assert [i for i in ids if i in page] == []


def test_with_segno_one_svg_per_drawing(plant: Plant) -> None:
    pytest.importorskip("segno")
    plant.pin("ISO-1", "A")
    plant.pin("ISO-2", "A")
    got = pack(plant.w, plant.number)
    assert got.qr is True
    assert got.html.count("<svg") == 2
    assert "QR codes not drawn" not in got.html


def test_without_segno_no_qr_and_the_note_is_present(
    plant: Plant, monkeypatch: pytest.MonkeyPatch
) -> None:
    plant.pin("ISO-1", "A")
    monkeypatch.setitem(sys.modules, "segno", None)  # the import fails
    got = pack(plant.w, plant.number)
    assert got.qr is False
    assert "<svg" not in got.html
    assert "QR codes not drawn: the pack extra is not installed." in got.notes


def test_the_same_call_twice_is_byte_equal(plant: Plant) -> None:
    assert pack(plant.w, plant.number).html == pack(plant.w, plant.number).html
