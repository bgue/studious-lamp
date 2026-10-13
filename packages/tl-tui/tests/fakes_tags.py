"""In-memory engineering tags for `FakeClient` (P1-I1): the tag reads of `ClientInterface`.

It holds `TagView`s by project and answers `list_tags` and `get_tag` the way the embedded client
does: tags by number, the ended ones (`Superseded`, `Deleted`) only on request, the filters of the
real call, and `TagNotFoundError` for an unknown number. `test_embedded_tags.py` runs the same
reads on this fake and on the embedded client and compares the answers. A listing carries no
issues; `get_tag` carries the ones the test gave the tag.
"""

from __future__ import annotations

from typing import Any

from tl_mod_engineering.errors import TagNotFoundError
from tl_mod_engineering.views import TagView
from tl_schema.forms import ConformanceIssue

ENDED = ("Superseded", "Deleted")


class FakeTagSupport:
    """Mixin for `FakeClient`: call `_init_tags()` from its `__init__`."""

    def _init_tags(self) -> None:
        self._tags: dict[str, dict[str, TagView]] = {}  # project -> number -> view

    def add_tag(
        self,
        project: str,
        number: str,
        *,
        class_code: str | None = "ControlValve",
        status: str | None = None,
        conformance: str = "ok",
        number_status: str = "ok",
        issues: list[ConformanceIssue] | None = None,
        violations: list[dict[str, Any]] | None = None,
        title: str | None = None,
        psets: dict[str, Any] | None = None,
    ) -> TagView:
        """Add a tag; the segments are read from a number of the form ``area-mnemonic-seq``."""
        parts = number.split("-")
        well_formed = len(parts) == 3 and parts[2].isdigit()
        view = TagView(
            id=f"TAG{len(self._tags.get(project, {})) + 1:04d}",
            number=number,
            title=title or number,
            class_code=class_code,
            status=status,
            area=parts[0] if well_formed else None,
            mnemonic=parts[1] if well_formed else None,
            sequence=int(parts[2]) if well_formed else None,
            segments={"area": parts[0], "mnemonic": parts[1], "seq": parts[2]}
            if well_formed
            else {},
            pattern_code="tag" if well_formed else None,
            number_status=number_status,
            violations=violations or [],
            origin="created",
            conformance=conformance,
            version=2,
            psets=psets or {},
            issues=issues or [],
        )
        self._tags.setdefault(project, {})[number] = view
        return view

    def list_tags(
        self,
        project: str,
        *,
        class_code: str | None = None,
        status: str | None = None,
        number_status: str | None = None,
        include_ended: bool = False,
        limit: int = 1000,
    ) -> list[TagView]:
        self.calls.append("list_tags")  # type: ignore[attr-defined]
        found = [
            view.model_copy(update={"issues": []})
            for number, view in sorted(self._tags.get(project, {}).items())
            if (class_code is None or view.class_code == class_code)
            and (status is None or view.status == status)
            and (number_status is None or view.number_status == number_status)
            and (include_ended or status is not None or view.status not in ENDED)
        ]
        return found[:limit]

    def get_tag(self, project: str, number: str) -> TagView:
        self.calls.append("get_tag")  # type: ignore[attr-defined]
        view = self._tags.get(project, {}).get(number)
        if view is None:
            raise TagNotFoundError(f"no tag {number!r} in scope 'project:{project}'")
        return view
