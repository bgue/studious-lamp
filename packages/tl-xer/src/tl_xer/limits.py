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
#: Rows of one table, and cells (rows x columns) over all tables. 6 million cells is a schedule of
#: tens of thousands of activities with their relationships, codes and resources.
MAX_ROWS_PER_TABLE: Final = 400_000
MAX_CELLS: Final = 6_000_000
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
#: The parent reads at most this much from the child: the typed snapshot (about 100 MB at its
#: bounds) and the compressed raw tables (at most the source size plus the JSON framing).
MAX_ANSWER_BYTES: Final = 200 * 1024 * 1024
#: What the parser may inflate the stored raw bundle to when it is read back (the lake loader).
MAX_BUNDLE_BYTES: Final = 400 * 1024 * 1024
