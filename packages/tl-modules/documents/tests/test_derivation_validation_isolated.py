"""Validation inside the envelope: a pattern that never ends, a schema that loops (FANOUT D10)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from docworld import World
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_mod_documents.derivation.schemas import MAX_PATTERN_CHARS
from tl_mod_documents.derivation.store import use_files
from tl_mod_documents.derivation.validation_isolated import (
    LIMIT_MESSAGE,
    UNUSABLE_MESSAGE,
    validate_isolated,
)
from tl_mod_documents.errors import InvalidDocumentSchemaError, ValidationFailedError

#: A classic catastrophic pattern: thirty letters and a mismatch take about a minute.
REDOS = {"type": "object", "properties": {"tag": {"type": "string", "pattern": "^(a+)+$"}}}
HOSTILE_ROW: dict[str, str | None] = {"tag": "a" * 32 + "!"}
LOOP = {
    "type": "object",
    "properties": {"tag": {"$ref": "#/$defs/x"}},
    "$defs": {"x": {"$ref": "#/$defs/x"}},
}


def run(schema: dict[str, Any], row: dict[str, str | None], **limits: Any) -> Any:
    return validate_isolated(
        schema, ["tag"], [row], schema_code="s", schema_version="1.0.0", **limits
    )


def test_a_normal_validation_returns_the_report() -> None:
    report = run(REDOS, {"tag": "aaa"}, timeout_s=30)
    assert report.status == "valid" and report.rows_checked == 1


def test_a_catastrophic_pattern_ends_at_the_clock_with_a_fixed_failure() -> None:
    started = time.monotonic()
    with pytest.raises(ValidationFailedError) as caught:
        run(REDOS, HOSTILE_ROW, timeout_s=2)
    assert time.monotonic() - started < 30
    assert caught.value.code == "validation_limit" and str(caught.value) == LIMIT_MESSAGE
    assert "(a+)+" not in str(caught.value) and "/" not in str(caught.value)


def test_a_reference_loop_is_a_fixed_schema_unusable_failure_not_a_crash() -> None:
    with pytest.raises(ValidationFailedError) as caught:
        run(LOOP, {"tag": "x"}, timeout_s=30)
    assert caught.value.code == "schema_unusable" and str(caught.value) == UNUSABLE_MESSAGE


# --- registration --------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def runtime(world: World) -> Iterator[None]:
    with use_extractors(make_extractors()), use_files(world.files):
        yield


def test_a_pattern_over_the_cap_is_refused_at_registration(world: World) -> None:
    long = {"type": "object", "properties": {"tag": {"type": "string", "pattern": "a" * 201}}}
    with pytest.raises(InvalidDocumentSchemaError, match=f"longer than {MAX_PATTERN_CHARS}"):
        world.register_schema(code="long", json_schema=long, mapping=None, target_kind=None)
    keyed = {
        "type": "object",
        "properties": {"tag": {"type": "string"}},
        "patternProperties": {"b" * 201: {"type": "string"}},
    }
    with pytest.raises(InvalidDocumentSchemaError, match="a pattern is longer"):
        world.register_schema(code="keyed", json_schema=keyed, mapping=None, target_kind=None)


def test_a_sample_that_never_finishes_is_refused_at_registration(world: World) -> None:
    started = time.monotonic()
    with pytest.raises(InvalidDocumentSchemaError, match="sample rows could not be checked"):
        world.register_schema(
            code="slow", json_schema=REDOS, mapping=None, target_kind=None, sample=[HOSTILE_ROW]
        )
    assert time.monotonic() - started < 60


def test_a_reference_loop_is_refused_at_registration_even_without_a_sample(world: World) -> None:
    with pytest.raises(InvalidDocumentSchemaError, match="cannot be applied"):
        world.register_schema(code="loop", json_schema=LOOP, mapping=None, target_kind=None)


# --- the job ------------------------------------------------------------------------------------


def test_a_validation_that_never_finishes_fails_the_job_for_good_and_writes_nothing(
    world: World,
) -> None:
    world.register("ISD-001", doc_type="IDX")
    world.create_revision("ISD-001")
    world.attach("ISD-001", "A")
    world.register_schema(code="redos", json_schema=REDOS, mapping=None, target_kind=None)
    derived = world.open_derived("ISD-001", "A", "redos")
    csv = f"tag\n{HOSTILE_ROW['tag']}\n".encode()
    world.upload_content(derived.id, csv)
    job_id = world.start_extraction(derived_id=derived.id).stream_id
    assert [r.outcome for r in world.run_jobs(timeout_s=2)] == ["final"]  # not retried
    job = [j for j in world.jobs() if j.id == job_id][0]
    assert (job.state, job.attempt, job.error_code) == ("failed", 1, "validation_limit")
    assert job.error_message == LIMIT_MESSAGE
    after = world.derived_row(derived.id)
    assert after.state == "Pending" and after.content_rev == 0  # nothing recorded
