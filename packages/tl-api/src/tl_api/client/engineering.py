"""The engineering module's reads over HTTP: tags (P1-I1).

The same ``TagView`` the embedded services return. A missing tag is the module's error
(``TagNotFoundError``), rebuilt from the error body like any other.
"""

from __future__ import annotations

from tl_core.services.commands import CommandResult
from tl_mod_engineering.handlers.tags import CreateTag, RenameTag
from tl_mod_engineering.views import TagView

from tl_api.client.base import ApiClientBase, quote


class EngineeringApi(ApiClientBase):
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
        """A project's tags by number (``GET /projects/{project}/tags``)."""
        params = {
            "class": class_code,
            "status": status,
            "number_status": number_status,
            "include_ended": "true" if include_ended else None,
            "limit": limit,
        }
        data = self._get_json(f"/projects/{quote(project)}/tags", params)
        return self._models(TagView, data)

    def list_code_lists(self, scope: str) -> dict[str, dict[str, str]]:
        """The company's code lists as ``{list name: {code: label}}`` as ``scope`` sees them.

        Reads ``GET /standards?kind=code_list`` for the names, then
        ``GET /code-lists/{name}/values`` (with ``project`` when ``scope`` is ``project:<id>``) for
        each: usable values only.
        """
        project = scope.removeprefix("project:") if scope.startswith("project:") else None
        names = self._get_json("/standards", {"kind": "code_list"})
        found: dict[str, dict[str, str]] = {}
        for item in names:
            name = str(item["code"])
            values = self._get_json(f"/code-lists/{quote(name)}/values", {"project": project})
            found[name] = {str(v["code"]): str(v["label"]) for v in values}
        return found

    def create_tag(self, cmd: CreateTag) -> CommandResult:
        """Create a tag (``POST /commands/CreateTag``); the token's actor is recorded."""
        return self._command("CreateTag", cmd)

    def rename_tag(self, cmd: RenameTag) -> CommandResult:
        """Replace a tag by one with a new number (``POST /commands/RenameTag``)."""
        return self._command("RenameTag", cmd)

    def get_tag(self, project: str, number: str) -> TagView:
        """One tag with its conformance issues (``GET /projects/{project}/tags/{number}``)."""
        data = self._get_json(f"/projects/{quote(project)}/tags/{quote(number)}")
        return self._model(TagView, data)
