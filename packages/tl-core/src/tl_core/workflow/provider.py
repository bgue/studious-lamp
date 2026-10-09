"""Where the engine gets workflow definitions and expected links (brief 8, 7.1).

By default both are read from the schema directory (``TL_SCHEMA_DIR`` or ``schema/fixtures``) on
every call, so an edited file takes effect at once. Tests and embedders install their own with
``use_workflows`` and ``use_expected_links``.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from tl_core.links.expected import ExpectedLinkRegistry, default_expected_links
from tl_core.workflow.loader import WorkflowRegistry, default_workflows

_workflows: WorkflowRegistry | None = None
_expected: ExpectedLinkRegistry | None = None


def get_workflows() -> WorkflowRegistry:
    """The installed registry, else the definitions in the schema directory."""
    return _workflows if _workflows is not None else default_workflows()


def get_expected_links() -> ExpectedLinkRegistry:
    """The installed registry, else the declarations in the schema directory."""
    return _expected if _expected is not None else default_expected_links()


@contextmanager
def use_workflows(registry: WorkflowRegistry) -> Generator[None]:
    global _workflows
    previous, _workflows = _workflows, registry
    try:
        yield
    finally:
        _workflows = previous


@contextmanager
def use_expected_links(registry: ExpectedLinkRegistry) -> Generator[None]:
    global _expected
    previous, _expected = _expected, registry
    try:
        yield
    finally:
        _expected = previous
