"""The CI workflow keeps the Postgres parity gate (P0-I5-T11).

These tests read ``.github/workflows/ci.yml`` so that the ``parity`` job, its Postgres 16 service
container and its connection string cannot disappear by accident, and so that the existing
``check-and-test`` job keeps running ``just check`` and ``just test``. Nothing here starts a
server or a container; the tests only parse the YAML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

WORKFLOW: Path = Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"


def _load_workflow() -> dict[str, Any]:
    data: Any = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "ci.yml must parse to a mapping"
    return data


def _job(workflow: dict[str, Any], name: str) -> dict[str, Any]:
    job: Any = workflow["jobs"][name]
    assert isinstance(job, dict), f"job {name!r} must be a mapping"
    return job


def _run_commands(job: dict[str, Any]) -> list[str]:
    steps: list[dict[str, Any]] = job["steps"]
    return [str(step["run"]) for step in steps if "run" in step]


def test_the_parity_job_exists_and_runs_the_parity_recipe() -> None:
    parity = _job(_load_workflow(), "parity")
    assert "just test-parity" in _run_commands(parity)


def test_the_parity_job_has_a_postgres_16_service_and_the_url() -> None:
    parity = _job(_load_workflow(), "parity")

    postgres: dict[str, Any] = parity["services"]["postgres"]
    assert postgres["image"] == "postgres:16"
    assert postgres["env"]["POSTGRES_DB"] == "tl_test"

    url = str(parity["env"]["TL_PG_URL"])
    assert url.startswith("postgresql://")
    assert url.endswith("/tl_test")


def test_the_existing_job_still_checks_and_tests() -> None:
    runs = _run_commands(_job(_load_workflow(), "check-and-test"))
    assert "just check" in runs
    assert "just test" in runs
