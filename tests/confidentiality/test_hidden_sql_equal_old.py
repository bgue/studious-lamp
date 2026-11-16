"""P2-IP-PERF1: the faster ``hidden_sql`` answers exactly what the old statement answered.

The old builder (one part per confidential source, each joined to every ``SUBJECT_LINKS`` table
twice on a ``COALESCE`` chain) is copied below as the reference (``old_hidden_sql``). The world is
written straight into the current-state tables so that every source, every child, both hops, a
dangling or missing subject, a chain deeper than two hops and the author-only draft rule are all in
play at once; the same ids must come back for each kind of viewer, as a whole set and one record at
a time (``only``), on SQLite and on Postgres.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

import pytest
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.confidentiality import (
    _DRAFT_TABLE,  # pyright: ignore[reportPrivateUsage]
    _HOPS,  # pyright: ignore[reportPrivateUsage]
    _LEVELS,  # pyright: ignore[reportPrivateUsage]
    ACCOUNT_PARAM,
    ACTOR_PARAM,
    DRAFT_TYPE,
    OWN_CLASS_TYPES,
    PRIVILEGED,
    SUBJECT_LINKS,
    Viewer,
    current_viewer,
)
from tl_core.modules import (
    ChildSource,
    ConfidentialSource,
    confidential_sources,
    is_module_record_type,
)

# --- the old builder, verbatim (reference) ------------------------------------------------------


def _types(types: Iterable[str]) -> str:
    return ", ".join(f"'{t}'" for t in sorted(types))  # names were checked by ConfidentialSource


def _allowed(source: ConfidentialSource, viewer: Viewer) -> str:
    null = source.null_class or ""
    cls = f"COALESCE(s.{source.class_column}, '{null}')"
    classes = ", ".join(f"'{c}'" for c in sorted(_LEVELS) if _LEVELS[c] <= viewer.level)
    clause = f"{cls} IN ({classes})"
    if source.clearance_table is not None and viewer.account:
        clause += (
            f" OR ({cls} = '{PRIVILEGED}' AND EXISTS (SELECT 1 FROM {source.clearance_table} c "
            f"WHERE c.{source.clearance_record_column} = s.{source.id_column} "
            f"AND c.{source.clearance_account_column} = :{ACCOUNT_PARAM}))"
        )
    return clause


def _only(only: str | None) -> str:
    """The extra condition that limits a part to the records asked about (``hr.id = :_cf_id``)."""
    return f" AND {only}" if only else ""


def _subject_chain() -> tuple[str, str]:
    """``(joins, id expression)`` of the record whose class governs ``hr``; only the tables of
    installed modules are named."""
    links = [link for link in SUBJECT_LINKS if is_module_record_type(link[0])]
    joins = " LEFT JOIN cur_core_constraint k ON k.id = hr.id AND hr.type = 'core.Constraint'"
    # the subject columns reached so far, the latest hop first (a flat COALESCE)
    found: list[str] = []
    for hop in range(_HOPS if links else 0):
        current = f"COALESCE({', '.join([*found, 'k.subject_id', 'hr.id'])})"
        hopped: list[str] = []
        for number, (_, table, id_column, subject_column) in enumerate(links):
            alias = f"q{hop}{number}"
            joins += f" LEFT JOIN {table} {alias} ON {alias}.{id_column} = {current}"
            hopped.append(f"{alias}.{subject_column}")
        found = [*hopped, *found]
    final = f"COALESCE({', '.join([*found, 'k.subject_id', 'hr.id'])})"
    return joins + f" LEFT JOIN cur_core_record rr ON rr.id = {final}", final


def _of_types(types: frozenset[str]) -> str:
    return f"rr.type IN ({_types(types)})"


def _own_draft(viewer: Viewer) -> str:
    """SQL that is true when ``hr`` is a submission the viewer wrote, a draft or submitted: its
    class does not hide it from its author, who knows the answers (its subject still can)."""
    if not viewer.account or not is_module_record_type(DRAFT_TYPE):
        return "1 = 0"
    return (
        f"EXISTS (SELECT 1 FROM {_DRAFT_TABLE} d WHERE d.id = hr.id AND d.author = :{ACTOR_PARAM})"
    )


def _source_hidden(source: ConfidentialSource, viewer: Viewer, only: str | None = None) -> str:
    joins, subj = _subject_chain()
    exempt = (
        f" AND NOT (hr.id = rr.id AND {_own_draft(viewer)})"
        if source.record_types & OWN_CLASS_TYPES
        else ""
    )
    return (
        f"SELECT hr.id FROM cur_core_record hr{joins} "
        f"WHERE {_of_types(source.record_types)}"
        f"{_only(only)}{exempt} "
        f"AND NOT EXISTS (SELECT 1 FROM {source.table} s WHERE s.{source.id_column} = {subj} "
        f"AND ({_allowed(source, viewer)}))"
    )


def _child_hidden(
    source: ConfidentialSource, child: ChildSource, viewer: Viewer, only: str | None = None
) -> str:
    """The children whose root is not readable. A flat join to the root: nesting one subquery
    inside another per level overflows SQLite's parser stack."""
    if child.hop is None:
        via, root_key = "", f"ch.{child.root_column}"
    else:
        table, key, root = child.hop
        via = f" JOIN {table} hop ON hop.{key} = ch.{child.root_column}"
        root_key = f"hop.{root}"
    joins, subj = _subject_chain()
    return (
        f"SELECT hr.id FROM cur_core_record hr{joins} "
        f"WHERE {_of_types(child.record_types)}"
        f"{_only(only)} "
        f"AND NOT EXISTS (SELECT 1 FROM {child.table} ch{via} "
        f"JOIN {source.table} s ON s.{source.id_column} = {root_key} "
        f"WHERE ch.{child.id_column} = {subj} AND ({_allowed(source, viewer)}))"
    )


def _own_hidden(source: ConfidentialSource, viewer: Viewer, only: str | None = None) -> str:
    """The records of ``OWN_CLASS_TYPES`` whose own row is not readable (no subject, no join); a
    draft is its author's whatever its class."""
    types = source.record_types & OWN_CLASS_TYPES
    return (
        f"SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ({_types(types)})"
        f"{_only(only)} AND NOT {_own_draft(viewer)} "
        f"AND NOT EXISTS (SELECT 1 FROM {source.table} s WHERE s.{source.id_column} = hr.id "
        f"AND ({_allowed(source, viewer)}))"
    )


def _draft_parts(viewer: Viewer, only: str | None = None) -> list[str]:
    """The drafts the viewer is not the author of: the draft itself, and a record whose governing
    subject is such a draft. Nothing when the forms module is not installed."""
    if not is_module_record_type(DRAFT_TYPE):
        return []
    # a viewer with no account (the default, an agent) is nobody's author; a draft with no
    # author is nobody's too
    other = f"(d.author IS NULL OR d.author <> :{ACTOR_PARAM})" if viewer.account else "1 = 1"
    own = (
        f"SELECT hr.id FROM cur_core_record hr JOIN {_DRAFT_TABLE} d ON d.id = hr.id "
        f"WHERE hr.type = '{DRAFT_TYPE}'{_only(only)} AND d.submitted_on IS NULL "
        f"AND {other}"
    )
    joins, subj = _subject_chain()
    governed = (
        f"SELECT hr.id FROM cur_core_record hr{joins} JOIN {_DRAFT_TABLE} d ON d.id = {subj} "
        f"WHERE hr.id <> {subj} AND rr.type = '{DRAFT_TYPE}'{_only(only)} "
        f"AND d.submitted_on IS NULL AND {other}"
    )
    return [own, governed]


def _source_parts(source: ConfidentialSource, viewer: Viewer, only: str | None = None) -> list[str]:
    """The root's hidden records, then each child's, then the records of an own-class type whose
    own row is not readable."""
    parts = [_source_hidden(source, viewer, only)] + [
        _child_hidden(source, child, viewer, only) for child in source.children
    ]
    if source.record_types & OWN_CLASS_TYPES:
        parts.append(_own_hidden(source, viewer, only))
    return parts


def old_hidden_sql(viewer: Viewer | None = None, *, only: str | None = None) -> str | None:
    """A ``SELECT id`` of every record ``viewer`` must not read; ``None`` when nothing is hidden.

    The text holds only names the modules declared and the bind parameter ``_cf_acct`` (see
    ``params_for``). A system viewer hides nothing (the author-only draft rule included).

    ``only`` is a condition on ``hr.id`` (``hr`` is the record under test) written by the caller
    (``hr.id = :_cf_id``, ``hr.id IN :_cf_ids`` or ``hr.id = l.from_id``, never user input): the
    answer is then the hidden records that also meet it, the same ids as the whole set would
    hold, but the database looks at those records and not at every confidential record.
    """
    who = viewer if viewer is not None else current_viewer()
    if who.system:
        return None
    parts: list[str] = []
    for source in confidential_sources():
        parts.extend(_source_parts(source, who, only))
    parts.extend(_draft_parts(who, only))
    return " UNION ALL ".join(parts) if parts else None


# --- the world ---

SCOPE = "project:P123"
ANN = Viewer(actor="user:ann", level=0, account="user:ann")  # cleared on c_priv, author of drafts
BO = Viewer(actor="user:bo", level=0, account="user:bo")  # author of other drafts
CTL = Viewer(actor="user:ctl", level=1, account="user:ctl")  # restricted, not named anywhere
CTL_ANN = Viewer(actor="user:ann", level=1, account="user:ann")  # restricted and cleared
AGENT = Viewer(actor="agent:x", level=0, account="")
VIEWERS = {
    "lowest": cf.LOWEST,
    "ann": ANN,
    "bo": BO,
    "ctl": CTL,
    "ctl_ann": CTL_ANN,
    "agent": AGENT,
    "restricted_agent": Viewer(actor="agent:y", level=1, account=""),
}

CORR = "correspondence.Correspondence"
DOC = "documents.Document"
LAB = "requisitions.LaborRequisition"
SUB = "forms.Submission"
PUNCH = "quality.PunchItem"
PERMIT = "permits.Permit"
TABLES = {
    CORR: "cur_correspondence_correspondence",
    DOC: "cur_documents_document",
    "legacy.LoadRun": "cur_legacy_load_run",
    LAB: "cur_requisitions_labor_requisition",
    "requisitions.MaterialRequisition": "cur_requisitions_material_requisition",
    "requisitions.GeneralRequisition": "cur_requisitions_general_requisition",
    "requisitions.ScaffoldRequest": "cur_requisitions_scaffold_request",
    "requisitions.WorkOrder": "cur_requisitions_work_order",
    PUNCH: "cur_quality_punch_item",
    SUB: "cur_forms_submission",
    "forms.IntakeItem": "cur_forms_intake_item",
    "forms.IntakeCode": "cur_forms_intake_code",
    "qr.ScanCode": "cur_qr_scan_code",
    "quality.Inspection": "cur_quality_inspection",
    PERMIT: "cur_permits_permit",
    "permits.Isolation": "cur_permits_isolation",
    "permits.GasTest": "cur_permits_gas_test",
    "correspondence.CorrespondenceThread": "cur_correspondence_correspondence_thread",
    "correspondence.ResponseClock": "cur_correspondence_response_clock",
    "documents.Revision": "cur_documents_revision",
    "documents.DerivedDocument": "cur_documents_derived_document",
    "documents.ProcessingJob": "cur_documents_processing_job",
    "core.Constraint": "cur_core_constraint",
}
Row = tuple[str, str, Mapping[str, Any]]  # (record id, type, columns of its type table)


def world_rows() -> list[Row]:
    """Every record the equivalence test reads; ``None`` as a type table skips the row."""
    r: list[Row] = []

    def add(rid: str, typ: str, **cols: Any) -> None:
        r.append((rid, typ, cols))

    # sources and their children
    add("c_int", CORR, confidentiality="internal")
    add("c_res", CORR, confidentiality="restricted")
    add("c_priv", CORR, confidentiality="privileged")
    add("c_bogus", CORR, confidentiality="bogus")
    add("c_none", "correspondence.TechnicalItem")  # confidential type, no source row
    add("th_res", "correspondence.CorrespondenceThread", governing_item_id="c_res")
    add("th_int", "correspondence.CorrespondenceThread", governing_item_id="c_int")
    add("th_priv", "correspondence.CorrespondenceThread", governing_item_id="c_priv")
    add("ck_res", "correspondence.ResponseClock", item_id="c_res")
    add("d_int", DOC, confidentiality="internal")
    add("d_res", DOC, confidentiality="restricted")
    add("d_null", DOC, confidentiality=None)
    add("d_priv", DOC, confidentiality="privileged")
    add("rev_res", "documents.Revision", document_id="d_res")
    add("rev_int", "documents.Revision", document_id="d_int")
    add("dd_res", "documents.DerivedDocument", source_document_id="d_res")
    add("dd_int", "documents.DerivedDocument", source_document_id="d_int")
    add("job_res", "documents.ProcessingJob", derived_id="dd_res")
    add("job_int", "documents.ProcessingJob", derived_id="dd_int")
    add("l_res", "legacy.LoadRun", confidentiality="restricted")
    add("l_int", "legacy.LoadRun", confidentiality="internal")
    # requisitions, work orders, punch items, constraints (one and two hops, dangling, deep)
    add("lab_res", LAB, for_record_id="c_res")
    add("lab_int", LAB, for_record_id="c_int")
    add("lab_none", LAB)
    add("lab_dangling", LAB, for_record_id="nowhere")
    add("lab_chain", LAB, for_record_id="lab_res")
    add("lab_deep", LAB, for_record_id="lab_chain")
    add("lab_priv", LAB, for_record_id="c_priv")
    add("mat_res", "requisitions.MaterialRequisition", for_record_id="c_res")
    add("gen_res", "requisitions.GeneralRequisition", for_record_id="c_res")
    add("scf_res", "requisitions.ScaffoldRequest", for_record_id="c_res")
    add("scf_int", "requisitions.ScaffoldRequest", for_record_id="c_int")
    add("wo_res", "requisitions.WorkOrder", requisition_id="lab_res")
    add("wo_int", "requisitions.WorkOrder", requisition_id="lab_int")
    add("wo_priv", "requisitions.WorkOrder", requisition_id="lab_priv")
    add("pu_c", PUNCH, source_id="c_res")
    add("pu_wo", PUNCH, source_id="wo_res")
    add("pu_int", PUNCH, source_id="c_int")
    add("pu_none", PUNCH)
    add("con_c", "core.Constraint", subject_id="c_res")
    add("con_int", "core.Constraint", subject_id="c_int")
    add("con_wo", "core.Constraint", subject_id="wo_res")
    add("con_priv", "core.Constraint", subject_id="c_priv")
    add("con_nowhere", "core.Constraint", subject_id="nowhere")
    # permits, gas tests, isolations, scan codes, inspections
    add("pm_res", PERMIT, for_record_id="c_res")
    add("pm_int", PERMIT, for_record_id="c_int")
    add("pm_priv", PERMIT, for_record_id="c_priv")
    add("pm_free", PERMIT)
    add("gt_res", "permits.GasTest", permit_id="pm_res")
    add("gt_priv", "permits.GasTest", permit_id="pm_priv")
    add("gt_int", "permits.GasTest", permit_id="pm_int")
    add("iso_res", "permits.Isolation", point_record_id="c_res")
    add("iso_none", "permits.Isolation")
    add("sc_pm", "qr.ScanCode", target_id="pm_res")
    add("sc_c", "qr.ScanCode", target_id="c_res")
    add("sc_int", "qr.ScanCode", target_id="pm_int")
    add("in_res", "quality.Inspection", subject_id="c_res")
    add("in_pm", "quality.Inspection", subject_id="pm_res")
    add("in_int", "quality.Inspection", subject_id="c_int")
    # forms: classes, drafts, authors, subjects, intake
    done = "2026-11-01"
    add("f_int", SUB, answer_class="internal", author="user:ann", submitted_on=done)
    add("f_res", SUB, answer_class="restricted", author="user:bo", submitted_on=done)
    add("f_priv", SUB, answer_class="privileged", author="user:bo", submitted_on=done)
    add("f_own_res", SUB, answer_class="restricted", author="user:ann", submitted_on=done)
    add("f_on_c", SUB, answer_class="internal", subject_id="c_res", submitted_on=done)
    add("f_on_int", SUB, answer_class="internal", subject_id="c_int", submitted_on=done)
    add("f_on_pu", SUB, answer_class="internal", subject_id="pu_c", submitted_on=done)
    add("f_on_wo", SUB, answer_class="internal", subject_id="pu_wo", submitted_on=done)
    add("d_ann", SUB, answer_class="internal", author="user:ann")
    add("d_bo", SUB, answer_class="internal", author="user:bo")
    add("d_noauth", SUB, answer_class="internal")
    add("d_ann_res", SUB, answer_class="restricted", author="user:ann")
    add("d_ann_nocls", SUB, author="user:ann")
    add("f_missing", SUB + "#norow")
    add("pu_on_dbo", PUNCH, source_id="d_bo")
    add("pu_on_dann", PUNCH, source_id="d_ann")
    add("in_on_dbo", "quality.Inspection", subject_id="d_bo")
    add("sc_on_dann", "qr.ScanCode", target_id="d_ann")
    add("f_on_dbo", SUB, answer_class="internal", subject_id="d_bo", submitted_on=done)
    add("ic_res", "forms.IntakeCode", context_id="c_res")
    add("ic_int", "forms.IntakeCode", context_id="c_int")
    add("ic_none", "forms.IntakeCode")
    add("ii_res", "forms.IntakeItem", code_id="ic_res")
    add("ii_int", "forms.IntakeItem", code_id="ic_int")
    add("ii_none", "forms.IntakeItem", code_id="ic_none")
    add("ii_ctx", "forms.IntakeItem", code_id="d_bo")
    # records no module knows
    add("other_1", "core.Note")
    add("other_2", "awp.IWP")
    return r


def _required(conn: Connection, table: str) -> dict[str, Any]:
    """A value for each column a row must give (not null, no default); ``count`` makes it unique."""
    if conn.dialect.name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})")).all()
        return {
            r[1]: "int" if "INT" in r[2].upper() else "text" for r in rows if r[3] and r[4] is None
        }
    found = conn.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = :t AND table_schema = current_schema() "
            "AND is_nullable = 'NO' AND column_default IS NULL ORDER BY ordinal_position"
        ),
        {"t": table},
    ).all()
    kinds = {
        "integer": "int",
        "bigint": "int",
        "smallint": "int",
        "boolean": "int",
        "numeric": "int",
    }
    return {
        r[0]: "when" if r[1].startswith(("timestamp", "date")) else kinds.get(r[1], "text")
        for r in found
    }


def build_world(conn: Connection, rows: list[Row] | None = None) -> list[str]:
    """Write the rows (each of a distinct value in every required column, so a unique key never
    clashes); ``cur_core_record`` gets one for each, its type table one when it has a row."""
    required: dict[str, dict[str, str]] = {}
    count = 0

    def insert(table: str, cols: Mapping[str, Any]) -> None:
        nonlocal count
        count += 1
        if table not in required:
            required[table] = _required(conn, table)
        make = {"int": count, "text": f"x{count}", "when": "2026-11-01T00:00:00+00:00"}
        values = {n: make[kind] for n, kind in required[table].items()}
        values.update(cols)
        names = ", ".join(values)
        marks = ", ".join(f":{k}" for k in values)
        conn.execute(text(f"INSERT INTO {table} ({names}) VALUES ({marks})"), values)

    ids: list[str] = []
    for rid, typ, cols in rows if rows is not None else world_rows():
        real = typ.removesuffix("#norow")
        record = {"id": rid, "type": real, "scope": SCOPE, "title": rid, "psets_json": "{}"}
        insert("cur_core_record", record)
        table = TABLES.get(real)
        if table is not None and typ == real:
            insert(table, {"id": rid, "scope": SCOPE, **cols})
        ids.append(rid)
    clearance = {
        "clearance_id": "cl1",
        "scope": SCOPE,
        "record_id": "c_priv",
        "account": "user:ann",
    }
    insert("cur_correspondence_clearance", clearance)
    return ids


@pytest.fixture
def world(new_db: Callable[[], DbTarget]) -> tuple[DbTarget, list[str]]:
    target = new_db()
    create_schema(target)
    with open_uow(target) as uow:
        ids = build_world(uow.conn())
    return target, ids


def ids_of(conn: Connection, sql: str | None, viewer: Viewer, **extra: Any) -> set[str]:
    """The ids ``sql`` answers (an empty set for ``None``, nothing hidden)."""
    if sql is None:
        return set()
    params = {**cf.params_for(sql, viewer), **extra}
    return {str(row[0]) for row in conn.execute(text(sql), params)}


def old_ids(conn: Connection, viewer: Viewer, **kw: Any) -> set[str]:
    return ids_of(conn, old_hidden_sql(viewer, **kw), viewer)


# --- tests ---


def test_the_world_has_every_source_and_both_hops() -> None:
    assert {s.table for s in confidential_sources()} >= {
        "cur_correspondence_correspondence",
        "cur_documents_document",
        "cur_forms_submission",
        "cur_legacy_load_run",
    }
    assert _HOPS == 2
    assert {row[0] for row in SUBJECT_LINKS if is_module_record_type(row[0])} == {
        row[0] for row in SUBJECT_LINKS
    }
    assert {typ for _, typ, _ in world_rows() if typ in TABLES} >= {row[0] for row in SUBJECT_LINKS}


@pytest.mark.parametrize("who", sorted(VIEWERS))
def test_the_whole_set_is_the_old_set(world: tuple[DbTarget, list[str]], who: str) -> None:
    target, ids = world
    viewer = VIEWERS[who]
    with open_uow(target, readonly=True) as uow:
        conn = uow.conn()
        old = ids_of(conn, old_hidden_sql(viewer), viewer)
        new = ids_of(conn, cf.hidden_sql(viewer), viewer)
        assert new == old
        assert old <= set(ids)
        # the world is rich enough that the answer is neither empty nor everything
        assert 0 < len(old) < len(ids) or who == "ctl_ann"


def test_the_viewers_are_told_apart(world: tuple[DbTarget, list[str]]) -> None:
    """Viewers differ, so the comparison can tell a wrong rule from a right one."""
    target, _ = world
    with open_uow(target, readonly=True) as uow:
        sets = {n: ids_of(uow.conn(), cf.hidden_sql(v), v) for n, v in VIEWERS.items()}
    assert len({frozenset(s) for s in sets.values()}) >= 5
    assert "d_bo" in sets["ann"] and "d_bo" not in sets["bo"]
    assert "d_ann" in sets["bo"] and "d_ann" not in sets["ann"]
    assert "c_priv" not in sets["ann"] and "c_priv" in sets["bo"]
    assert "pu_on_dbo" in sets["ann"] and "pu_on_dbo" not in sets["bo"]
    assert "d_ann_res" not in sets["ann"] and "d_ann_res" in sets["bo"]
    assert "con_wo" in sets["lowest"] and "con_wo" not in sets["ctl"]
    assert "gt_res" in sets["lowest"] and "gt_res" not in sets["ctl"]
    assert "ii_res" in sets["lowest"] and "sc_pm" in sets["lowest"] and "job_res" in sets["lowest"]


@pytest.mark.parametrize("who", sorted(VIEWERS))
def test_one_record_at_a_time_is_the_old_answer(
    world: tuple[DbTarget, list[str]], who: str
) -> None:
    """The ``only`` form: every record at once through a correlated condition (``not_hidden_each``
    and ``hidden_among`` use it), and a sample of single records through a bound id."""
    target, ids = world
    viewer = VIEWERS[who]
    each = "SELECT l.id FROM cur_core_record l WHERE l.id IN ({})"
    with open_uow(target, readonly=True) as uow:
        conn = uow.conn()
        whole = old_ids(conn, viewer)
        for build in (old_hidden_sql, cf.hidden_sql):
            sql = build(viewer, only="hr.id = l.id")
            assert sql is not None
            assert ids_of(conn, each.format(sql), viewer) == whole
        for rid in ids[::7]:
            only = "hr.id = :_cf_id"
            old = ids_of(conn, old_hidden_sql(viewer, only=only), viewer, _cf_id=rid)
            new = ids_of(conn, cf.hidden_sql(viewer, only=only), viewer, _cf_id=rid)
            assert new == old, rid
            assert cf.is_hidden(conn, rid, viewer) == (rid in whole)


@pytest.mark.parametrize("who", sorted(VIEWERS))
def test_the_row_filters_keep_the_same_records(world: tuple[DbTarget, list[str]], who: str) -> None:
    """``not_hidden`` and ``not_hidden_each`` over every record, and ``hidden_row_ids``."""
    target, ids = world
    viewer = VIEWERS[who]
    with open_uow(target, readonly=True) as uow:
        conn = uow.conn()
        old = old_ids(conn, viewer)
        visible = set(ids) - old
        clause, params = cf.not_hidden("r.id", viewer)
        kept = {
            str(x[0])
            for x in conn.execute(
                text(f"SELECT r.id FROM cur_core_record r WHERE {clause}"), params
            )
        }
        assert kept == visible
        clause, params = cf.not_hidden_each("r.id", viewer)
        kept = {
            str(x[0])
            for x in conn.execute(
                text(f"SELECT r.id FROM cur_core_record r WHERE {clause}"), params
            )
        }
        assert kept == visible
        assert set(cf.hidden_among(conn, ids, viewer)) == old


def test_a_system_viewer_hides_nothing_and_so_does_the_old_one(
    world: tuple[DbTarget, list[str]],
) -> None:
    with cf.system_view():
        assert cf.hidden_sql() is None
        assert old_hidden_sql() is None
