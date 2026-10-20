"""The document marts of the lake (P1-I8-T08; brief 28.2 gold, 28.4 uses).

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
    for name in MARTS:
        con.execute(f"DROP TABLE IF EXISTS {table_ref(name)}")
    tables = lake_tables(con)
    if not {DOCUMENT_TABLE, REVISION_TABLE, RECORD_TABLE} <= set(tables):
        return
    counted = con.execute(f"SELECT count(*) FROM {table_ref(DOCUMENT_TABLE)}").fetchone()
    if not counted or counted[0] == 0:
        return

    document = table_ref(DOCUMENT_TABLE)
    revision = table_ref(REVISION_TABLE)
    record = table_ref(RECORD_TABLE)
    con.execute(
        f"""
        CREATE TABLE {table_ref(STATUS_TABLE)} AS
        SELECT
            d.scope,
            COALESCE(d.discipline, '-') AS discipline,
            COALESCE(d.doc_type, '-') AS doc_type,
            COALESCE(d.current_revision_status, '-') AS status,
            COUNT(*) AS documents,
            MIN(NULLIF(d.current_revision_issued_on, '')) AS first_issued_on,
            MAX(NULLIF(d.current_revision_issued_on, '')) AS last_issued_on
        FROM {document} d
        JOIN {record} r ON r.id = d.id
        WHERE NOT r.voided
        GROUP BY
            d.scope,
            COALESCE(d.discipline, '-'),
            COALESCE(d.doc_type, '-'),
            COALESCE(d.current_revision_status, '-')
        ORDER BY 1, 2, 3, 4
        """
    )
    con.execute(
        f"""
        CREATE TABLE {table_ref(TURNAROUND_TABLE)} AS
        WITH {_issued_cte(revision, document, record)},
        gaps AS (
            SELECT
                scope,
                discipline,
                document_id,
                DATE_DIFF(
                    'day',
                    LAG(issued_date) OVER (PARTITION BY document_id ORDER BY ordinal),
                    issued_date
                ) AS gap_days
            FROM issued
        )
        SELECT
            scope,
            discipline,
            COUNT(DISTINCT document_id) AS documents,
            COUNT(*) AS issued_revisions,
            ROUND(AVG(gap_days), 1) AS avg_days_between_issues,
            MAX(gap_days) AS longest_gap_days
        FROM gaps
        GROUP BY scope, discipline
        ORDER BY scope, discipline
        """
    )
    con.execute(
        f"""
        CREATE TABLE {table_ref(ISSUES_TABLE)} AS
        WITH {_issued_cte(revision, document, record)}
        SELECT
            scope,
            SUBSTR(issued_on, 1, 7) AS month,
            COUNT(*) AS revisions_issued,
            COUNT(DISTINCT document_id) AS documents
        FROM issued
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    )


def _issued_cte(revision: str, document: str, record: str) -> str:
    """The ``issued`` CTE: the issued revisions of documents that are not voided.

    A revision whose issue date does not start with a date is left out, so ``issued_date`` is never
    NULL. The turnaround and the issue trend both read it, so they use the same filter.
    """
    return f"""issued AS (
            SELECT
                rv.scope,
                COALESCE(d.discipline, '-') AS discipline,
                rv.document_id,
                rv.ordinal,
                rv.issued_on,
                TRY_CAST(SUBSTR(rv.issued_on, 1, 10) AS DATE) AS issued_date
            FROM {revision} rv
            JOIN {document} d ON d.id = rv.document_id
            JOIN {record} r ON r.id = d.id
            WHERE NOT r.voided
              AND TRY_CAST(SUBSTR(rv.issued_on, 1, 10) AS DATE) IS NOT NULL
        )"""
