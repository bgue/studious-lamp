"""Names the legacy module shares: record type, event types, table, slots, workflow states."""

from __future__ import annotations

from typing import Final

LOAD_RUN: Final = "legacy.LoadRun"
RECORD_TYPES: Final = frozenset({LOAD_RUN})

RUN_TABLE: Final = "cur_legacy_load_run"
RUN_VIEW: Final = "v_legacy_load_run"

RUN_OPENED: Final = "LoadRun.Opened"
RUN_EXTRACTED: Final = "LoadRun.Extracted"
RUN_PROFILED: Final = "LoadRun.Profiled"
RUN_BRONZED: Final = "LoadRun.Bronzed"
RUN_PLANNED: Final = "LoadRun.Planned"
RUN_LOADED: Final = "LoadRun.Loaded"
RUN_RECONCILED: Final = "LoadRun.Reconciled"
RUN_COMPENSATED: Final = "LoadRun.Compensated"
RUN_FAILED: Final = "LoadRun.Failed"
RUN_VOIDED: Final = "LoadRun.Voided"

SLOT_SOURCE: Final = "source"
SLOT_EXTRACTED: Final = "extracted"
SLOT_PROFILE: Final = "profile"
SLOT_REPORT: Final = "report"

OPENED: Final = "Opened"
EXTRACTED: Final = "Extracted"
PROFILED: Final = "Profiled"
PLANNED: Final = "Planned"
LOADED: Final = "Loaded"
RECONCILED: Final = "Reconciled"
COMPENSATED: Final = "Compensated"
VOID: Final = "Void"

#: Correlation ids of a load and of its compensation carry this prefix; a client cannot set one
#: (``tl_core.services.reserved``).
CORRELATION_PREFIX: Final = "load:"
SOURCE_PREFIX: Final = "legacy:"
ACTOR: Final = "svc:legacy"
