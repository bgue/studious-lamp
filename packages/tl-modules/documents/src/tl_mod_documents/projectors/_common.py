"""What every documents projector shares.

A module event lands on the stream of a record whose envelope row ``RecordProjector`` made. The
event moves the stream's version, so each projector keeps ``cur_core_record`` in step
(``version``, ``last_seq``, ``updated_at``), the way the pset and workflow projectors do; callers
read that version for optimistic concurrency. The helpers are the engineering module's, imported
rather than copied.
"""

from __future__ import annotations

from tl_mod_engineering.projectors._common import ddl_for, json_text, touch_record

__all__ = ["ddl_for", "json_text", "touch_record"]
