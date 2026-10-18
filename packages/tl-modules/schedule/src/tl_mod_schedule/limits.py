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

#: Links that may point at one activity reference (active, stale or suggested). Anyone signed in
#: can link, so the work of flagging them when the activity leaves is bounded by this.
MAX_LINKS_PER_ACTIVITY = 100
#: Snapshots of one schedule that wait for a build (Uploaded or Processing). Anyone signed in can
#: open one, so the queue of unbuilt snapshots is bounded; building or voiding one frees a place.
MAX_OPEN_SNAPSHOTS = 20
#: Activity references of one schedule: at most the activities a snapshot can hold.
MAX_REFS_PER_SCHEDULE = 60_000
#: Operations (a reference changed, a link flagged or restored) one run of the flagging job does;
#: more is left to the next run, which the run queues.
FLAG_BATCH = 500
#: A data date more than this many days after today cannot be published: it would sit above every
#: later snapshot and freeze the series (publication needs a later data date than the current).
MAX_DATA_DATE_AHEAD_DAYS = 31

#: How long a worker holds a claim. A build reads the file in the envelope (at most the envelope's
#: wall clock, 60 s by default) and then writes the typed rows in one transaction (measured in
#: ADR-0015: well under a minute at the limits); the claim must outlast both with a wide margin, or
#: a second worker would take the job over while the first is still writing.
BUILD_LEASE_S = 600.0
