# P1-I2-T11a — Base reports: register, revision history, overdue reviews, transmittal log, stale pins

Status: ready
Tier: haiku
Labels: core
Depends on: S3 and S4 on `p1/i2`; no other ticket
Branch: `p1/i2-t11a-doc-reports`

## Goal
The five base reports of document control are functions of `tl_mod_documents.reports` that read the flat views and return frozen lines. `packages/tl-modules/documents/src/tl_mod_documents/reports.py` has the line dataclasses and the five signatures final; the five bodies raise `NotImplementedError`. You implement the bodies. One provided test file (8 test functions) must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 15 (base reports).** Document Control: Document register; revision history; overdue reviews; transmittal log; documents by status/discipline; derived-document validation status; stale pinned revisions.
>
> **Brief 7.3.** Link health report and data-health dashboard: stale pins, broken external refs, missing expected links, unreviewed suggestions. A pinned link goes stale when a newer revision is issued.

### Specification
- Read through the generated views `v_documents_document`, `v_documents_revision`, `v_documents_review_cycle`, `v_documents_transmittal` (the constants `DOCUMENT_VIEW`, `REVISION_VIEW`, `REVIEW_CYCLE_VIEW`, `TRANSMITTAL_VIEW` in `names.py`) and the tables `cur_documents_reviewer`, `cur_documents_transmittal_item`. A view row has the envelope columns (`key`, `title`, `status`, `voided`, ...) and the typed columns. Never hand-write a join to `cur_core_record`.
- `status` is the workflow state and is NULL for a record that never moved: it means the workflow's first state, `Draft`. Always write `COALESCE(x.status, 'Draft')` in SQL and `row.status or "Draft"` in Python.
- Booleans: SQLite returns 0/1 and Postgres returns booleans; `NOT c.voided` works in both. `NULL` sorts first on SQLite and last on Postgres, so every `ORDER BY` here is on columns that are never NULL.
- Dates are ISO text (`YYYY-MM-DD`), compared as text. "Today" is the `on` argument, so a report is repeatable.
- Use SQLAlchemy `text()` with named parameters (`conn.execute(text(sql), params)`); never format a user value into SQL. Fixed names (view and table constants) may be formatted in.
- Nothing here writes. A void document or transmittal is left out of the lists.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/documents/src/tl_mod_documents/reports.py` (the stub you complete):
```python
"""Base reports of document control (brief 15; P1-I2-T11): the register, a document's history,
overdue reviews, the transmittal log and the stale pinned revisions.

Every function takes a connection (``uow.conn()`` inside a unit of work, a read transaction
elsewhere) and a project scope, reads the flat views (``v_documents_<class>``) and the review and
transmittal tables, and returns frozen lines in a stable order. Nothing here writes. A void record
is left out. Dates are ISO text (``YYYY-MM-DD``); "today" is a parameter (``on``) so a report is
repeatable.

STUB (P1-I2-T11a): the bodies of the five report functions raise NotImplementedError; the line
dataclasses and every signature are final. Each body has a STEPS comment. Implement them, then
delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Connection, text

from tl_mod_documents import registry
from tl_mod_documents.errors import DocumentNotFoundError
from tl_mod_documents.names import (
    DOCUMENT_VIEW,
    REVIEW_CYCLE_VIEW,
    REVIEWER_TABLE,
    REVISION_VIEW,
    TRANSMITTAL_ITEM_TABLE,
    TRANSMITTAL_VIEW,
)
from tl_mod_documents.resolver import links_to_documents


@dataclass(frozen=True)
class RegisterLine:
    """One document in the register."""

    number: str
    title: str
    doc_type: str | None
    discipline: str | None
    state: str
    current_code: str | None
    current_status: str | None
    current_class: str | None
    current_issued_on: str | None
    revisions: int  # revisions that are not void
    open_code: str | None  # the revision being prepared or reviewed
    stale_links: int  # links to the document whose status is stale


@dataclass(frozen=True)
class HistoryLine:
    """One revision in a document's history."""

    code: str
    ordinal: int
    state: str
    issue_status: str | None
    status_class: str | None
    issued_on: str | None
    is_current: bool
    purpose: str | None
    change_note: str | None
    renditions: int  # current renditions
    transmittals: list[str]  # numbers of the transmittals that carry it
    review_outcome: str | None  # outcome of the latest closed review cycle
    superseded_by: str | None  # the code of the revision that replaced it


@dataclass(frozen=True)
class OverdueLine:
    """A reviewer who should have answered by now."""

    document_number: str
    revision_code: str
    cycle_key: str
    reviewer: str
    due_date: str
    days_overdue: int


@dataclass(frozen=True)
class TransmittalLine:
    """One transmittal in the log."""

    number: str
    title: str
    direction: str
    purpose: str
    state: str
    issued_on: str | None
    due_date: str | None
    response_code: str | None
    responded_on: str | None
    items: int
    overdue: bool  # issued, not answered, and the due date has passed


@dataclass(frozen=True)
class StalePinLine:
    """A link pinned to a revision that a newer issue has replaced (or flagged stale)."""

    document_number: str
    document_title: str
    pinned_code: str | None
    current_code: str | None
    current_status: str | None
    linked_key: str | None
    linked_type: str
    link_id: str
    link_status: str
    newer_codes: list[str]


def document_register(
    conn: Connection,
    scope: str,
    *,
    doc_type: str | None = None,
    discipline: str | None = None,
    state: str | None = None,
    limit: int = 1000,
) -> list[RegisterLine]:
    """The documents of a project by number, with the facts a register shows.

    ``state`` is a document state (Registered, In Review, Issued, Superseded). A void document is
    left out.
    """
    # STEPS
    # 1. Build one SELECT over the view v_documents_document (DOCUMENT_VIEW, alias d) with the
    #    columns key, title, doc_type, discipline, status, current_revision_code,
    #    current_revision_status, current_revision_class, current_revision_issued_on and three
    #    scalar subqueries: `revisions` = COUNT of the document's rows in REVISION_VIEW (alias
    #    r, r.document_id = d.id) whose COALESCE(r.status, 'Draft') <> 'Void'; `open_code` =
    #    MAX(r.code) over its revisions whose COALESCE(r.status, 'Draft') IN ('Draft', 'In
    #    Review'); `stale_links` = COUNT of rows of cur_links l with l.to_id = d.id AND l.status
    #    = 'stale'.
    # 2. WHERE d.scope = :scope AND COALESCE(d.status, 'Draft') <> 'Void'; add `AND d.doc_type =
    #    :doc_type`, `AND d.discipline = :discipline`, `AND COALESCE(d.status, 'Draft') =
    #    :state` only for the arguments that are not None. ORDER BY d.key LIMIT :limit. Run it
    #    with conn.execute(text(sql), params).
    # 3. One RegisterLine per row: number = row.key, state = row.status or "Draft", the revision
    #    counts as int(...), the rest as read.
    raise NotImplementedError


def revision_history(conn: Connection, scope: str, number: str) -> list[HistoryLine]:
    """Every revision of a document, oldest first, with its renditions, transmittals and review.

    Raises ``DocumentNotFoundError``. Void revisions are kept in the history and shown as Void.
    """
    # STEPS
    # 1. doc = registry.find_document(conn, scope, number); None: raise
    #    DocumentNotFoundError(f"no document {number!r} in scope {scope!r}").
    # 2. revisions = registry.revisions_of(conn, doc.id) (void ones included, oldest first);
    #    codes = {r.id: r.code for r in revisions}.
    # 3. For each revision: closed = [c for c in registry.review_cycles_of(conn, rev.id) if
    #    c.state == "closed"]; one HistoryLine with state = "Void" if rev.voided else rev.state;
    #    renditions = len(registry.renditions_of(conn, rev.id, current_only=True)); transmittals
    #    = [t.number for t in registry.transmittals_of_revision(conn, rev.id)]; review_outcome =
    #    closed[-1].outcome if closed else None; superseded_by = codes.get(rev.superseded_by) if
    #    rev.superseded_by else None; the other fields come straight from the row (code,
    #    ordinal, issue_status, status_class, issued_on, is_current, purpose, change_note).
    raise NotImplementedError


def overdue_reviews(conn: Connection, scope: str, *, on: date | None = None) -> list[OverdueLine]:
    """Reviewers of open review cycles who have not answered and whose due date has passed.

    A reviewer with no date of their own is due on the cycle's date; one with no date at all is
    never overdue. Ordered by due date, then cycle key, then reviewer.
    """
    # STEPS
    # 1. day = (on or date.today()).isoformat().
    # 2. SELECT c.key AS cycle_key, r.reviewer, r.due_date, rv.document_number, rv.code FROM
    #    REVIEWER_TABLE r JOIN REVIEW_CYCLE_VIEW c ON c.id = r.review_cycle_id JOIN
    #    REVISION_VIEW rv ON rv.id = r.revision_id WHERE r.scope = :scope AND c.state = 'open'
    #    AND r.outcome IS NULL AND r.due_date IS NOT NULL AND r.due_date < :day AND NOT c.voided
    #    ORDER BY r.due_date, c.key, r.reviewer.
    # 3. One OverdueLine per row; days_overdue = (date.fromisoformat(day) -
    #    date.fromisoformat(row.due_date)).days.
    raise NotImplementedError


def transmittal_log(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    direction: str | None = None,
    on: date | None = None,
) -> list[TransmittalLine]:
    """The transmittals of a project by number. A void one is left out unless ``state`` is Void.

    ``overdue`` is true for an issued transmittal that has no answer and whose due date has passed.
    """
    # STEPS
    # 1. day = (on or date.today()).isoformat().
    # 2. SELECT t.key, t.title, t.direction, t.purpose, t.status, t.issued_on, t.due_date,
    #    t.response_code, t.responded_on and `items` = (SELECT COUNT(*) FROM
    #    TRANSMITTAL_ITEM_TABLE i WHERE i.transmittal_id = t.id) FROM TRANSMITTAL_VIEW t WHERE
    #    t.scope = :scope. With `state` add AND COALESCE(t.status, 'Draft') = :state; without it
    #    AND COALESCE(t.status, 'Draft') <> 'Void'. With `direction` add AND t.direction =
    #    :direction. ORDER BY t.key.
    # 3. One TransmittalLine per row: state = row.status or "Draft"; overdue is True exactly
    #    when that state is "Issued" and row.due_date is not None and row.due_date < day.
    raise NotImplementedError


def stale_pins(conn: Connection, scope: str) -> list[StalePinLine]:
    """Links pinned to a revision that has been replaced, or flagged stale, by document and record.

    Ordered by document number, then the key of the record that links.
    """
    # STEPS
    # 1. For each link in links_to_documents(conn, scope, only_stale=True) (from
    #    tl_mod_documents.resolver) read current = registry.get_document(conn,
    #    link.document_id).
    # 2. One StalePinLine per link: document_number, document_title, pinned_code = link.pin,
    #    current_code = link.resolution.current_code, current_status = the document's
    #    current_revision_status (None when current is None), linked_key = link.from_key,
    #    linked_type = link.from_type, link_id, link_status = link.link_status, newer_codes =
    #    list(link.resolution.newer_codes). Keep the order the function returns.
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/registry.py` (reads, already written; the parts you use):
```python
@dataclass(frozen=True)
class DocumentRow:
    id: str
    scope: str
    number: str
    title: str
    description: str | None
    state: str  # the document workflow state
    voided: bool
    version: int
    conformance: str
    doc_type: str | None
    discipline: str | None
    originator: str | None
    confidentiality: str | None
    revision_scheme: str
    pattern_code: str | None
    current_revision_id: str | None
    current_revision_code: str | None
    current_revision_status: str | None
    current_revision_class: str | None
    current_revision_issued_on: str | None
    superseded_by: str | None
    created_at: str
    updated_at: str

    @property
    def closed(self) -> bool:
        """True once the document is void or superseded: it takes no more changes."""
        return self.voided or self.state in ("Void", "Superseded")

@dataclass(frozen=True)
class RevisionRow:
    id: str
    scope: str
    document_id: str
    document_number: str
    key: str
    title: str
    code: str
    ordinal: int
    state: str  # Draft, In Review, Issued, Superseded, Void
    voided: bool
    version: int
    previous_revision_id: str | None
    purpose: str | None
    change_note: str | None
    revision_date: str | None
    intended_status: str | None
    issue_status: str | None
    status_class: str | None
    issued_on: str | None
    is_current: bool
    superseded_by: str | None

    @property
    def issued(self) -> bool:
        return self.issued_on is not None

    @property
    def open(self) -> bool:
        return self.state in OPEN_STATES and not self.voided

@dataclass(frozen=True)
class RenditionRow:
    id: str
    scope: str
    revision_id: str
    document_id: str
    key: str
    kind: str
    file_id: str
    filename: str
    content_type: str
    size: int
    sha256: str
    page_count: int | None
    is_current: bool
    superseded_by: str | None
    version: int
    created_at: str

@dataclass(frozen=True)
class TransmittalRow:
    id: str
    scope: str
    number: str
    title: str
    description: str | None
    state: str  # Draft, Issued, Acknowledged, Closed, Void
    voided: bool
    version: int
    direction: str
    purpose: str
    due_date: str | None
    issued_on: str | None
    response_code: str | None
    response_note: str | None
    responded_on: str | None
    recipients: list[dict[str, Any]]
    item_count: int
    created_at: str

@dataclass(frozen=True)
class ReviewCycleRow:
    id: str
    scope: str
    key: str
    title: str
    voided: bool
    version: int
    revision_id: str
    document_id: str
    round: int
    state: str  # open | closed
    due_date: str | None
    outcome: str | None
    opened_on: str | None
    closed_on: str | None

def find_document(conn: Connection, scope: str, number: str) -> DocumentRow | None: ...

def get_document(conn: Connection, document_id: str) -> DocumentRow | None: ...

def revisions_of(
    conn: Connection, document_id: str, *, include_void: bool = True
) -> list[RevisionRow]: ...

def renditions_of(
    conn: Connection, revision_id: str, *, current_only: bool = False, kind: str | None = None
) -> list[RenditionRow]: ...

def transmittals_of_revision(conn: Connection, revision_id: str) -> list[TransmittalRow]: ...

def review_cycles_of(conn: Connection, revision_id: str) -> list[ReviewCycleRow]: ...
```

`packages/tl-modules/documents/src/tl_mod_documents/resolver.py` (already written; the parts you use):
```python
@dataclass(frozen=True)
class PinResolution:
    """What a pin on a document means now."""

    document_id: str
    document_number: str
    pin: str | None  # as stored on the link; None floats
    state: PinState
    resolved_code: (
        str | None
    )  # the revision the link means: the pin, or the current one when floating
    resolved_revision_id: str | None
    current_code: str | None  # the document's current revision
    newer_codes: list[str] = field(default_factory=lambda: [])  # issued revisions after the pin

    @property
    def stale(self) -> bool:
        return self.state == "stale"

@dataclass(frozen=True)
class PinnedLink:
    """One link that points to a document, with what its pin means now."""

    link_id: str
    from_id: str
    from_key: str | None
    from_type: str
    from_title: str
    document_id: str
    document_number: str
    document_title: str
    relation: str
    link_status: str  # active | stale (the link lifecycle)
    pin: str | None
    resolution: PinResolution

def links_to_documents(
    conn: Connection,
    scope: str,
    *,
    document_id: str | None = None,
    only_stale: bool = False,
    limit: int = 1000,
) -> list[PinnedLink]: ...
```

The view columns (generated; `v_documents_revision` shown, the others have the same envelope columns first):
```text
CREATE VIEW IF NOT EXISTS v_documents_revision AS
SELECT
  r.id AS id,
  r.key AS key,
  r.type AS record_type,
  r.scope AS scope,
  r.title AS title,
  r.description AS description,
  r.status AS status,
  r.voided AS voided,
  r.version AS version,
  r.conformance AS conformance,
  r.psets_json AS psets_json,
  r.created_at AS created_at,
  r.updated_at AS updated_at,
  t.document_id AS document_id,
  t.document_number AS document_number,
  t.code AS code,
  t.ordinal AS ordinal,
  t.previous_revision_id AS previous_revision_id,
  t.purpose AS purpose,
  t.change_note AS change_note,
  t.revision_date AS revision_date,
  t.intended_status AS intended_status,
  t.issue_status AS issue_status,
  t.status_class AS status_class,
  t.issued_on AS issued_on,
  t.is_current AS is_current,
  t.superseded_by AS superseded_by
FROM cur_documents_revision AS t
JOIN cur_core_record AS r ON r.id = t.id;
```

## Context (read these, nothing else)
- `packages/tl-modules/documents/src/tl_mod_documents/reports.py` (the file you edit)
- `packages/tl-modules/engineering/src/tl_mod_engineering/reports.py` (a finished report module of the same kind; read it for style)
- `packages/tl-modules/documents/src/tl_mod_documents/registry.py`
- `packages/tl-modules/documents/src/tl_mod_documents/resolver.py`
- `docs/tickets/P1-I2/provided/t11a-test_reports.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-modules`, `tl-cli`, `tl-api`; strict for `tl_core`, `tl_schema`, `tl_adapters`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run the scoped command in *Acceptance*, never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- The test builds transmittals and review cycles with raw events (`forge`), so it does not need the commands that make them (other tickets of this batch).

## Allowed paths
- `packages/tl-modules/documents/src/tl_mod_documents/reports.py` (edit)
- `packages/tl-modules/documents/tests/test_reports.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T11a.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t11a-test_reports.py.txt` to `packages/tl-modules/documents/tests/test_reports.py`.
3. Implement the five functions by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/documents/tests/test_reports.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-modules/documents/tests/test_reports.py -q --adapters sqlite,postgres
uv run pytest packages/tl-modules/documents -q
```
Expected: `just check` clean; 8 passed on SQLite; 16 passed with both adapters; the whole `documents` package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of the parity run.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in another file of `tl_mod_documents` or a view.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
