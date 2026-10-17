"""Validation of rows against a JSON Schema, inside the resource envelope (FANOUT D10; ADR-0014).

A document schema is written by an admin but its patterns and references are applied to cells a
stranger typed, and a pattern such as ``^(a+)+$`` takes a minute on thirty characters. So the
worker, the API and the CLI never call :func:`validate_result` themselves: they call
:func:`validate_isolated`, which runs it in a fresh process under the wall clock and the memory
limit of :mod:`tl_core.derivation.envelope` (the same machinery as the extractors). A breach is
one fixed ``validation_limit`` failure; a schema that cannot be applied at all (a reference loop
that overflows the stack, a reference that does not resolve) is a fixed ``schema_unusable``
failure. Neither carries a trace, a path or the text of the schema. Both are final: a job that
hits one is not retried.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError
from tl_core.derivation.envelope import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIMEOUT_S,
    Breach,
    run_in_envelope,
)
from tl_core.derivation.types import Cell, ExtractionProblem

from tl_mod_documents.derivation.validation import ValidationReport, validate_result
from tl_mod_documents.errors import ValidationFailedError

ENTRY = "tl_mod_documents.derivation.validation_isolated:validate_entry"
TAG_REPORT = b"V"
TAG_UNUSABLE = b"U"
LIMIT_CODE = "validation_limit"
LIMIT_MESSAGE = "the validation used more time or memory than the limit allows"
REFERENCE_ERROR_PACKAGES = ("jsonschema", "referencing", "jsonschema_specifications")
UNUSABLE_CODE = "schema_unusable"
UNUSABLE_MESSAGE = "the document schema cannot be applied to rows (a reference does not resolve)"


def validate_entry(header: Mapping[str, Any], data: bytes) -> tuple[bytes, bytes]:
    """What the child runs: validate the rows and answer with the report as JSON."""
    rows: list[dict[str, Cell]] = json.loads(data)
    problems = [ExtractionProblem.model_validate(p) for p in header["problems"]]
    try:
        report = validate_result(
            header["json_schema"],
            header["columns"],
            rows,
            schema_code=header["schema_code"],
            schema_version=header["schema_version"],
            key_column=header["key_column"],
            problems=problems,
        )
    except RecursionError:
        return TAG_UNUSABLE, b""
    except Exception as exc:  # noqa: BLE001 - jsonschema/referencing errors, named by module only
        if type(exc).__module__.split(".")[0] in REFERENCE_ERROR_PACKAGES:
            return TAG_UNUSABLE, b""
        raise
    return TAG_REPORT, report.model_dump_json().encode()


def validate_isolated(
    json_schema: Mapping[str, Any],
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Cell]],
    *,
    schema_code: str,
    schema_version: str,
    key_column: str | None = None,
    problems: Sequence[ExtractionProblem] = (),
    timeout_s: float = DEFAULT_TIMEOUT_S,
    memory_limit_mb: int | None = DEFAULT_MEMORY_LIMIT_MB,
) -> ValidationReport:
    """The report of :func:`validate_result`, computed in a child process.

    Raises :class:`ValidationFailedError` (fixed text) when the envelope is broken or the schema
    cannot be applied.
    """
    header = {
        "json_schema": dict(json_schema),
        "columns": list(columns),
        "schema_code": schema_code,
        "schema_version": schema_version,
        "key_column": key_column,
        "problems": [p.model_dump() for p in problems],
    }
    data = json.dumps([dict(r) for r in rows], ensure_ascii=False).encode()
    try:
        answer = run_in_envelope(
            ENTRY, header, data, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb
        )
    except Breach:
        raise ValidationFailedError(LIMIT_CODE, LIMIT_MESSAGE) from None
    if answer.tag == TAG_UNUSABLE:
        raise ValidationFailedError(UNUSABLE_CODE, UNUSABLE_MESSAGE)
    try:
        return ValidationReport.model_validate_json(answer.payload)
    except ValidationError:
        raise ValidationFailedError(LIMIT_CODE, LIMIT_MESSAGE) from None
