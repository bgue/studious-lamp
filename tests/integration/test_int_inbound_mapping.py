"""The restricted JSONata runtime (FANOUT D5): the profile check and the enveloped evaluation."""

from __future__ import annotations

import pytest
from tl_core.integration.contract import MAPPING_MAX_COMMANDS, MAPPING_MAX_EXPRESSION_CHARS
from tl_core.integration.inbound.mapping import JsonataRestricted

RT = JsonataRestricted()
OK = '{"command": "CreateRecord", "args": {"title": $.title}}'


def _codes(expression: str) -> set[str]:
    return {p.code for p in RT.check(expression)}


def test_a_plain_mapping_passes_the_check() -> None:
    assert RT.check(OK) == []
    assert RT.check('$.items.{"command": "PostToFeed", "args": {"body": $uppercase(name)}}') == []
    assert RT.check('$exists(a) ? {"command": "CreateRecord", "args": {}} : []') == []


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("$eval('1+1')", "function_not_allowed"),
        ("$now()", "function_not_allowed"),
        ("$millis()", "function_not_allowed"),
        ("$random()", "function_not_allowed"),
        ("$map(a, function($v) {$v})", "function_not_allowed"),
        ("$match(a, /x/)", "function_not_allowed"),
        ("$replace(a, 'x', 'y')", "function_not_allowed"),
        ("function($x){$x}", "not_allowed"),
        ("$x := 1", "not_allowed"),
        ("a.**.b", "not_allowed"),
        ("a.%.b", "not_allowed"),
        ("a ~> | b | {} |", "not_allowed"),
        ("$unknown(a)", "function_not_allowed"),
    ],
)
def test_the_profile_refuses(expression: str, code: str) -> None:
    assert code in _codes(expression)


def test_the_profile_refuses_eval_by_name() -> None:
    assert "function_not_allowed" in _codes("$eval('1')")
    assert "not_allowed" in _codes("function($x){$x}")


def test_syntax_errors_and_size_are_refused_without_echoing_the_expression() -> None:
    problems = RT.check("a.[[")
    assert problems and problems[0].code == "syntax"
    assert "a.[[" not in problems[0].message
    assert _codes("a" * (MAPPING_MAX_EXPRESSION_CHARS + 1)) == {"too_long"}
    assert _codes("   ") == {"empty"}


def test_evaluate_gives_commands() -> None:
    out = RT.evaluate(OK, {"title": "Hello"})
    assert out.status == "ok"
    assert [(c.command, c.args) for c in out.commands] == [("CreateRecord", {"title": "Hello"})]


def test_evaluate_gives_a_list_and_nothing() -> None:
    expression = '$.items.{"command": "PostToFeed", "args": {"body": name}}'
    out = RT.evaluate(expression, {"items": [{"name": "a"}, {"name": "b"}]})
    assert out.status == "ok" and len(out.commands) == 2
    nothing = RT.evaluate("missing", {"x": 1})
    assert nothing.status == "ok" and nothing.commands == []


def test_evaluate_refuses_a_command_automation_may_not_run() -> None:
    out = RT.evaluate('{"command": "DeleteEverything", "args": {}}', {})
    assert out.status == "invalid_output"


def test_evaluate_refuses_a_server_field_in_args() -> None:
    out = RT.evaluate('{"command": "CreateRecord", "args": {"actor": "admin"}}', {})
    assert out.status == "invalid_output"


def test_evaluate_refuses_a_bare_value() -> None:
    assert RT.evaluate("1 + 1", {}).status == "invalid_output"


def test_evaluate_limits_the_command_count() -> None:
    out = RT.evaluate(
        f'[1..{MAPPING_MAX_COMMANDS + 1}].{{"command": "PostToFeed", "args": {{}}}}', {}
    )
    assert out.status == "limit"


def test_evaluate_reports_a_library_error_by_code_only() -> None:
    out = RT.evaluate('{"command": $number("abc")}', {})
    assert out.status == "error"
    assert "abc" not in " ".join(p.message for p in out.problems)


def test_a_refused_expression_is_never_run() -> None:
    out = RT.evaluate("$eval('1')", {})
    assert out.status == "error" and out.problems[0].code == "function_not_allowed"


def test_evaluate_stops_runaway_work() -> None:
    expression = '$sum([1..100000000]) ? {"command": "PostToFeed", "args": {}} : []'
    out = RT.evaluate(expression, {})
    assert out.status in ("limit", "error")
