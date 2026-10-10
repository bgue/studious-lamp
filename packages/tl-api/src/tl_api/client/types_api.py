"""Extension types over HTTP: the registry, instances and bodies (P0-I8-T23).

The same shapes the embedded services return: ``TypeSummary`` rows, ``TypeDetail`` with its form,
``CommandResult`` for a create, ``BodyView`` for a body read. Failures raise the embedded
exception classes (``UnknownTypeError``, ``BodyValidationError``, ``BodyHashMismatchError`` ...).
"""

from __future__ import annotations

from typing import Any

from tl_core.extypes.service import BodyStoredOut, BodyView, TypeDetail, TypeSummary
from tl_core.extypes.types import TypeStatus
from tl_core.services.commands import CommandResult

from tl_api.client.base import ApiClientBase, quote


class TypesApi(ApiClientBase):
    def list_types(self, status: TypeStatus | None = None) -> list[TypeSummary]:
        """Registered type versions (``GET /types``); ``status`` is omitted when ``None``.

        Decode with ``self._models(TypeSummary, data)``.
        """
        data = self._get_json("/types", {"status": status})
        return self._models(TypeSummary, data)

    def get_type(self, type_ref: str) -> TypeDetail:
        """One version with its form (``GET /types/{type_ref}``, the ref through ``quote``)."""
        data = self._get_json(f"/types/{quote(type_ref)}")
        return self._model(TypeDetail, data)

    def create_instance(
        self,
        type_name: str,
        *,
        scope: str,
        title: str,
        key: str | None = None,
        description: str | None = None,
        psets: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        numbering: dict[str, str] | None = None,
    ) -> CommandResult:
        """Create an instance (``POST /types/{type_name}/records``).

        The JSON body has ``scope`` and ``title`` always, ``psets`` and ``numbering`` as given
        (empty objects when ``None``), and ``key``, ``description`` and ``body`` only when they are
        not ``None``. Decode with ``CommandResult.model_validate``.
        """
        payload: dict[str, Any] = {
            "scope": scope,
            "title": title,
            "psets": psets if psets is not None else {},
            "numbering": numbering if numbering is not None else {},
        }
        if key is not None:
            payload["key"] = key
        if description is not None:
            payload["description"] = description
        if body is not None:
            payload["body"] = body
        data = self._post_json(f"/types/{quote(type_name)}/records", payload)
        return CommandResult.model_validate(data)

    def get_record_body(self, record_id: str) -> BodyView:
        """The verified body of an object-backed record (``GET /records/{id}/body``)."""
        data = self._get_json(f"/records/{quote(record_id)}/body")
        return self._model(BodyView, data)

    def put_record_body(
        self,
        record_id: str,
        *,
        scope: str,
        body: dict[str, Any],
        expected_version: int | None = None,
    ) -> BodyStoredOut:
        """Store a new body (``PUT /records/{id}/body``).

        The JSON body has ``scope`` and ``body``, and ``expected_version`` when it is not ``None``.
        ``ApiClientBase`` has no ``_put_json``: call ``self._send("PUT", path, json=payload)`` and
        decode ``.json()`` with ``self._model(BodyStoredOut, ...)``.
        """
        payload: dict[str, Any] = {"scope": scope, "body": body}
        if expected_version is not None:
            payload["expected_version"] = expected_version
        response = self._send("PUT", f"/records/{quote(record_id)}/body", json=payload)
        return self._model(BodyStoredOut, response.json())
