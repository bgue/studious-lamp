# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false
"""The document marts of the lake (P1-I8-T08; brief 28.2 gold, 28.4 uses).

STUB: this file is the interface P1-I8-T08 implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it.

Marts are rebuilt from silver whenever the document tables changed, so a mart never disagrees with
the silver it came from. Silver already holds only the documents and revisions the lowest reader
may read (``tl_lake.sync``, ADR-0016), so a mart holds none of the others, in a row or in a count.

* ``mart_document_status``: one row per project, discipline, document type and current revision
  status: how many documents, and the first and last issue date among them.
* ``mart_document_turnaround``: one row per project and discipline: documents with an issued
  revision, issued revisions, the average and the longest gap in days between a document's
  consecutive issued revisions.
* ``mart_document_issues``: one row per project and month: revisions issued and documents involved.

Voided documents are in none of them. No document at all means no mart (and a stale one is dropped).
"""

from __future__ import annotations

from tl_lake.duck import Duck, lake_tables, table_ref

DOCUMENT_TABLE = "cur_documents_document"
REVISION_TABLE = "cur_documents_revision"
RECORD_TABLE = "cur_core_record"
STATUS_TABLE = "mart_document_status"
TURNAROUND_TABLE = "mart_document_turnaround"
ISSUES_TABLE = "mart_document_issues"
MARTS = (STATUS_TABLE, TURNAROUND_TABLE, ISSUES_TABLE)


def build_document_marts(con: Duck) -> None:
    """Replace the three document marts from the silver tables of the lake.

    Silver columns the SQL may use: ``cur_core_record`` (``id``, ``voided``);
    ``cur_documents_document`` (``id``, ``scope``, ``discipline``, ``doc_type``,
    ``current_revision_status``, ``current_revision_issued_on``); ``cur_documents_revision``
    (``id``, ``scope``, ``document_id``, ``ordinal``, ``issued_on``). All text is VARCHAR; the
    issue dates are text that starts ``YYYY-MM-DD`` or is empty or is not a date at all.
    """
    # STEPS
    # 1. DROP TABLE IF EXISTS for each name in MARTS (use table_ref(name)).
    # 2. Stop (return) when lake_tables(con) lacks any of DOCUMENT_TABLE, REVISION_TABLE or
    #    RECORD_TABLE, or when the document table has no row (SELECT count(*)).
    # 3. mart_document_status: CREATE TABLE ... AS SELECT d.scope, COALESCE(d.discipline, '-') AS
    #    discipline, COALESCE(d.doc_type, '-') AS doc_type, COALESCE(d.current_revision_status,
    #    '-') AS status, COUNT(*) AS documents, MIN(NULLIF(d.current_revision_issued_on, '')) AS
    #    first_issued_on, MAX(NULLIF(...)) AS last_issued_on FROM document d JOIN record r ON
    #    r.id = d.id WHERE NOT r.voided, grouped by scope and the three COALESCE expressions,
    #    ordered by scope, discipline, doc_type, status.
    # 4. mart_document_turnaround: a CTE `issued` of revisions rv joined to their document d (on
    #    d.id = rv.document_id) and its record r (not voided) where the issue date
    #    TRY_CAST(SUBSTR(rv.issued_on, 1, 10) AS DATE) is not NULL (columns scope = rv.scope,
    #    discipline = COALESCE(d.discipline, '-'), document_id, ordinal, issued_date); a CTE `gaps`
    #    with gap_days = DATE_DIFF('day', LAG(issued_date) OVER (PARTITION BY document_id ORDER
    #    BY ordinal), issued_date); then SELECT scope, discipline, COUNT(DISTINCT document_id) AS
    #    documents, COUNT(*) AS issued_revisions, ROUND(AVG(gap_days), 1) AS
    #    avg_days_between_issues, MAX(gap_days) AS longest_gap_days GROUP BY scope, discipline
    #    ORDER BY scope, discipline.
    # 5. mart_document_issues: SELECT rv.scope, SUBSTR(rv.issued_on, 1, 7) AS month, COUNT(*) AS
    #    revisions_issued, COUNT(DISTINCT rv.document_id) AS documents over the same join and
    #    filter as step 4, grouped by scope and month, ordered by scope, month.
    raise NotImplementedError("STEPS: see the comments")
