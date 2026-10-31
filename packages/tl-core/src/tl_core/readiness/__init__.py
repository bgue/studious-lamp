"""Readiness checks (phase 2 contracts section 1): the frozen types, the registry, the harness."""

from __future__ import annotations

from tl_core.readiness.harness import ContractViolation, ContractWorld, check_readiness_contract
from tl_core.readiness.registry import ReadinessLoadError, load_checks
from tl_core.readiness.types import (
    CHECK_MAX_SECONDS,
    EVALUATION_LEASE_S,
    JOB_KIND,
    MAX_CHECKS,
    MAX_DETAIL_CHARS,
    MAX_NAME_CHARS,
    MAX_RESOLVE_VIA,
    READINESS_ENTRY_POINT,
    CheckResult,
    CheckState,
    IwpFacts,
    ReadinessCheck,
    RecordRef,
)

__all__ = [
    "CHECK_MAX_SECONDS",
    "EVALUATION_LEASE_S",
    "JOB_KIND",
    "MAX_CHECKS",
    "MAX_DETAIL_CHARS",
    "MAX_NAME_CHARS",
    "MAX_RESOLVE_VIA",
    "READINESS_ENTRY_POINT",
    "CheckResult",
    "CheckState",
    "ContractViolation",
    "ContractWorld",
    "IwpFacts",
    "ReadinessCheck",
    "ReadinessLoadError",
    "RecordRef",
    "check_readiness_contract",
    "load_checks",
]
