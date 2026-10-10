"""``tl new projector <module>.<name>``: a projector for a derived table, with tests and docs."""

from __future__ import annotations

from collections.abc import Sequence

from tl_cli.scaffold.engine import Plan, render
from tl_cli.scaffold.names import ProjectorName


def plan_projector(projector: ProjectorName, events: Sequence[str]) -> Plan:
    """The files of a new projector inside an existing module (the module must exist; the command
    checks that). ``events`` are validated event types; they are sorted and de-duplicated here, and
    the first one (in sorted order) is the event the generated tests append."""
    module = projector.module
    handled = sorted(set(events))
    values = {
        "module": module.name,
        "package": module.package,
        "name": projector.name,
        "cls": projector.cls,
        "table": projector.table,
        "events_literal": ", ".join(f'"{event}"' for event in handled),
        "first_event": handled[0],
        "event_rows": "\n".join(f"| {event} |" for event in handled),
    }
    base = module.directory
    plan = Plan()
    plan.add(
        f"{base}/src/{module.package}/projectors/{projector.name}.py",
        render("projector/projector.py.tmpl", **values),
    )
    plan.add(
        f"{base}/tests/test_projector_{projector.name}.py",
        render("projector/test.py.tmpl", **values),
    )
    plan.add(
        f"docs/modules/{module.name}/projector-{projector.name}.md",
        render("projector/spec.md.tmpl", **values),
    )
    plan.next_steps = [
        f"register {projector.cls} in the registry your application builds",
        "just check && just test",
    ]
    return plan
