# P0-I8-T05 — The feed reads its two settings

Status: ready
Tier: haiku
Labels: core
Depends on: — (the settings service and the reader functions are on the base)
Branch: `p0/i8a-t05-feed-settings`

## Goal
`feed.reactions.enabled` and `feed.signal_tags` stop being constants: `tl_core/feed/config.py` reads them from the settings in force for the scope, inside the caller's transaction, so a company or project value applies to the next post, completion or reaction with no restart. The three callers pass the connection and scope; the old constants and no-argument functions are gone. A provided test file (6 tests) must pass and the existing feed tests must stay green.

## Brief references (pasted)
> **30.5 Representative keys.** `feed.reactions.enabled` = true; `feed.signal_tags` = [safety, hold, decision, urgent, fyi]. **30.3** Changes apply live: no restart.
> **21.3** A post that uses a signal tag (`#safety`) is shown with high importance. Reactions (`ack`, `+1`, `resolved`) can be switched off.

### Specification
The target shape of `feed/config.py` is below (replace the whole file). `value_of(conn, key, project=...)` resolves the effective value for a project (`None`: the company/default); `project_of_scope("project:P1")` is `"P1"` and `project_of_scope("company")` is `None`. The three call sites each already have a connection and a scope:

| File | Now | Becomes |
|---|---|---|
| `services/feed.py`, `parse_post(uow, scope, body)` | `signal_tags=signal_tags(),` | `signal_tags=signal_tags(uow.conn(), scope),` |
| `services/feed_completion.py`, `_hash_completions(conn, scope, prefix, limit)` | `for word in signal_tags()` | `for word in signal_tags(conn, scope)` (and the docstring of `complete_tags` that names `signal_tags()`) |
| `services/feed_actions.py`, `handle_react_to_post(uow, cmd)` | `if not reactions_enabled():` | `if not reactions_enabled(uow.conn(), cmd.scope):` |

Two existing tests change with it:
- `tests/services/test_feed_actions.py::test_reactions_can_be_switched_off` monkeypatched `reactions_enabled`; make it switch reactions off for the project with `settings.set_setting(uow, key="feed.reactions.enabled", layer=P1, value=False, actor="user:a", source="test")` in a unit of work, then expect `ReactionsDisabledError`. Drop the now unused `feed_actions` module import.
- `packages/tl-tui/tests/fakes_feed.py` (a fake that has no database) used the two functions: use `DEFAULT_SIGNAL_TAGS` (from `tl_core.feed.types`) where it called `signal_tags()` and delete its `reactions_enabled()` check and the `ReactionsDisabledError` import if nothing else uses it.

Nothing else may change. In particular `DEFAULT_SIGNAL_TAGS` stays in `feed/types.py` (the tag parser uses it as a default argument).

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`, `tl-api`, `tl-mcp` and `tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I8/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I8/<ticket-id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from the module docstring and from every docstring or comment you fill in.
- Never run `python` with the working directory set to a package directory that holds a file named `types.py` (it shadows the standard library); run everything from the repository root.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. The base is green: if a test outside your Allowed paths fails, report it under *Blocked* with the output.
- `tests/services/*` run on both adapters with `uv run pytest tests/services/test_feed_settings.py --adapters sqlite,postgres` (the parity fixtures); run that once.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/feed/config.py: whole file
"""Feed settings: ``feed.reactions.enabled`` and ``feed.signal_tags`` (brief 30.5; P0-I8 D2).

Every reader goes through these two functions, which read the settings in force for a scope inside
the caller's transaction: a change applies to the next call, with no restart, and the company
value reaches every project that does not set its own.
"""

from __future__ import annotations

from sqlalchemy import Connection

from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of

SIGNAL_TAGS_KEY = "feed.signal_tags"
REACTIONS_KEY = "feed.reactions.enabled"


def signal_tags(conn: Connection, scope: str) -> tuple[str, ...]:
    """The signal tag set for ``scope`` (lower case words without the sigil)."""
    found = value_of(conn, SIGNAL_TAGS_KEY, project=project_of_scope(scope))
    return tuple(str(word).lower() for word in found)


def reactions_enabled(conn: Connection, scope: str) -> bool:
    """Whether ``Feed.Reacted`` is accepted in ``scope``."""
    return bool(value_of(conn, REACTIONS_KEY, project=project_of_scope(scope)))
```
```python
# already implemented (read only)
# tl_core.settings.resolver.value_of(conn, key, *, project=None, user=None, at=None) -> Any     # UnknownSettingError
# tl_core.settings.layers.project_of_scope(scope: str) -> str | None
# tl_core.settings.set_setting(uow, *, key, layer, value, actor, source, reason=None, accept_risk=False, applies_at=None)
# tl_core.feed.types.DEFAULT_SIGNAL_TAGS = ("safety", "hold", "decision", "urgent", "fyi")
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/feed/config.py`
- `packages/tl-core/src/tl_core/services/feed.py` (around `parse_post`)
- `packages/tl-core/src/tl_core/services/feed_completion.py`
- `packages/tl-core/src/tl_core/services/feed_actions.py` (around `handle_react_to_post`)
- `docs/tickets/P0-I8/provided/t05-test_feed_settings.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/feed/config.py` (edit)
- `packages/tl-core/src/tl_core/services/feed.py` (edit: one line)
- `packages/tl-core/src/tl_core/services/feed_completion.py` (edit: one line and a docstring)
- `packages/tl-core/src/tl_core/services/feed_actions.py` (edit: one line)
- `tests/services/test_feed_actions.py` (edit: one test and an import)
- `packages/tl-tui/tests/fakes_feed.py` (edit: the two uses)
- `tests/services/test_feed_settings.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I8/P0-I8-T05.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I8/provided/t05-test_feed_settings.py.txt tests/services/test_feed_settings.py`
2. Replace `feed/config.py`, change the three call sites, then the two tests as the table says.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest tests/services/test_feed_settings.py tests/services/test_feed_actions.py tests/services/test_feed_post.py tests/services/test_feed_completion.py packages/tl-core/tests/test_feed_tags.py -q --adapters sqlite,postgres
uv run pytest packages/tl-tui -q -k "feed or react or composer"
just check
```
Expected: all pass on both adapters; the TUI feed tests pass; `just check` clean.

## Tests to add
None beyond the provided file and the two edited tests.

## Report requirements
Standard report. Say which tests you edited and why (the two above only).

## Escalation triggers
- Stop and report *Blocked* if a caller other than the three above uses `signal_tags()` or `reactions_enabled()` (run `grep -rn "signal_tags()\|reactions_enabled()" packages tests --include=*.py`), or a pasted signature disagrees with the repo.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
