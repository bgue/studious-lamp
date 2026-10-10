"""``tl new record-type <module>.<Class>``: schema stub, handler, tests and a spec page."""

from __future__ import annotations

from tl_cli.scaffold.engine import Plan, render
from tl_cli.scaffold.names import RecordTypeName


def plan_record_type(record_type: RecordTypeName) -> Plan:
    """The files of a new record type inside an existing module. The schema is
    ``schema/modules/<module>/<snake>.yaml``; the handler and tests live in the module."""
    module = record_type.module
    snake = record_type.snake
    values = {
        "module": module.name,
        "package": module.package,
        "cls": record_type.cls,
        "snake": snake,
        "qualified": record_type.qualified,
    }
    base = module.directory
    src = f"{base}/src/{module.package}"
    plan = Plan()
    plan.add(
        f"schema/modules/{module.name}/{snake}.yaml",
        render("record_type/schema.yaml.tmpl", **values),
    )
    plan.add(f"{src}/handlers/{snake}.py", render("record_type/handler.py.tmpl", **values))
    plan.add(f"{base}/tests/test_{snake}.py", render("record_type/test.py.tmpl", **values))
    plan.add(
        f"docs/modules/{module.name}/{snake}.md",
        render("record_type/spec.md.tmpl", **values),
    )
    plan.next_steps = [
        f"add `- {snake}` to the imports of schema/modules/{module.name}/module.yaml",
        f"replace the example field in schema/modules/{module.name}/{snake}.yaml",
        "just check && just test",
    ]
    return plan
