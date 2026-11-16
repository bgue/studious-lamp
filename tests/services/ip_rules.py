"""The rules one module's command rows pass: hooks, words, money, one mark, decided (P2-IP S2)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent)
)  # helpers beside this file (importlib mode)

from test_module_conformance import (
    load_exclusions,
    load_marks,
    load_undecided,
    mark_problems,
    money_problems,
    proposable_rows,
    ratchet_problems,
    word_problems,
)
from tl_core.modules import IN_TREE_SURFACES, hook_failures, load_modules, module_commands


def problems(module: str, names: set[str]) -> list[str]:
    """Problems of the rows of ``module`` (none: clean); the row names must equal ``names``."""
    specs, all_marks, excluded = load_modules(), load_marks(), load_exclusions()
    spec = next(s for s in specs if s.name == module)
    rows = [r for r in module_commands() if r.module == module]
    own = {r.name for r in rows}  # only this module's marks: the file holds every module's
    marks = type(all_marks)(
        {k: v for k, v in all_marks.eligible.items() if k in own},
        {k: v for k, v in all_marks.excluded.items() if k in own},
    )
    found = [] if {r.name for r in rows} == names else [f"rows {sorted(r.name for r in rows)}"]
    found += [text for name, text in hook_failures().items() if name == module]
    if module not in IN_TREE_SURFACES:
        found += [
            f"no {k} hook" for k in ("read_routers", "tools", "cli_groups") if not getattr(spec, k)
        ]
    agent = proposable_rows(specs, agent_only=True)
    found += word_problems(rows, specs) + money_problems(rows, marks)
    found += mark_problems(rows, marks, agent_rows=agent, exclusions=excluded)
    return found + ratchet_problems(
        rows, proposable_rows(specs, agent_only=False) | excluded, load_undecided()
    )
