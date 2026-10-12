"""The engineering module's reads over HTTP: tags (P1-I1).

The same ``TagView`` the embedded services return. A missing tag is the module's error
(``TagNotFoundError``), rebuilt from the error body like any other.
"""

from __future__ import annotations

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

    def get_tag(self, project: str, number: str) -> TagView:
        """One tag with its conformance issues (``GET /projects/{project}/tags/{number}``)."""
        data = self._get_json(f"/projects/{quote(project)}/tags/{quote(number)}")
        return self._model(TagView, data)
