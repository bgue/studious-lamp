"""The revision scheme engine and the scheme file (T05): codes, order, assignment, bad files."""

from __future__ import annotations

import pytest
from tl_mod_documents.errors import (
    InvalidIssueStatusError,
    InvalidRevisionCodeError,
    UnknownSchemeError,
)
from tl_mod_documents.schemes import (
    SchemeFile,
    load_scheme_file,
    parse_scheme_file,
    scheme_by_code,
    scheme_code_for,
    status_class,
)


@pytest.fixture
def config() -> SchemeFile:
    return load_scheme_file()


def walk(config: SchemeFile, code: str, count: int) -> list[str]:
    scheme = scheme_by_code(config, code)
    out: list[str] = []
    previous: str | None = None
    for _ in range(count):
        previous = scheme.next_code(previous)
        out.append(previous)
    return out


def test_the_alpha_scheme_counts_like_a_column_and_skips_i_and_o(config: SchemeFile) -> None:
    codes = walk(config, "alpha", 30)
    assert codes[:9] == ["A", "B", "C", "D", "E", "F", "G", "H", "J"]
    assert "I" not in codes and "O" not in codes
    assert codes[23] == "Z"  # 24 usable letters
    assert codes[24:27] == ["AA", "AB", "AC"]


def test_the_numeric_scheme_starts_at_zero(config: SchemeFile) -> None:
    assert walk(config, "numeric", 4) == ["0", "1", "2", "3"]
    assert scheme_by_code(config, "numeric").next_code("9") == "10"


def test_the_staged_scheme_counts_within_a_stage_and_moves_on_request(config: SchemeFile) -> None:
    scheme = scheme_by_code(config, "staged")
    assert walk(config, "staged", 3) == ["P1", "P2", "P3"]
    assert scheme.next_code("P3", stage="C") == "C1"
    assert scheme.next_code("C1") == "C2"
    assert scheme.next_code(None, stage="C") == "C1"


def test_a_stage_cannot_go_back_or_repeat(config: SchemeFile) -> None:
    scheme = scheme_by_code(config, "staged")
    with pytest.raises(InvalidRevisionCodeError, match="not after"):
        scheme.next_code("C2", stage="P")
    with pytest.raises(InvalidRevisionCodeError, match="not after"):
        scheme.next_code("P2", stage="P")
    with pytest.raises(InvalidRevisionCodeError, match="not a stage"):
        scheme.next_code("P2", stage="Q")
    with pytest.raises(InvalidRevisionCodeError, match="no stages"):
        scheme_by_code(config, "alpha").next_code("A", stage="C")


@pytest.mark.parametrize(
    ("scheme", "code", "valid"),
    [
        ("alpha", "A", True),
        ("alpha", "AB", True),
        ("alpha", "I", False),  # skipped letter
        ("alpha", "a", False),
        ("alpha", "A1", False),
        ("alpha", "", False),
        ("numeric", "0", True),
        ("numeric", "12", True),
        ("numeric", "01", False),
        ("numeric", "-1", False),
        ("numeric", "A", False),
        ("numeric", "١", False),  # an Arabic-Indic digit is not a digit here
        ("staged", "P1", True),
        ("staged", "C12", True),
        ("staged", "P0", False),  # stages start at 1
        ("staged", "P01", False),
        ("staged", "X1", False),
        ("staged", "P", False),
    ],
)
def test_which_codes_belong_to_a_scheme(
    config: SchemeFile, scheme: str, code: str, valid: bool
) -> None:
    assert (scheme_by_code(config, scheme).position(code) is not None) is valid


def test_codes_only_go_forward(config: SchemeFile) -> None:
    scheme = scheme_by_code(config, "alpha")
    scheme.validate_after("B", "A")
    scheme.validate_after("A", None)
    with pytest.raises(InvalidRevisionCodeError, match="does not come after"):
        scheme.validate_after("A", "B")
    with pytest.raises(InvalidRevisionCodeError, match="does not come after"):
        scheme.validate_after("B", "B")
    with pytest.raises(InvalidRevisionCodeError, match="not a code of the alpha scheme"):
        scheme.validate_after("1", "A")
    staged = scheme_by_code(config, "staged")
    staged.validate_after("C1", "P9")  # a later stage is after any number of the earlier
    with pytest.raises(InvalidRevisionCodeError):
        staged.validate_after("P10", "C1")


def test_next_code_of_a_foreign_code_is_refused(config: SchemeFile) -> None:
    with pytest.raises(InvalidRevisionCodeError, match="not a code of the numeric scheme"):
        scheme_by_code(config, "numeric").next_code("A")


def test_the_scheme_of_a_document_comes_from_project_then_type_then_default(
    config: SchemeFile,
) -> None:
    assert scheme_code_for(config, "project:P9", None) == "alpha"
    assert scheme_code_for(config, "project:P9", "ISO") == "alpha"
    assert scheme_code_for(config, "project:P9", "SPC") == "numeric"  # the company type rule
    assert scheme_code_for(config, "project:P9", "DS") == "staged"
    # P123 adds type rules of its own: they win for those types, the company rules stay otherwise
    assert scheme_code_for(config, "project:P123", "ITR") == "numeric"
    assert scheme_code_for(config, "project:P123", "DRW") == "staged"
    assert scheme_code_for(config, "project:P123", "SPC") == "numeric"
    assert scheme_code_for(config, "project:P123", "ISO") == "alpha"
    # P200 sets a default for the whole project, which wins over the company type rules
    assert scheme_code_for(config, "project:P200", "ISO") == "numeric"
    assert scheme_code_for(config, "project:P200", "DS") == "numeric"


def test_an_unknown_scheme_is_an_error_naming_the_choices(config: SchemeFile) -> None:
    with pytest.raises(UnknownSchemeError, match="no revision scheme 'roman'.*alpha"):
        scheme_by_code(config, "roman")


def test_the_status_class_of_an_issue_status(config: SchemeFile) -> None:
    assert status_class(config, "IFR") == "review"
    assert status_class(config, "IFC") == "construction"
    assert status_class(config, "ASB") == "record"
    with pytest.raises(InvalidIssueStatusError, match="not an issue status"):
        status_class(config, "XYZ")


GOOD = """
default_scheme: alpha
schemes:
  alpha: {label: Letters, kind: alpha}
statuses:
  IFR: {label: Issued for review, class: review}
classes: [review]
"""


def test_a_minimal_file_loads() -> None:
    parsed = parse_scheme_file(GOOD)
    assert scheme_by_code(parsed, "alpha").first_code() == "A"


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (
            ("default_scheme: alpha", "default_scheme: roman"),
            "default_scheme 'roman' is not a scheme",
        ),
        (("class: review}", "class: nope}"), "class 'nope' is not in classes"),
        (("kind: alpha}", "kind: staged}"), "a staged scheme needs stages"),
        (("kind: alpha}", "kind: alpha, skip: [i]}"), "skip holds capital letters"),
        (("kind: alpha}", "kind: alpha, start: Q, skip: [Q]}"), "not a usable letter"),
        (("classes: [review]", "classes: [review, review]"), "lists a class twice"),
        (("kind: alpha}", "kind: mystery}"), "kind"),
        (("statuses:", "bogus: 1\nstatuses:"), "bogus"),
    ],
)
def test_a_file_that_is_unsound_is_refused_with_the_reason(
    edit: tuple[str, str], message: str
) -> None:
    with pytest.raises(UnknownSchemeError, match=message):
        parse_scheme_file(GOOD.replace(*edit))


def test_a_file_that_is_not_a_mapping_or_not_yaml_is_refused() -> None:
    with pytest.raises(UnknownSchemeError):
        parse_scheme_file("- just\n- a list\n")
    with pytest.raises(UnknownSchemeError, match="invalid YAML"):
        parse_scheme_file("a: [unclosed")


def test_hostile_yaml_is_an_error_not_a_crash() -> None:
    with pytest.raises(UnknownSchemeError):
        parse_scheme_file("a: " + "[" * 50_000)
    with pytest.raises(UnknownSchemeError):
        parse_scheme_file(GOOD.replace("kind: alpha}", "kind: alpha, start: " + "9" * 5000 + "}"))


def test_an_assignment_to_a_missing_scheme_is_refused() -> None:
    text = GOOD + "assignment:\n  by_document_type: {ISO: roman}\n"
    with pytest.raises(UnknownSchemeError, match="by_document_type.ISO: 'roman' is not a scheme"):
        parse_scheme_file(text)


def test_the_committed_file_is_sound(config: SchemeFile) -> None:
    assert config.problems() == []
    assert set(config.schemes) == {"alpha", "numeric", "staged"}
    assert {s.status_class for s in config.statuses.values()} == set(config.classes)


def test_an_unreadable_scheme_file_is_reported_by_name_and_never_by_path(tmp_path: object) -> None:
    from pathlib import Path

    from tl_mod_documents.schemes import load_scheme_file as load

    missing = Path(str(tmp_path)) / "private-dir" / "revision-schemes.yaml"
    with pytest.raises(UnknownSchemeError) as raised:
        load(missing)
    assert "revision-schemes.yaml" in str(raised.value)
    assert "private-dir" not in str(raised.value) and str(tmp_path) not in str(raised.value)
