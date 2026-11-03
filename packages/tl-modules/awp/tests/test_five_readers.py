"""The five kinds of reader (ADR-0016) over the awp views, with a class put on awp records.

No awp record carries a confidentiality class (D22), so the walk gives them one: a test-only
confidential source (a table of ids and classes) covers the WBS nodes, areas, packages and the
schedule's activity refs. The readers are the five of the API and MCP walks: a plain user, a
document controller, an admin, a person named on a privileged record and an agent.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from awp_world import SCOPE, World, link_activity
from sqlalchemy import bindparam, text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.modules import ConfidentialSource, confidential_sources
from tl_mod_awp import views

READERS = {
    "bob": cf.Viewer(actor="user:bob", level=0, account="user:bob"),
    "ctl": cf.Viewer(actor="user:ctl", level=1, account="user:ctl"),
    "boss": cf.Viewer(actor="user:boss", level=1, account="user:boss"),
    "amy": cf.Viewer(actor="user:amy", level=0, account="user:amy"),
    "bot": cf.Viewer(actor="agent:bot", level=0, account=""),
}
#: What each reader may read of the classed records: restricted, privileged (named), nothing more.
READS_RESTRICTED = {"ctl", "boss"}
READS_PRIVILEGED = {"amy"}
TYPES = frozenset({"awp.WBSNode", "awp.CWA", "awp.CWP", "awp.EWPRef", "schedule.ActivityRef"})

CWP_RESTRICTED = "P123-CWP-PIP-0002"  # allocated to node 1.1.2
CWP_PRIVILEGED = "P123-CWP-PIP-0004"  # allocated to node 1.2.3
NODE_RESTRICTED = "1.1.2"
AREA_RESTRICTED = "A2"


class Classed:
    """The ledger with a class on some records, and the ids and words that must stay hidden."""

    def __init__(self, world: World, hidden: dict[str, str]) -> None:
        self.world = world
        self.hidden = hidden  # kind -> record id


@pytest.fixture
def classed(seeded: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Classed]:
    w = seeded
    cwp = {r.number: r.id for r in _read(w, views.cwp_list)}
    ref = link_activity(w, cwp["P123-CWP-PIP-0001"], tmp_path)
    ids = {
        "node": w.id_of(NODE_RESTRICTED),
        "area": w.id_of(AREA_RESTRICTED, "awp.CWA"),
        "cwp": cwp[CWP_RESTRICTED],
        "private_cwp": cwp[CWP_PRIVILEGED],
        "ref": ref,
    }
    with open_uow(w.db) as uow:
        conn = uow.conn()
        conn.execute(text("CREATE TABLE t11_class (id TEXT PRIMARY KEY, cls TEXT NOT NULL)"))
        conn.execute(
            text("CREATE TABLE t11_clear (record_id TEXT NOT NULL, account TEXT NOT NULL)")
        )
        wanted = {
            ids["node"]: "restricted",
            ids["area"]: "restricted",
            ids["cwp"]: "restricted",
            ids["private_cwp"]: "privileged",
            ids["ref"]: "restricted",
        }
        everything = conn.execute(
            text("SELECT id FROM cur_core_record WHERE type IN :t").bindparams(
                bindparam("t", expanding=True)
            ),
            {"t": sorted(TYPES)},
        )
        for (record_id,) in everything.all():
            conn.execute(
                text("INSERT INTO t11_class (id, cls) VALUES (:i, :c)"),
                {"i": record_id, "c": wanted.get(record_id, "internal")},
            )
        conn.execute(
            text("INSERT INTO t11_clear (record_id, account) VALUES (:r, :a)"),
            {"r": ids["private_cwp"], "a": "user:amy"},
        )
    source = ConfidentialSource(
        record_types=TYPES,
        table="t11_class",
        id_column="id",
        class_column="cls",
        clearance_table="t11_clear",
    )

    def sources() -> list[ConfidentialSource]:
        return [*confidential_sources(), source]

    monkeypatch.setattr(cf, "confidential_sources", sources)
    yield Classed(w, ids)


def _read(w: World, fn, *args, **kw):  # type: ignore[no-untyped-def]
    with open_uow(w.db, readonly=True) as uow:
        return fn(uow.conn(), SCOPE, *args, **kw)


def as_reader(c: Classed, name: str, fn, *args, **kw):  # type: ignore[no-untyped-def]
    with cf.use_viewer(READERS[name]):
        return _read(c.world, fn, *args, **kw)


def sees(name: str, kind: str) -> bool:
    """Whether reader ``name`` may read a record of the class this fixture gave ``kind``."""
    if kind == "private_cwp":
        return name in READS_PRIVILEGED
    return name in READS_RESTRICTED


@pytest.mark.parametrize("reader", sorted(READERS))
def test_the_cwp_register_and_detail_show_each_reader_only_the_packages_they_may_read(
    classed: Classed, reader: str
) -> None:
    numbers = [r.number for r in as_reader(classed, reader, views.cwp_list)]
    assert (CWP_RESTRICTED in numbers) == sees(reader, "cwp")
    assert (CWP_PRIVILEGED in numbers) == sees(reader, "private_cwp")
    assert "P123-CWP-PIP-0001" in numbers  # the reader does read some
    for number, kind in ((CWP_RESTRICTED, "cwp"), (CWP_PRIVILEGED, "private_cwp")):
        detail = as_reader(classed, reader, views.cwp_detail, number)
        assert (detail is not None) == sees(reader, kind), (reader, number)
        absent = as_reader(classed, reader, views.cwp_detail, "P123-CWP-PIP-9999")
        if not sees(reader, kind):
            assert detail == absent  # a hidden CWP answers as one that never existed


@pytest.mark.parametrize("reader", sorted(READERS))
def test_the_wbs_tree_and_its_counts_do_not_tell_a_reader_about_hidden_packages(
    classed: Classed, reader: str
) -> None:
    """S3F3: tree counts. Node 1.1.2 is restricted, CWP PIP-0002 sits on it, PIP-0004 on 1.2.3."""
    rows = {r.code: r for r in as_reader(classed, reader, views.wbs_tree)}
    allowed_restricted = reader in READS_RESTRICTED
    assert (NODE_RESTRICTED in rows) == allowed_restricted
    hidden_cwps = (0 if allowed_restricted else 1) + (0 if reader in READS_PRIVILEGED else 1)
    assert rows["1"].cwp_count == 6 - hidden_cwps
    assert rows["1.1"].cwp_count == 3 - (0 if allowed_restricted else 1)
    assert rows["1.2"].cwp_count == 3 - (0 if reader in READS_PRIVILEGED else 1)
    detail = as_reader(classed, reader, views.wbs_detail, NODE_RESTRICTED)
    assert (detail is not None) == allowed_restricted
    assert as_reader(classed, reader, views.wbs_detail, "9.9.9") is None


@pytest.mark.parametrize("reader", sorted(READERS))
def test_the_path_lookup_leaves_out_the_steps_of_areas_a_reader_may_not_read(
    classed: Classed, reader: str
) -> None:
    """S3F2: the path lookup (and the area register) honour the class of an area."""
    path = as_reader(classed, reader, views.path)
    codes = [s.cwa for s in path.steps]
    areas = [a.code for a in as_reader(classed, reader, views.cwa_list)]
    if reader in READS_RESTRICTED:
        assert codes == ["A1", "A2", "A3", "A4"]
        assert areas == ["A1", "A2", "A3", "A4"]
    else:
        assert codes == ["A1", "A3", "A4"]
        assert areas == ["A1", "A3", "A4"]
    versions = as_reader(classed, reader, views.path_versions)
    assert versions[0].step_count == len(codes)
    rows = {r.number: r.cwa for r in as_reader(classed, reader, views.cwp_list)}
    assert rows["P123-CWP-PIP-0003"] == ("A2" if reader in READS_RESTRICTED else None)


@pytest.mark.parametrize("reader", sorted(READERS))
def test_every_awp_read_holds_no_id_or_code_the_reader_may_not_read(
    classed: Classed, reader: str
) -> None:
    dumps = [
        *(r.model_dump_json() for r in as_reader(classed, reader, views.cwp_list)),
        *(r.model_dump_json() for r in as_reader(classed, reader, views.wbs_tree)),
        *(r.model_dump_json() for r in as_reader(classed, reader, views.cwa_list)),
        as_reader(classed, reader, views.path).model_dump_json(),
        *(v.model_dump_json() for v in as_reader(classed, reader, views.path_versions)),
        *(
            d.model_dump_json()
            for number in ("P123-CWP-PIP-0001", "P123-CWP-PIP-0003")
            if (d := as_reader(classed, reader, views.cwp_detail, number)) is not None
        ),
    ]
    blob = " ".join(dumps)
    assert "P123-CWP-PIP-0001" in blob  # the reader reads something, so the check can fail
    for kind in ("node", "area", "cwp", "private_cwp"):
        if not sees(reader, kind):
            assert classed.hidden[kind] not in blob, (reader, kind)
    if not sees(reader, "cwp"):
        assert CWP_RESTRICTED not in blob
        assert f'"code":"{NODE_RESTRICTED}"' not in blob
    if not sees(reader, "private_cwp"):
        assert CWP_PRIVILEGED not in blob


@pytest.mark.parametrize("reader", sorted(READS_RESTRICTED))
def test_the_readers_of_a_restricted_activity_ref_see_the_link_on_the_cwp(
    classed: Classed, reader: str
) -> None:
    detail = as_reader(classed, reader, views.cwp_detail, "P123-CWP-PIP-0001")
    assert [a.ref_key for a in detail.activities] == ["MAIN/A1000"]
    assert detail.activities[0].resolution.state == "current"
