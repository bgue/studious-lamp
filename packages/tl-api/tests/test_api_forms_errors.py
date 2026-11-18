"""The forms and permits refusals at the API door (V3-FX).

Every error class of ``tl_mod_forms.errors`` and ``tl_mod_permits.errors`` has its own row in
``tl_api.errors``. A refused ``SubmitForm`` answers 422 ``forms_answers`` with the module's text and
no answer value in the body, and the HTTP client re-raises the same class. The ledger is the forms
module's own world helper (``forms_world.py``, loaded by path as ``test_api_scaffold_commands.py``
loads ``scaffold_world.py``), never a projection write.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from harness import Harness
from tl_api.client.base import ApiClientBase
from tl_api.errors import ERROR_TABLE
from tl_core.auth import sessions
from tl_mod_forms import errors as forms
from tl_mod_permits import errors as permits

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
SCOPE = "project:P123"
SECRET = "zq-secret-42"  # an answer value: it must never reach the body


def load_world() -> ModuleType:
    """The forms module's ``forms_world`` helper, loaded by path (it is not an installed module)."""
    name = "forms_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "forms" / "tests" / "forms_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def classes_of(module: ModuleType) -> set[type[Exception]]:
    return {
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if obj.__module__ == module.__name__ and issubclass(obj, Exception)
    }


@dataclass
class Seeded:
    harness: Harness
    template: str  # a published company template, the refused submission's


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Seeded]:
    h = Harness.build(tmp_path_factory.mktemp("api-forms-errors"))
    try:
        world = load_world().World(h.target or h.db)
        world.people()
        yield Seeded(h, world.template())
    finally:
        h.close()


def test_every_forms_and_permits_error_class_has_its_own_row() -> None:
    classes = classes_of(forms) | classes_of(permits)
    assert {c.__name__ for c in classes_of(forms)} == {
        "FormsError",
        "FormsScopeError",
        "FormTemplateError",
        "FormRuleError",
        "FormStateError",
        "FormAnswersError",
        "StaleVersionError",
    }
    mapped = {spec.exc for spec in ERROR_TABLE}
    assert classes - mapped == set(), "map the forms or permits error in tl_api/errors.py"


def test_a_refused_submit_form_is_422_forms_answers_with_text_and_no_answer(
    seeded: Seeded,
) -> None:
    harness = seeded.harness
    token = sessions.sign_in(harness.backend, username="uma", password=PASSWORD)[1]
    client = harness.client_for(None)
    client.headers.update({"Authorization": f"Bearer {token}"})
    body: dict[str, Any] = {
        "scope": SCOPE,
        "template_id": seeded.template,
        "answers": [
            {"q": "topic", "value": "Ladders", "note": None},
            {"q": "count", "value": SECRET, "note": None},
        ],
    }
    response = client.post("/commands/SubmitForm", json=body)
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["error"] == "forms_answers"
    assert payload["message"].startswith("the answers have problems")
    assert payload["issues"] and all(isinstance(i, str) for i in payload["issues"])
    assert SECRET not in response.text

    rebuilt = ApiClientBase.error_from(response)
    assert type(rebuilt) is forms.FormAnswersError
    assert str(rebuilt) == payload["message"]
