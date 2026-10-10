"""``tl new module <name>``: a module package, its schema header and its spec placeholder."""

from __future__ import annotations

from tl_cli.scaffold.engine import Plan, render
from tl_cli.scaffold.names import ModuleName


def plan_module(module: ModuleName) -> Plan:
    """The files of a new module. The package is ``packages/tl-mod-<name>`` (a uv workspace
    member through ``packages/*``); the schema is ``schema/modules/<name>/module.yaml``."""
    values = {
        "name": module.name,
        "package": module.package,
        "distribution": module.distribution,
    }
    base = module.directory
    src = f"{base}/src/{module.package}"
    plan = Plan()
    plan.add(f"{base}/pyproject.toml", render("module/pyproject.toml.tmpl", **values))
    plan.add(f"{base}/README.md", render("module/package_readme.md.tmpl", **values))
    plan.add(f"{base}/AGENTS.md", render("module/package_agents.md.tmpl", **values))
    plan.add(f"{src}/__init__.py", render("module/package_init.py.tmpl", **values))
    plan.add(f"{src}/py.typed", "")
    plan.add(f"{src}/handlers/__init__.py", render("module/handlers_init.py.tmpl", **values))
    plan.add(f"{src}/projectors/__init__.py", render("module/projectors_init.py.tmpl", **values))
    plan.add(f"{base}/tests/test_module.py", render("module/test_module.py.tmpl", **values))
    plan.add(
        f"schema/modules/{module.name}/module.yaml", render("module/module.yaml.tmpl", **values)
    )
    plan.add(
        f"docs/modules/{module.name}/README.md", render("module/docs_readme.md.tmpl", **values)
    )
    plan.next_steps = [
        "uv lock && uv sync --all-packages   # the new package joins the workspace; commit uv.lock",
        f"edit docs/modules/{module.name}/README.md and schema/modules/{module.name}/module.yaml",
        f"uv run tl new record-type {module.name}.<Class>",
        "just check && just test",
    ]
    return plan
