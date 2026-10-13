"""The rules a document's revisions must always obey, as a check (brief 9 M1).

The handlers keep them; this function reads the tables and reports every breach, so a test, a data
health report or an operator after a restore can ask "is this document sound?" without trusting the
handlers. An empty list means sound.

1. At most one revision per status class is current.
2. A current revision is issued and not void; a revision that is not issued is not current.
3. The document row names the current revision with the highest ordinal (none when no revision is
   current), and copies its code, status, class and issue date.
4. Revision ordinals run 1, 2, 3 ... without a gap, and codes are unique.
5. At most one revision is being prepared or reviewed (Draft or In Review, not void).
6. At most one native, pdf or signed rendition per revision is current (markups are additive: every
   markup stays current).
"""

from __future__ import annotations

from sqlalchemy import Connection

from tl_mod_documents import registry


def check_document(conn: Connection, document_id: str) -> list[str]:
    """Every breach of the rules above for one document; ``[]`` when it is sound."""
    doc = registry.get_document(conn, document_id)
    if doc is None:
        return [f"no document {document_id}"]
    problems: list[str] = []
    revisions = registry.revisions_of(conn, document_id)
    classes: dict[str, list[str]] = {}
    for rev in revisions:
        if rev.is_current:
            if not rev.issued or rev.voided:
                problems.append(f"revision {rev.code} is current but not issued")
            classes.setdefault(rev.status_class or "?", []).append(rev.code)
        elif rev.state == "Issued":
            problems.append(f"revision {rev.code} is issued but not current or superseded")
    for status_class, codes in sorted(classes.items()):
        if len(codes) > 1:
            problems.append(f"class {status_class} has {len(codes)} current revisions: {codes}")
    currents = [r for r in revisions if r.is_current]
    top = max(currents, key=lambda r: r.ordinal) if currents else None
    if (top.id if top else None) != doc.current_revision_id:
        problems.append(
            f"document names {doc.current_revision_code} as current, "
            f"the revisions say {top.code if top else None}"
        )
    elif top is not None and (
        doc.current_revision_code != top.code
        or doc.current_revision_status != top.issue_status
        or doc.current_revision_class != top.status_class
        or doc.current_revision_issued_on != top.issued_on
    ):
        problems.append("the document's current revision columns differ from the revision")
    if [r.ordinal for r in revisions] != list(range(1, len(revisions) + 1)):
        problems.append(f"ordinals {[r.ordinal for r in revisions]} are not 1..{len(revisions)}")
    if len({r.code for r in revisions}) != len(revisions):
        problems.append("a revision code is used twice")
    open_ones = [r.code for r in revisions if r.open]
    if len(open_ones) > 1:
        problems.append(f"more than one open revision: {open_ones}")
    for rev in revisions:
        kinds: dict[str, int] = {}
        for rendition in registry.renditions_of(conn, rev.id, current_only=True):
            kinds[rendition.kind] = kinds.get(rendition.kind, 0) + 1
        for kind, count in sorted(kinds.items()):
            if count > 1 and kind != "markup":
                problems.append(f"revision {rev.code} has {count} current {kind} renditions")
    return problems
