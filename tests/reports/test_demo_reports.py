"""`tl report` on a generated project ledger (V3-P0): every module report that has data there.

One small ledger (core, engineering, awp, constraints, requisitions, scaffold, materials,
correspondence, documents) is built once per run. For each report: the header is pinned, the row
count equals the module's own list view for the same viewer, JSONL equals the CSV rows, the low
viewer never has more rows than the controller, and for the reports with a restricted record
(documents in the ledger; an RFI made restricted in a copy) the low output is the full output
without that record's row, byte for byte. A ledger built without the generator's forms section has
no form data; those reports are in ``tests/confidentiality/test_reports_v3.py``.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.modules import module_reports
from tl_core.report_out import render
from tl_core.util import utcnow
from tl_mod_awp import iwp_reports
from tl_mod_awp import iwp_views as awp_iwp_views
from tl_mod_awp import report_rows as awp_rows
from tl_mod_awp import reports as awp_reports
from tl_mod_awp import views as awp_cwp_views
from tl_mod_correspondence import reports_technical
from tl_mod_correspondence import views as corr_views
from tl_mod_correspondence.handlers.confidentiality import (
    SetCorrespondenceConfidentiality,
    handle_set_confidentiality,
)
from tl_mod_correspondence.testing import frozen_today
from tl_mod_documents import reports as doc_reports
from tl_mod_engineering import registry as eng_registry
from tl_mod_engineering import report_rows as eng_rows
from tl_mod_permits import iso_views
from tl_mod_permits import report_rows as permit_rows
from tl_mod_permits import views as permit_views
from tl_mod_qr import report_rows as qr_rows
from tl_mod_quality import insp_views
from tl_mod_quality import report_rows as quality_rows
from tl_mod_quality import views as quality_views
from tl_mod_requisitions import report_rows as req_rows
from tl_mod_requisitions import views as req_views
from tl_mod_scaffold import views as scaffold_views
from tl_mod_schedule import registry as sched_registry
from tl_mod_schedule import report_rows as sched_rows
from tl_mod_schedule import views as sched_views

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = (
    "core,engineering,awp,constraints,requisitions,scaffold,materials,correspondence,documents,"
    "quality,permits,schedule"
)
SCOPE = "project:P200"
LOW = cf.Viewer(actor="user:ada")  # level 0, unnamed; ada holds the module view words
FULL = cf.Viewer(actor="user:ada", level=1, account="user:ada")

HEADERS = {
    "rfis": "number,subtype,state,discipline,raised_on,issued_on,required_by,answered_on,"
    "response_days,on_time,overdue,days_overdue,potential_cost_impact,potential_schedule_impact,"
    "cost_impact,schedule_impact,review_decision,class,subject",
    "correspondence": "number,kind,state,direction,domain,subtype,date,counterparty,response_due,"
    "class,subject",
    "documents": "number,state,doc_type,discipline,current_revision,current_status,current_class,"
    "current_issued_on,revisions,open_revision,stale_links,title",
    "scaffolds": "key,subject,state,tag,tagged_on,last_inspected_on,next_due_on,location,elevation,"
    "gridline,load_class,request_key",
    "awp-cwp-status": "state,discipline,count,budget_hours",
    "awp-wbs-vs-cost-code": "code,name,awp_budget_hours,cost_budget_hours,difference",
    "awp-cwa-sequence": "position,cwa,cwa_title,cwps,budget_hours",
    "awp-iwp-status": "state,discipline,count,estimated_hours",
    "awp-iwp-readiness": "number,ready,passing,total,blocked",
    "awp-constraint-log": "key,state,category,severity,owner,phase,due,age_days,aging",
    "materials-stock-on-hand": "Lot,Heat,Item,Description,Location,On hand,Reserved,Available,UOM",
    "materials-movement-log": "Date,Kind,Lot,Item,Qty,UOM,From,To,By,Reason",
    "materials-mto-status": None,
    "materials-shortages": None,
    "materials-consumables-by-cost-code": None,
    "form-submissions": "key,state,template,template_version,subject,answer_class,author,"
    "submitted_on,reviewed_by,reviewed_on",
    "form-templates": "key,title,version,state,intake,purpose,answer_class,bound_record_type,"
    "field_count,published_on,retired_on",
    "tags": "tag,class,state,title,area",
    "cwps": "number,title,state,discipline,cwa,planned_start,planned_finish,budget_hours,allocated",
    "iwps": "number,title,state,discipline,planned_start,planned_finish,foreman,estimated_hours,"
    "cwp_number,scope_count",
    "punch": "key,subject,state,category,area,system,due_on,assignee,raised_by,source_key",
    "inspections": "key,title,subject_key,for_key,state,point,area,planned_on,scheduled_for,"
    "inspector,result,done_on,punch_count",
    "permits": "key,subject,permit_type,state,area,holder,issued_at,valid_until,"
    "revalidation_count,closed_by,for_key",
    "isolations": "key,point_text,energy,method,lock_number,tag_number,state,applied_by,"
    "applied_at,verified_by,verified_at,depends",
    "requisitions": "key,kind,subject,state,requester,priority,need_by,approved_by",
    "activities": "schedule,snapshot,activity_id,name,state,planned_start,planned_finish,"
    "actual_start,actual_finish,total_float_hr",
    "qr-codes": "label_text,size,state,subject_key,issued_by,issued_at,expires_on,revoked_at",
    "work-orders": "key,work_kind,state,assigned_to,planned_start,planned_finish,actual_start,"
    "actual_finish,hours_planned,hours_actual",
}


@pytest.fixture(scope="module")
def ledger(tmp_path_factory: pytest.TempPathFactory) -> Path:
    reuse = os.environ.get("TL_REPORT_DEMO_DB")  # a ledger already built with SECTIONS (dev only)
    if reuse and Path(reuse).exists():
        return Path(reuse)
    base = tmp_path_factory.mktemp("demo-reports")
    db = base / "demo.db"
    env = {**os.environ, "TL_ENV": "dev", "PYTHONPATH": str(ROOT)}
    done = subprocess.run(
        [sys.executable, "-m", "dev.seed.demo_project", "--db", str(db), "--objects",
         str(base / "obj"), "--sections", SECTIONS],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-500:]
    return db


def out(db: Path, name: str, viewer: cf.Viewer, fmt: str = "csv") -> str:
    with open_uow(str(db), readonly=True) as uow:
        return "".join(render(module_reports()[name], uow.conn(), SCOPE, viewer, fmt))


def rows(body: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body)))[1:]


def _all_pages(read: object, page: int = 500) -> int:
    """Every row of a list read that clamps its limit: paged by offset until a short page."""
    total, offset = 0, 0
    while True:
        got = len(read(page, offset))  # type: ignore[operator]
        total += got
        offset += got
        if got < page:
            return total


def list_view_count(db: Path, name: str, viewer: cf.Viewer) -> int | None:
    """The row count the module's own view gives this viewer; None where a view has no count."""
    with open_uow(str(db), readonly=True) as uow, cf.use_viewer(viewer):
        conn = uow.conn()
        if name == "tags":
            return len(eng_registry.list_tags(conn, SCOPE, limit=1_000_000))
        if name == "cwps":
            return len(awp_cwp_views.cwp_list(conn, SCOPE))
        if name == "iwps":
            return _all_pages(lambda n, o: awp_iwp_views.iwp_list(conn, SCOPE, limit=n, offset=o))
        if name == "punch":
            return quality_views.punch_list(conn, SCOPE, limit=500, viewer=viewer).total
        if name == "inspections":
            return insp_views.inspection_list(conn, SCOPE, limit=500, viewer=viewer).total
        if name == "permits":
            return permit_views.permit_list(
                conn, SCOPE, now=utcnow(), limit=500, viewer=viewer
            ).total
        if name == "isolations":
            return iso_views.isolation_list(conn, SCOPE, limit=500, viewer=viewer).total
        if name == "work-orders":
            return _all_pages(
                lambda n, o: req_views.work_order_list(
                    conn, SCOPE, limit=n, offset=o, viewer=viewer
                )
            )
        if name == "requisitions":
            return _all_pages(
                lambda n, o: req_views.requisition_list(
                    conn, SCOPE, limit=n, offset=o, viewer=viewer
                )
            )
        if name == "activities":
            return sum(
                sched_views.activity_page(conn, SCOPE, s.code, limit=1).total
                for s in sched_registry.list_schedules(conn, SCOPE)
                if s.current_snapshot_id is not None
            )
        if name == "rfis":
            return reports_technical.rfi_log(conn, SCOPE, limit=1_000_000).total
        if name == "correspondence":
            return len(corr_views.register(conn, SCOPE, limit=1_000_000))
        if name == "documents":
            return len(doc_reports.document_register(conn, SCOPE, limit=1_000_000))
        if name == "scaffolds":
            return scaffold_views.scaffold_list(conn, SCOPE, limit=500, viewer=viewer).total
        if name == "awp-cwp-status":
            return len(awp_reports.cwp_status(conn, SCOPE))
        if name == "awp-cwa-sequence":
            return len(awp_reports.cwa_sequence(conn, SCOPE))
        if name == "awp-iwp-status":
            return len(iwp_reports.iwp_status(conn, SCOPE))
        if name == "awp-iwp-readiness":
            return len(iwp_reports.iwp_readiness(conn, SCOPE))
        if name == "awp-constraint-log":
            return len(iwp_reports.constraint_log(conn, SCOPE))
    return None


def test_every_registered_report_has_a_pinned_header() -> None:
    assert set(module_reports()) == set(HEADERS)


@pytest.mark.parametrize("name", [n for n, h in HEADERS.items() if h])
def test_the_header_is_pinned(ledger: Path, name: str) -> None:
    assert out(ledger, name, FULL).splitlines()[0] == HEADERS[name]
    assert out(ledger, name, LOW).splitlines()[0] == HEADERS[name]


@pytest.mark.parametrize("name", [n for n, h in HEADERS.items() if h and not n.startswith("form")])
def test_the_row_count_equals_the_list_view_and_jsonl_equals_csv(ledger: Path, name: str) -> None:
    for viewer in (LOW, FULL):
        body = out(ledger, name, viewer)
        counted = list_view_count(ledger, name, viewer)
        if counted is not None:
            assert len(rows(body)) == counted, (name, viewer.level)
    full = rows(out(ledger, name, FULL))
    lines = [json.loads(x) for x in out(ledger, name, FULL, "jsonl").splitlines()]
    assert len(lines) == len(full)
    assert len(rows(out(ledger, name, LOW))) <= len(full)
    for line, row in zip(lines, full, strict=True):
        assert [
            "" if v is None else str(v).lower() if isinstance(v, bool) else str(v)
            for v in line.values()
        ] == [c.removeprefix("'") if c.startswith("'") else c for c in row]


@pytest.mark.parametrize("name", ["rfis", "correspondence", "documents", "scaffolds"])
def test_each_module_report_has_rows(ledger: Path, name: str) -> None:
    assert len(rows(out(ledger, name, FULL))) > 0


def test_a_restricted_document_is_a_controller_row_and_not_a_low_row(ledger: Path) -> None:
    full, low = rows(out(ledger, "documents", FULL)), rows(out(ledger, "documents", LOW))
    assert len(full) == len(low) + 1
    gone = [r for r in full if r not in low]
    assert len(gone) == 1
    expected = [r for r in full if r != gone[0]]
    assert expected == low  # nothing else moved: no gap, no mark, no count
    assert gone[0][0] not in out(ledger, "documents", LOW)  # its number is nowhere in the output


def test_a_restricted_rfi_is_missing_for_the_low_viewer(ledger: Path, tmp_path: Path) -> None:
    copy = tmp_path / "copy.db"
    shutil.copy(ledger, copy)
    before_low = rows(out(copy, "rfis", LOW))
    before_full = rows(out(copy, "rfis", FULL))
    assert before_low == before_full  # the generated RFIs are all internal
    with open_uow(str(copy), readonly=True) as uow:
        row = (
            uow.conn()
            .exec_driver_sql(
                "SELECT t.id, r.key FROM cur_correspondence_technical_item t "
                "JOIN cur_core_record r ON r.id = t.id WHERE r.scope = ? ORDER BY r.key LIMIT 1",
                (SCOPE,),
            )
            .one()
        )
    cmd = SetCorrespondenceConfidentiality(
        actor="user:dora", source="test", scope=SCOPE, stream_id=row[0], to_class="restricted",
        grant=[], reason="test",
    )  # fmt: skip
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(str(copy)) as uow:
        handle_set_confidentiality(uow, cmd)
    after_low, after_full = rows(out(copy, "rfis", LOW)), rows(out(copy, "rfis", FULL))
    assert len(after_full) == len(before_full)  # the controller still has the row, now marked
    assert [r[:17] + r[18:] for r in after_full] == [r[:17] + r[18:] for r in before_full]
    assert [r[17] for r in after_full if r[0] == row[1]] == ["restricted"]
    assert after_low == [r for r in before_low if r[0] != row[1]]
    assert len(after_low) == len(before_low) - 1
    assert row[1] not in out(copy, "rfis", LOW)


# --- review follow-ups (V3-P0) ------------------------------------------------------------------


def lines_of(body: str) -> list[str]:
    return body.splitlines(keepends=True)


def test_hidden_is_missing_byte_for_byte_for_documents(ledger: Path) -> None:
    """The low viewer's text is the controller's text with the restricted document's line gone:
    same header, same other lines, nothing marks the place (key numbering is not claimed)."""
    full, low = lines_of(out(ledger, "documents", FULL)), lines_of(out(ledger, "documents", LOW))
    gone = [line for line in full if line not in low]
    assert len(gone) == 1
    assert [line for line in full if line != gone[0]] == low


def test_hidden_is_missing_byte_for_byte_for_rfis(ledger: Path, tmp_path: Path) -> None:
    copy = tmp_path / "copy.db"
    shutil.copy(ledger, copy)
    before = lines_of(out(copy, "rfis", LOW))
    with open_uow(str(copy), readonly=True) as uow:
        row = (
            uow.conn()
            .exec_driver_sql(
                "SELECT t.id, r.key FROM cur_correspondence_technical_item t "
                "JOIN cur_core_record r ON r.id = t.id WHERE r.scope = ? ORDER BY r.key LIMIT 1",
                (SCOPE,),
            )
            .one()
        )
    cmd = SetCorrespondenceConfidentiality(
        actor="user:dora", source="test", scope=SCOPE, stream_id=row[0], to_class="restricted",
        grant=[], reason="test",
    )  # fmt: skip
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(str(copy)) as uow:
        handle_set_confidentiality(uow, cmd)
    after = lines_of(out(copy, "rfis", LOW))
    assert after == [line for line in before if not line.startswith(row[1] + ",")]
    assert len(after) == len(before) - 1


def test_scaffolds_have_no_class_of_their_own(ledger: Path) -> None:
    """A scaffold is not a confidential record type: the low viewer gets the controller's bytes."""
    assert out(ledger, "scaffolds", LOW) == out(ledger, "scaffolds", FULL)


def test_a_hidden_linker_does_not_shift_stale_links(ledger: Path, tmp_path: Path) -> None:
    """``stale_links`` counts only links from records the viewer may read (a restricted record
    that links to a document leaves the low viewer's count where it was)."""
    copy = tmp_path / "copy.db"
    shutil.copy(ledger, copy)
    before = out(copy, "documents", LOW)
    full_rows, low_rows = rows(out(copy, "documents", FULL)), rows(before)
    hidden_number = next(r[0] for r in full_rows if r not in low_rows)
    shown_number = low_rows[0][0]
    with open_uow(str(copy)) as uow:
        conn = uow.conn()
        ids = {
            str(r.key): str(r.id)
            for r in conn.exec_driver_sql(
                "SELECT id, key FROM cur_core_record WHERE key IN (?, ?)",
                (hidden_number, shown_number),
            )
        }
        cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(cur_links)")]
        seed = dict(conn.exec_driver_sql("SELECT * FROM cur_links LIMIT 1").one()._mapping)
        seed.update(
            link_id="01TESTLINKSTALE0000000000A", from_id=ids[hidden_number],
            to_id=ids[shown_number], status="stale", scope=SCOPE,
        )  # fmt: skip
        conn.exec_driver_sql(
            f"INSERT INTO cur_links ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            tuple(seed[c] for c in cols),
        )
    assert out(copy, "documents", LOW) == before  # the low viewer's lines did not move
    shown = next(r for r in rows(out(copy, "documents", FULL)) if r[0] == shown_number)
    assert int(shown[10]) == int(next(r for r in low_rows if r[0] == shown_number)[10]) + 1


@pytest.mark.parametrize("page", [1, 2, 3, 7, 8])
def test_scaffold_report_pages_without_a_drop_or_a_repeat(
    monkeypatch: pytest.MonkeyPatch, page: int
) -> None:
    """The demo project has one scaffold, so the loop is run over seven made-up rows behind the
    same ``scaffold_list`` signature (the clamp ``MAX_LIMIT`` is the page size)."""
    from types import SimpleNamespace

    from tl_mod_scaffold import report_rows

    keys = [f"SCF-{n:04d}" for n in range(7)]

    def fake(conn: object, scope: str, *, limit: int, offset: int = 0, viewer: object = None):  # type: ignore[no-untyped-def]
        size = max(1, min(limit, scaffold_views.MAX_LIMIT))
        part = [
            SimpleNamespace(**{**dict.fromkeys(scaffold_views.EXPORT_COLUMNS), "key": k})
            for k in keys[offset : offset + size]
        ]
        return SimpleNamespace(rows=part, total=len(keys))

    monkeypatch.setattr(scaffold_views, "MAX_LIMIT", page)
    monkeypatch.setattr(scaffold_views, "scaffold_list", fake)
    monkeypatch.setattr(report_rows, "require_word", lambda *a, **k: None)
    monkeypatch.setattr(report_rows, "holder_for_actor", lambda *a, **k: None)
    got = [r["key"] for r in report_rows.scaffold_rows(None, SCOPE, FULL)]  # type: ignore[arg-type]
    assert got == keys


def test_scaffold_list_offset_pages_are_the_list(ledger: Path) -> None:
    with open_uow(str(ledger), readonly=True) as uow:
        conn = uow.conn()
        whole = scaffold_views.scaffold_list(conn, SCOPE, limit=500, viewer=FULL)
        keys: list[str] = []
        for offset in range(0, whole.total + 2, 2):
            part = scaffold_views.scaffold_list(conn, SCOPE, limit=2, offset=offset, viewer=FULL)
            assert part.total == whole.total
            keys.extend(r.key for r in part.rows)
        assert keys == [r.key for r in whole.rows]
        past = scaffold_views.scaffold_list(conn, SCOPE, offset=whole.total + 5, viewer=FULL)
        assert past.rows == [] and past.total == whole.total


# --- V3-P0b: the registered list reports ---------------------------------------------------------

#: The module that holds each paged report's ``_PAGE`` (the page size the monkeypatch makes small).
PAGED = {
    "tags": eng_rows,
    "iwps": awp_rows,
    "punch": quality_rows,
    "inspections": quality_rows,
    "permits": permit_rows,
    "isolations": permit_rows,
    "work-orders": req_rows,
    "requisitions": req_rows,
    "activities": sched_rows,
}


@pytest.mark.parametrize("name", sorted(PAGED))
def test_the_report_pages_the_same_at_every_page_size(
    ledger: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """A page of one row and a page of two give the same bytes as the report's own page size, for
    the controller and the low viewer (the offset walk neither drops nor repeats a row)."""
    whole = {v: out(ledger, name, v) for v in (LOW, FULL)}
    for size in (1, 2):
        monkeypatch.setattr(PAGED[name], "_PAGE", size)
        for viewer in (LOW, FULL):
            assert out(ledger, name, viewer) == whole[viewer], (name, size, viewer.level)


@pytest.mark.parametrize("name", ["punch", "inspections", "permits", "isolations"])
def test_a_hidden_row_is_missing_and_nothing_else_moves(ledger: Path, name: str) -> None:
    """Hidden is missing, byte for byte: the low viewer's lines are the controller's lines in the
    same order, minus whatever the viewer may not read. No gap, no mark, no count."""
    full, low = lines_of(out(ledger, name, FULL)), lines_of(out(ledger, name, LOW))
    assert full[0] == low[0]  # the pinned header
    remaining = iter(full)
    assert all(line in remaining for line in low)  # low is an ordered part of full
    assert len(low) <= len(full)


# --- V3-P0b review: the view word is checked before any header -----------------------------------

#: The reports whose list read takes a view word (checked by their rows function).
VIEW_WORD_REPORTS = {
    "punch": "quality.view",
    "inspections": "quality.view",
    "permits": "permits.view",
    "isolations": "permits.view",
    "work-orders": "requisitions.view",
    "requisitions": "requisitions.view",
    "qr-codes": "qr.view",
}


@pytest.mark.parametrize("name", sorted(VIEW_WORD_REPORTS))
def test_a_viewer_without_the_view_word_gets_the_refusal_and_no_header(
    ledger: Path, name: str
) -> None:
    """An actor that holds no module words is refused with the list read's own text, and the
    report writes nothing (not even the header), in CSV and in JSON lines."""
    from tl_core.auth.errors import ForbiddenError

    word = VIEW_WORD_REPORTS[name]
    # An agent with no account: the dev-ledger rule (a user: actor with no account holds the user
    # role, with the table word read) does not reach it, so it holds no module word.
    stranger = cf.Viewer(actor="agent:nobody-holds-words")
    for fmt in ("csv", "jsonl"):
        with pytest.raises(ForbiddenError, match=f"^{word} needs the "):
            out(ledger, name, stranger, fmt)


# --- V3-P0b review 13: records hidden through their subject link ---------------------------------

#: The table and the subject column of one record per report that a subject link hides
#: (``tl_core.confidentiality.SUBJECT_LINKS``). Work orders are below (two tables).
SUBJECT_COLUMN = {
    "punch": ("cur_quality_punch_item", "source_id"),
    "inspections": ("cur_quality_inspection", "subject_id"),
    "permits": ("cur_permits_permit", "for_record_id"),
    "isolations": ("cur_permits_isolation", "point_record_id"),
}
REQUISITION_TABLES = (
    "cur_requisitions_labor_requisition",
    "cur_requisitions_material_requisition",
    "cur_requisitions_general_requisition",
    "cur_requisitions_scaffold_request",
)


def restrict_first_rfi(copy: Path) -> tuple[str, str]:
    """Make the first RFI of the copy restricted (as ``test_a_restricted_rfi`` does). Returns its
    id and key."""
    with open_uow(str(copy), readonly=True) as uow:
        rfi_id, rfi_key = (
            uow.conn()
            .exec_driver_sql(
                "SELECT t.id, r.key FROM cur_correspondence_technical_item t "
                "JOIN cur_core_record r ON r.id = t.id WHERE r.scope = ? ORDER BY r.key LIMIT 1",
                (SCOPE,),
            )
            .one()
        )
    cmd = SetCorrespondenceConfidentiality(
        actor="user:dora", source="test", scope=SCOPE, stream_id=rfi_id, to_class="restricted",
        grant=[], reason="test",
    )  # fmt: skip
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(str(copy)) as uow:
        handle_set_confidentiality(uow, cmd)
    return str(rfi_id), str(rfi_key)


def point_subject_at(copy: Path, name: str, subject_id: str) -> str:
    """Point the subject of one record of ``name`` at ``subject_id`` in the copy (a test-only
    edit of the current-state table, as the documents test edits ``cur_links``). Returns that
    record's key.
    A work order's subject is its requisition's ``for_record_id``; the requisition is chosen to
    have one work order, so exactly one line of the report goes."""
    with open_uow(str(copy)) as uow:
        conn = uow.conn()
        if name == "work-orders":
            key, requisition = conn.exec_driver_sql(
                "SELECT r.key, w.requisition_id FROM cur_requisitions_work_order w "
                "JOIN cur_core_record r ON r.id = w.id WHERE r.scope = ? "
                "AND w.requisition_id IN (SELECT requisition_id FROM "
                "cur_requisitions_work_order GROUP BY requisition_id HAVING COUNT(*) = 1) "
                "ORDER BY r.key LIMIT 1",
                (SCOPE,),
            ).one()
            for table in REQUISITION_TABLES:
                conn.exec_driver_sql(
                    f"UPDATE {table} SET for_record_id = ? WHERE id = ?",
                    (subject_id, requisition),
                )
            return str(key)
        if name == "requisitions":
            first = min(
                (
                    (str(r[0]), str(r[1]), t)
                    for t in REQUISITION_TABLES
                    for r in conn.exec_driver_sql(
                        f"SELECT r.key, t.id FROM {t} t JOIN cur_core_record r ON r.id = t.id "
                        "WHERE r.scope = ? ORDER BY r.key LIMIT 1",
                        (SCOPE,),
                    )
                ),
            )  # the first key over the four kinds
            conn.exec_driver_sql(
                f"UPDATE {first[2]} SET for_record_id = ? WHERE id = ?", (subject_id, first[1])
            )
            return first[0]
        table, column = SUBJECT_COLUMN[name]
        key, record = conn.exec_driver_sql(
            f"SELECT r.key, t.id FROM {table} t JOIN cur_core_record r ON r.id = t.id "
            "WHERE r.scope = ? ORDER BY r.key LIMIT 1",
            (SCOPE,),
        ).one()
        conn.exec_driver_sql(f"UPDATE {table} SET {column} = ? WHERE id = ?", (subject_id, record))
        return str(key)


@pytest.mark.parametrize(
    "name", ["punch", "inspections", "permits", "isolations", "work-orders", "requisitions"]
)
def test_a_record_hidden_through_its_subject_is_missing_for_the_low_viewer(
    ledger: Path, tmp_path: Path, name: str
) -> None:
    """One record's subject is a restricted RFI. The controller has its line; the low viewer's
    text is the controller's text with that one line gone, and its key is nowhere in it."""
    copy = tmp_path / "copy.db"
    shutil.copy(ledger, copy)
    # The unedited ledger is the baseline: the demo already hides some rows of this report (for
    # example punch items raised from a restricted letter), so the copy must equal the baseline
    # minus this one record, not the controller's text minus it.
    base_full, base_low = lines_of(out(ledger, name, FULL)), lines_of(out(ledger, name, LOW))
    rfi_id, rfi_key = restrict_first_rfi(copy)
    key = point_subject_at(copy, name, rfi_id)
    full, low = lines_of(out(copy, name, FULL)), lines_of(out(copy, name, LOW))
    assert rfi_key in out(copy, "rfis", FULL)  # the restricted RFI exists for the controller
    assert rfi_key not in out(copy, "rfis", LOW)
    assert any(line.startswith(key + ",") for line in base_low)  # visible before: not vacuous
    assert any(line.startswith(key + ",") for line in full)  # the controller has the record
    assert key not in "".join(low)  # absent for the low viewer, nothing marks it
    assert low == [line for line in base_low if not line.startswith(key + ",")]
    assert [line for line in full if not line.startswith(key + ",")] == [
        line for line in base_full if not line.startswith(key + ",")
    ]


@pytest.mark.parametrize("name", ["tags", "cwps", "iwps"])
def test_a_report_with_no_subject_link_is_the_same_for_both_viewers(
    ledger: Path, name: str
) -> None:
    """Tags, CWPs and IWPs are not in ``SUBJECT_LINKS`` and carry no class of their own, so no
    viewer loses a row: the low viewer's bytes are the controller's (as scaffolds are)."""
    assert out(ledger, name, LOW) == out(ledger, name, FULL)


# --- V3-P0c: requisitions, activities, QR codes --------------------------------------------------


def test_requisition_list_offset_pages_are_the_list(ledger: Path) -> None:
    """Pages of two by ``offset`` over the merged kinds are the whole list, in order; an offset
    past the end is empty; the default offset is 0 (existing callers see no change)."""
    with open_uow(str(ledger), readonly=True) as uow:
        conn = uow.conn()
        whole = req_views.requisition_list(conn, SCOPE, limit=500, viewer=FULL)
        assert len({r.kind for r in whole}) > 1  # the merge of kinds is what the offset must cut
        keys: list[str] = []
        for offset in range(0, len(whole) + 2, 2):
            part = req_views.requisition_list(conn, SCOPE, limit=2, offset=offset, viewer=FULL)
            assert len(part) <= 2
            keys.extend(r.key for r in part)
        assert keys == [r.key for r in whole]
        assert req_views.requisition_list(conn, SCOPE, offset=len(whole) + 5, viewer=FULL) == []
        assert req_views.requisition_list(conn, SCOPE, limit=3, viewer=FULL) == whole[:3]


def test_the_requisition_report_has_every_kind(ledger: Path) -> None:
    body = rows(out(ledger, "requisitions", FULL))
    assert len(body) > 4
    assert {r[1] for r in body} >= {"general", "labor", "material"}
    assert len({r[0] for r in body}) == len(body)  # no key twice (the merge)


def test_the_activity_report_is_the_current_snapshot_of_each_schedule(ledger: Path) -> None:
    body = rows(out(ledger, "activities", FULL))
    assert body
    with open_uow(str(ledger), readonly=True) as uow:
        conn = uow.conn()
        want = {
            s.code: sched_registry.get_snapshot(conn, s.current_snapshot_id).number  # type: ignore[union-attr, arg-type]
            for s in sched_registry.list_schedules(conn, SCOPE)
            if s.current_snapshot_id is not None
        }
    assert {r[0]: int(r[1]) for r in body} == want
    assert out(ledger, "activities", LOW) == out(ledger, "activities", FULL)


def test_a_schedule_without_a_current_snapshot_adds_no_rows(
    ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = sched_registry.list_schedules

    def none_current(conn: object, scope: str) -> list[object]:
        import dataclasses

        return [dataclasses.replace(s, current_snapshot_id=None) for s in real(conn, scope)]  # type: ignore[arg-type]

    monkeypatch.setattr(sched_registry, "list_schedules", none_current)
    assert out(ledger, "activities", FULL).splitlines() == [HEADERS["activities"]]


CODE_COLUMNS = (
    "id, scope, code_hash, target_id, target_type, label_text, size, issued_by, issued_at, "
    "expires_on, revoked_at, last_seq"
)


def add_code(
    conn: object, target: str, label: str | None, issued_at: str, *, tag: str,
    expires_on: str | None = None, revoked_at: str | None = None,
) -> tuple[str, str]:  # fmt: skip
    """A scan code row written straight into the copy's current-state table (the module's
    issue path needs a card provider and settings that a report test does not). Returns the
    row's id and hash, so a test can look for them in the output."""
    code_id, code_hash = f"01TESTQRCODE{tag:0>14}", f"{tag:0>2}" * 32
    conn.exec_driver_sql(  # type: ignore[attr-defined]
        f"INSERT INTO cur_qr_scan_code ({CODE_COLUMNS}) VALUES (?, ?, ?, ?, 'x.Y', ?, 'tag', "
        "'user:uma', ?, ?, ?, 1)",
        (code_id, SCOPE, code_hash, target, label, issued_at, expires_on, revoked_at),
    )
    return code_id, code_hash


@pytest.fixture(scope="module")
def qr_ledger(
    ledger: Path, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Path, dict[str, str]]:
    """A copy of the ledger with scan codes: two on punch items, three on the first RFI (live,
    expired, revoked), the labels of two sharing one issue time. Returns the path and what the
    tests look for (the RFI key, the ids and hashes that must never appear)."""
    copy = tmp_path_factory.mktemp("qr") / "copy.db"
    shutil.copy(ledger, copy)
    with open_uow(str(copy), readonly=True) as uow:
        punch = [
            tuple(r)
            for r in uow.conn().exec_driver_sql(
                "SELECT t.id, r.key FROM cur_quality_punch_item t JOIN cur_core_record r "
                "ON r.id = t.id WHERE r.scope = ? ORDER BY r.key LIMIT 2",
                (SCOPE,),
            )
        ]
        rfi = tuple(
            uow.conn()
            .exec_driver_sql(
                "SELECT t.id, r.key FROM cur_correspondence_technical_item t "
                "JOIN cur_core_record r ON r.id = t.id WHERE r.scope = ? ORDER BY r.key LIMIT 1",
                (SCOPE,),
            )
            .one()
        )
    secret: list[str] = []
    with open_uow(str(copy)) as uow:
        conn = uow.conn()
        for tag, target, label, at, extra in (
            ("1", punch[0][0], "Pump", "2026-10-01T08:00:00", {}),
            ("2", punch[1][0], "Valve B", "2026-10-02T08:00:00", {}),
            ("3", punch[1][0], "Valve A", "2026-10-02T08:00:00", {}),
            ("4", rfi[0], "Letter", "2026-10-03T08:00:00", {}),
            ("5", rfi[0], None, "2026-10-04T08:00:00", {"expires_on": "2020-01-01"}),
            ("6", rfi[0], "Old", "2026-10-05T08:00:00", {"revoked_at": "2026-10-06T08:00:00"}),
        ):
            secret.extend(add_code(conn, target, label, at, tag=tag, **extra))
    return copy, {"rfi": str(rfi[1]), "punch": str(punch[0][1]), "secret": "\n".join(secret)}


def test_the_qr_report_rows_order_state_and_no_secret(
    qr_ledger: tuple[Path, dict[str, str]],
) -> None:
    copy, known = qr_ledger
    body = out(copy, "qr-codes", FULL)
    got = rows(body)
    assert [(r[0], r[2]) for r in got] == [
        ("Pump", "live"), ("Valve A", "live"), ("Valve B", "live"), ("Letter", "live"),
        ("", "expired"), ("Old", "revoked"),
    ]  # fmt: skip  # issue time, then label; the expired and revoked states are worked out
    assert got[0][3] == known["punch"]
    assert got[0][4:] == ["user:uma", "2026-10-01T08:00:00", "", ""]
    for secret in known["secret"].splitlines():  # no register id, no hash, in either format
        assert secret not in body
        assert secret not in out(copy, "qr-codes", FULL, "jsonl")
    assert "http" not in body.lower()


def test_the_qr_report_jsonl_equals_csv(qr_ledger: tuple[Path, dict[str, str]]) -> None:
    copy, _ = qr_ledger
    csv_rows = rows(out(copy, "qr-codes", FULL))
    lines = [json.loads(x) for x in out(copy, "qr-codes", FULL, "jsonl").splitlines()]
    assert [["" if v is None else str(v) for v in line.values()] for line in lines] == csv_rows


def test_the_qr_report_pages_the_same_at_every_page_size(
    qr_ledger: tuple[Path, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    copy, _ = qr_ledger
    whole = {v: out(copy, "qr-codes", v) for v in (LOW, FULL)}
    for size in (1, 2):
        monkeypatch.setattr(qr_rows, "_PAGE", size)
        for viewer in (LOW, FULL):
            assert out(copy, "qr-codes", viewer) == whole[viewer], (size, viewer.level)


def test_a_code_of_a_restricted_record_is_missing_for_the_low_viewer(
    qr_ledger: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    """The codes of an RFI that becomes restricted: the controller still has their lines; the low
    viewer's text is the unedited ledger's low text minus exactly those lines, byte for byte."""
    ledger_copy, known = qr_ledger
    copy = tmp_path / "copy.db"
    shutil.copy(ledger_copy, copy)
    base_low = lines_of(out(ledger_copy, "qr-codes", LOW))
    base_full = lines_of(out(ledger_copy, "qr-codes", FULL))
    mark = f",{known['rfi']},"
    assert sum(mark in line for line in base_low) == 3  # visible before: not vacuous
    restrict_first_rfi(copy)
    low, full = lines_of(out(copy, "qr-codes", LOW)), lines_of(out(copy, "qr-codes", FULL))
    assert full == base_full  # the controller loses nothing
    assert low == [line for line in base_low if mark not in line]
    assert known["rfi"] not in "".join(low)
    assert len(low) == len(base_low) - 3
