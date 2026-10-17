"""The size limits of the schedule module's commands (the P1-I1 review rule).

A command arrives from a person or an agent, so every text has a length before a handler reads it.
The limits of the XER file itself are ``tl_xer.limits``.
"""

from __future__ import annotations

MAX_CODE = 40  # a schedule code
MAX_NAME = 200  # a schedule's name
MAX_OWNER = 200
MAX_P6_PROJECT = 60  # a P6 project short name
MAX_ACTIVITY_ID = 60  # a P6 activity id (the XER reader's bound)
MAX_REASON = 2000
#: Rows of each list in a comparison view before it says it was cut.
DEFAULT_VIEW_LIMIT = 500
MAX_VIEW_LIMIT = 5000
