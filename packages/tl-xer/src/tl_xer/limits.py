"""Every bound of the XER reader in one place (P1-I4-T03; the rules of ADR-0015 section 2).

An XER file is a stranger's text. Anything over a bound is **refused**, never cut: a file that
lost its last 400 000 rows to a limit would be a wrong schedule that looks right. The limits are
chosen so that a very large real schedule (tens of thousands of activities) is read and a hostile
file ends in a fixed, named refusal long before it costs the worker anything; the resource
envelope (``tl_core.derivation.envelope``: a process of its own, address space, CPU and wall clock)
is the backstop, not the plan.
"""

from __future__ import annotations

from typing import Final

#: Bytes of one file. The same bound as an extractor's source (``tl_core.derivation``).
MAX_BYTES: Final = 50 * 1024 * 1024
#: ``%T`` sections. A P6 export holds about 100.
MAX_TABLES: Final = 300
#: Fields of one table (``%F``). P6's widest table (TASK) has about 120.
MAX_COLUMNS: Final = 200
#: Rows of one table, rows over all tables, and the weight of all rows. A row weighs its columns,
#: and at least ``MIN_ROW_WEIGHT``: a row costs a tuple and a few objects whatever its width, so
#: millions of one-column rows must not pass as a few cells. The totals are what a schedule of tens
#: of thousands of activities with their relationships, codes, user fields and resources needs,
#: with room; the worst legal file is measured against the envelope in ADR-0015 section 2.
MAX_ROWS_PER_TABLE: Final = 400_000
MAX_ROWS_TOTAL: Final = 1_200_000
MIN_ROW_WEIGHT: Final = 16
MAX_CELLS: Final = 20_000_000
#: Characters of one field. P6 notebook memos are the longest text in a schedule.
MAX_FIELD_CHARS: Final = 32_000
#: The ``ERMHDR`` line.
MAX_HEADER_FIELDS: Final = 20
MAX_HEADER_FIELD_CHARS: Final = 255
#: Table and column names.
MAX_NAME_CHARS: Final = 64

# --- what the typed snapshot may hold (ADR-0015 section 3) ---------------------------------------
MAX_ACTIVITIES: Final = 60_000
MAX_RELATIONSHIPS: Final = 200_000
MAX_WBS: Final = 60_000
MAX_CALENDARS: Final = 2_000
MAX_CODES: Final = 300_000
MAX_UDFS: Final = 300_000
#: Depth of a WBS tree; a deeper one (or a loop) is refused.
MAX_WBS_DEPTH: Final = 100
#: An activity id, a WBS short name, a code: what P6 allows (40 characters) with room.
MAX_ID_CHARS: Final = 60
MAX_TEXT_CHARS: Final = 500

# --- the report ----------------------------------------------------------------------------------
#: Problems kept in a report; the count of all of them is kept too (``problem_count``).
MAX_PROBLEMS: Final = 500
MAX_MESSAGE_CHARS: Final = 300
#: Project names listed in a multi-project message.
MAX_PROJECTS_LISTED: Final = 20

# --- the envelope (ADR-0014: the same limits the extractors run under) ---------------------------
#: The text of the typed rows (every string of every cell, in bytes) may be at most this many times
#: the size of the source, plus a margin. A code or user field is copied into every row that links
#: it, so a few megabytes of links can name hundreds of megabytes of text; past the bound the file
#: is invalid with a report, and the worker never holds the copies.
TYPED_TEXT_FACTOR: Final = 2
TYPED_TEXT_EXTRA: Final = 16 * 1024 * 1024
#: The most typed text of any file (the bound for a file at ``MAX_BYTES``).
MAX_TYPED_TEXT: Final = TYPED_TEXT_FACTOR * MAX_BYTES + TYPED_TEXT_EXTRA
#: The typed snapshot as canonical JSON: its text plus the quotes, separators and numbers around it.
MAX_TYPED_JSON: Final = MAX_TYPED_TEXT + 48 * 1024 * 1024
#: The parent reads at most this much from the child: the typed snapshot, the compressed raw tables
#: (about the source size; gzip adds under 1 per cent) and the frames around them.
MAX_ANSWER_BYTES: Final = MAX_TYPED_JSON + MAX_BYTES + 8 * 1024 * 1024


def answer_bound(source_size: int) -> int:
    """The most the parent reads from the child for a file of ``source_size`` bytes.

    The typed text is at most ``TYPED_TEXT_FACTOR`` times the source plus a margin, the structure
    around it (quotes, separators, numbers of at most 60 000 + 200 000 + 300 000 + 300 000 rows)
    about 48 MiB at its largest, and the compressed raw tables about the source. A small file is
    therefore allowed a small answer; no file more than ``MAX_ANSWER_BYTES``.
    """
    typed = TYPED_TEXT_FACTOR * source_size + TYPED_TEXT_EXTRA + 48 * 1024 * 1024
    return min(MAX_ANSWER_BYTES, typed + source_size + 8 * 1024 * 1024)


#: What the parser may inflate the stored raw bundle to when it is read back (the lake loader).
MAX_BUNDLE_BYTES: Final = 400 * 1024 * 1024
#: The longest line of the raw bundle: a batch of rows, or one row (200 fields of 32 000 characters,
#: as UTF-8) with its JSON quotes. Longer is a damaged bundle, never held.
MAX_BUNDLE_LINE_BYTES: Final = 32 * 1024 * 1024
#: Rows per line of the raw bundle (a line is also cut at about one megabyte of text).
BUNDLE_BATCH_ROWS: Final = 2000
BUNDLE_BATCH_CHARS: Final = 1024 * 1024
#: The first and last year of a date in a schedule. P6 stores a date for 1 January 1900 for "none"
#: in some exports; a schedule outside these years is a typing mistake, and one far in the future
#: would freeze the series of snapshots.
MIN_YEAR: Final = 1990
MAX_YEAR: Final = 2100
