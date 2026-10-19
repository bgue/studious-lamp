"""The error table (O4): one status and one stable code per ServiceError, both directions."""

from __future__ import annotations

import importlib
import pkgutil

import pytest
import tl_core
from pydantic import ValidationError
from tl_api.errors import (
    ERROR_TABLE,
    EXTRACTOR_UNAVAILABLE,
    HTTP_ERRORS,
    ApiError,
    ApiValidationError,
    body_for,
    exception_for,
    spec_for,
)
from tl_core.derivation.registry import ExtractorLoadError
from tl_core.ledger import ConcurrencyError
from tl_core.query import QuerySyntaxError
from tl_core.services import errors as svc
from tl_core.workflow.engine import GuardResult
from tl_mod_cost import errors as cost


def all_service_errors() -> set[type[Exception]]:
    """Every ServiceError subclass defined anywhere in tl_core (modules imported first)."""
    for module in pkgutil.walk_packages(tl_core.__path__, "tl_core."):
        importlib.import_module(module.name)
    found: set[type[Exception]] = set()
    stack: list[type[Exception]] = [svc.ServiceError]
    while stack:
        for sub in stack.pop().__subclasses__():
            found.add(sub)
            stack.append(sub)
    return found


def test_every_service_error_has_its_own_row() -> None:
    mapped = {spec.exc for spec in ERROR_TABLE}
    assert all_service_errors() - mapped == set(), "map the new error in tl_api/errors.py"


def test_codes_are_unique_and_do_not_collide_with_http_codes() -> None:
    codes = [spec.error for spec in ERROR_TABLE]
    assert len(codes) == len(set(codes))
    assert not set(codes) & set(HTTP_ERRORS)


def test_statuses_follow_the_decision() -> None:
    by_class = {spec.exc: spec.status for spec in ERROR_TABLE}
    assert by_class[ConcurrencyError] == 409
    assert by_class[svc.GuardFailedError] == 409
    assert by_class[svc.RecordNotFoundError] == 404
    assert by_class[svc.PsetValidationError] == 422
    assert by_class[QuerySyntaxError] == 400


def build(exc_class: type[Exception]) -> Exception:
    if exc_class is QuerySyntaxError:
        return QuerySyntaxError("bad", 7)
    if exc_class is svc.GuardFailedError:
        return svc.GuardFailedError("blocked", [GuardResult(kind="k", passed=False, message="m")])
    if exc_class is svc.PsetValidationError:
        return svc.PsetValidationError("invalid", ["a is wrong"])
    if exc_class is cost.CostFileError:
        return cost.CostFileError("bad_number", "something specific", 7)
    if exc_class is cost.CostImportRefusedError:
        return cost.CostImportRefusedError("something specific", ["row 3: wrong"])
    return exc_class("something specific")


@pytest.mark.parametrize("spec", ERROR_TABLE, ids=lambda s: s.exc.__name__)
def test_every_row_round_trips_to_its_exception_class(spec) -> None:  # type: ignore[no-untyped-def]
    original = build(spec.exc)
    mapped = body_for(original)
    assert mapped is not None
    status, body = mapped
    assert status == spec.status
    assert body.error == spec.error
    rebuilt = exception_for(status, body.model_dump(mode="json", exclude_none=True))
    assert type(rebuilt) is spec.exc
    if spec.exc is ExtractorLoadError:  # the text is fixed: the original's detail never leaves
        assert str(rebuilt) == EXTRACTOR_UNAVAILABLE
        return
    assert str(rebuilt) == str(original)


def test_a_subclass_uses_the_row_of_its_nearest_mapped_ancestor() -> None:
    class Odd(svc.NumberingError): ...

    spec = spec_for(Odd("x"))
    assert spec is not None and spec.exc is svc.NumberingError


def test_extras_survive_the_trip() -> None:
    status, body = body_for(QuerySyntaxError("unexpected )", 12)) or (0, None)
    assert body is not None and body.position == 12
    rebuilt = exception_for(status, body.model_dump(mode="json", exclude_none=True))
    assert isinstance(rebuilt, QuerySyntaxError) and rebuilt.position == 12

    guard = svc.GuardFailedError("no", [GuardResult(kind="pset", passed=False, message="m")])
    _, gbody = body_for(guard) or (0, None)
    assert gbody is not None
    again = exception_for(409, gbody.model_dump(mode="json", exclude_none=True))
    assert isinstance(again, svc.GuardFailedError)
    assert isinstance(again.results[0], GuardResult) and again.results[0].passed is False


def test_a_pydantic_validation_error_is_a_422_with_issues() -> None:
    from tl_core.services.commands import CreateRecord

    with pytest.raises(ValidationError) as caught:
        CreateRecord(actor="a", source="s", scope="nope", record_type="x", title="t")
    mapped = body_for(caught.value)
    assert mapped is not None
    status, body = mapped
    assert status == 422
    assert body.error == "validation_error" and body.issues
    rebuilt = exception_for(422, body.model_dump(mode="json", exclude_none=True))
    assert isinstance(rebuilt, ApiValidationError)


def test_unknown_codes_become_api_error() -> None:
    err = exception_for(418, {"error": "teapot", "message": "short and stout"})
    assert isinstance(err, ApiError) and err.status == 418 and err.error == "teapot"


def test_an_unmapped_exception_has_no_body() -> None:
    assert body_for(RuntimeError("boom")) is None


def test_a_failing_extractor_load_is_a_fixed_503_that_names_nothing() -> None:
    status, body = body_for(ExtractorLoadError("extractor 'x' cannot be loaded: /home/u/secret.py"))  # type: ignore[misc]
    assert status == 503 and body.error == "extractor_unavailable"
    assert body.message == EXTRACTOR_UNAVAILABLE and "secret" not in body.message


def test_a_cost_file_error_keeps_its_code_and_row_and_an_import_refusal_its_issues() -> None:
    status, body = body_for(cost.CostFileError("bad_number", "row 7: no", 7)) or (0, None)
    assert status == 422 and body is not None and body.issues == [{"code": "bad_number", "row": 7}]
    rebuilt = exception_for(status, body.model_dump(mode="json", exclude_none=True))
    assert isinstance(rebuilt, cost.CostFileError)
    assert (rebuilt.code, rebuilt.row, str(rebuilt)) == ("bad_number", 7, "row 7: no")
    whole = exception_for(422, {"error": "cost_file", "message": "the file is empty"})
    assert isinstance(whole, cost.CostFileError) and (whole.code, whole.row) == ("cost_file", None)
    refused = body_for(cost.CostImportRefusedError("refused", ["a", "b"]))
    assert refused is not None and refused[1].issues == ["a", "b"]
