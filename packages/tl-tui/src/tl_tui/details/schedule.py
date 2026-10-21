"""Details of a schedule and of one of its snapshots, read through ``get_schedule`` and
``get_schedule_snapshot``. A snapshot's key is ``CODE#N``.

The labelled rows show in both modes; the key, the hash and the attempts show only in technical
mode (``technical_rows``, ``Attempts``, ``File hash``).
"""

from __future__ import annotations

from typing import Any

from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, register
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels, actor_label, humanize, type_label
from tl_tui.text import EMPTY, timestamp


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _day(value: str | None) -> str:
    """The day of an ISO date-time; the empty mark for none."""
    return EMPTY if not value else value[:10]


@register("schedule.Schedule")
def schedule_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_schedule(project, str(record["key"]), limit=1)
    rows = [
        DetailRow("Type", type_label(labels, "schedule.Schedule")),
        DetailRow("Code", view.code),
        DetailRow("Title", _or_empty(view.title)),
        DetailRow("Kind", humanize(view.schedule_type)),
    ]
    if view.owner:
        rows.append(DetailRow("Owner", actor_label(labels, view.owner)))
    if view.p6_project:
        rows.append(DetailRow("P6 project", view.p6_project))
    rows += [
        DetailRow("Current snapshot", _or_empty(view.current_snapshot_number)),
        DetailRow("Data date", _day(view.current_data_date)),
        DetailRow("Snapshots", str(view.snapshot_count)),
        DetailRow("Created", timestamp(record.get("created_at"))),
        DetailRow("Updated", timestamp(record.get("updated_at"))),
    ]
    return rows + technical_rows(record)


@register("schedule.ScheduleSnapshot")
def snapshot_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    code, separator, number = str(record["key"]).rpartition("#")
    if not separator:
        raise ValueError("a snapshot key is CODE#N")  # the registry shows the generic rows
    view = client.get_schedule_snapshot(project, code, int(number))
    rows = [
        DetailRow("Type", type_label(labels, "schedule.ScheduleSnapshot")),
        DetailRow("Snapshot", f"{view.number} of {code}"),
        DetailRow("State", view.state),
        DetailRow("Current", "Yes" if view.is_current else "No"),
        DetailRow("Data date", _day(view.data_date)),
    ]
    if view.previous_number is not None:
        rows.append(DetailRow("Compares with", f"snapshot {view.previous_number}"))
    rows += [
        DetailRow("P6 version", _or_empty(view.p6_version)),
        DetailRow("Activities", str(view.activity_count)),
        DetailRow("Relationships", str(view.relationship_count)),
        DetailRow("WBS", str(view.wbs_count)),
        DetailRow("Calendars", str(view.calendar_count)),
        DetailRow("Codes", str(view.code_count)),
        DetailRow("User fields", str(view.udf_count)),
        DetailRow("Errors", str(view.error_count)),
        DetailRow("Warnings", str(view.warning_count)),
        DetailRow("File", _or_empty(view.source_name)),
        DetailRow(
            "Requested by",
            EMPTY if not view.requested_by else actor_label(labels, view.requested_by),
        ),
    ]
    if view.published_at:
        rows.append(DetailRow("Published", _day(view.published_at)))
    if view.last_error:
        rows.append(DetailRow("Last error", view.last_error))
    rows += [
        DetailRow("Attempts", str(view.attempts), technical=True),
        DetailRow("File hash", _or_empty(view.source_sha256), technical=True),
    ]
    return rows + technical_rows(record)
