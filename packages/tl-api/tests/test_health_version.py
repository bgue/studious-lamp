"""`/health` answers the server's version from package metadata (P2-REL-T02); nothing else."""

from __future__ import annotations

from importlib.metadata import version

from harness import Harness
from tl_api.client.auth import health


def test_health_answers_status_and_the_package_version(harness: Harness) -> None:
    response = harness.client_for(None).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": version("tl-api")}


def test_health_adds_no_host_or_database_field(harness: Harness) -> None:
    body = harness.client_for(None).get("/health").json()
    assert set(body) == {"status", "version"}
    assert isinstance(body["version"], str)


def test_the_health_client_reads_the_same_body_without_a_token(harness: Harness) -> None:
    body = health("http://testserver", http=harness.client_for(None))
    assert body == {"status": "ok", "version": version("tl-api")}
