"""Conformance checks for the P1-I7 thread and dispatch contract (`tl_core.threads.contract`).

WS-B calls ``check_parser_contract(parser)`` from the parser's tests and ``check_preview_shape``
from the planner's tests (``sys.path`` holds this directory, as for ``test_extractor_contract``).
The cases follow the grammar in the module docstring of ``tl_core.threads.contract``.
"""

from __future__ import annotations

from typing import Any, get_args

from tl_core.integration.contract import PlannedCommand
from tl_core.threads.contract import (
    DISPATCH_VERBS,
    MAX_COMMAND_LINE_CHARS,
    MAX_DISPATCH_KEYS,
    MAX_MENTIONS,
    MAX_MESSAGE_CHARS,
    MAX_PLANNED_COMMANDS,
    SIDE_EFFECTING_VERBS,
    THREAD_EVENT_TYPES,
    THREAD_WEBHOOK_EVENT_TYPES,
    DispatchParser,
    DispatchPreview,
    DispatchVerb,
    ParsedDispatch,
    ParseProblem,
)

#: (text, verb, the fields of ``args`` that must equal these values)
PARSE_CASES: tuple[tuple[str, DispatchVerb, dict[str, Any]], ...] = (
    ("/link #ISO-1234 #47-FV-1001", "link", {"keys": ["ISO-1234", "47-FV-1001"], "relation": None}),
    ("/link ISO-1234 as requires", "link", {"keys": ["ISO-1234"], "relation": "requires"}),
    ("/LINK A", "link", {"keys": ["A"]}),
    ("/link A\n  second line note  ", "link", {"keys": ["A"], "note": "second line note"}),
    (
        "/assign @crew:P-07 W021 #W022",
        "assign",
        {"assignees": ["crew:P-07"], "items": ["W021", "W022"]},
    ),
    (
        '/dispatch material-request qty=2 urgent "6 inch CL300"',
        "dispatch",
        {
            "request_type": "material-request",
            "parameters": {"qty": "2"},
            "text": "urgent 6 inch CL300",
        },
    ),
    ('/dispatch crane-lift "a=b"', "dispatch", {"parameters": {}, "text": "a=b"}),
    (
        "/raise rfi #ISO-1234 Clash at grid C4",
        "raise",
        {"record_type": "rfi", "against": ["ISO-1234"], "text": "Clash at grid C4"},
    ),
    ("/raise record", "raise", {"record_type": "record", "against": [], "text": None}),
    (
        "/status Issued waiting on client",
        "status",
        {"target": "Issued", "text": "waiting on client"},
    ),
    ("   /status Closed", "status", {"target": "Closed", "text": None}),
    ("/hold awaiting scaffold", "hold", {"text": "awaiting scaffold"}),
    ("/hold", "hold", {"text": None}),
    ("/release", "release", {"text": None}),
    ("/due 2026-11-02", "due", {"when": "2026-11-02"}),
    ("/due +3d", "due", {"when": "+3d"}),
    ("/due +2w", "due", {"when": "+2w"}),
    (
        "/notify @jsmith @party:acme-nde please review",
        "notify",
        {"who": ["jsmith", "party:acme-nde"], "text": "please review"},
    ),
    (
        "/remind +2h @jsmith check the bevels",
        "remind",
        {"when": "+2h", "who": ["jsmith"], "text": "check the bevels"},
    ),
    ("/remind 2026-11-02T09:00", "remind", {"when": "2026-11-02T09:00", "who": [], "text": None}),
    ("/summarise", "summarise", {}),
    ("/summarize", "summarise", {}),
)

#: (text, problem code)
PROBLEM_CASES: tuple[tuple[str, str], ...] = (
    ("/frobnicate x", "unknown_verb"),
    ("/", "unknown_verb"),
    ("/ link A", "unknown_verb"),
    ("/link", "missing_argument"),
    ("/link as requires", "missing_argument"),
    ("/link A as", "missing_argument"),
    ("/link A as requires extra", "unexpected_arguments"),
    ("/link A @jsmith", "unexpected_arguments"),
    ("/assign W021", "missing_argument"),
    ("/dispatch", "missing_argument"),
    ("/dispatch mr qty=1 qty=2", "bad_parameter"),
    ("/raise", "missing_argument"),
    ("/status", "missing_argument"),
    ("/notify hello", "missing_argument"),
    ("/summarise now", "unexpected_arguments"),
    ("/due tomorrow", "bad_date"),
    ("/due 2026-13-40", "bad_date"),
    ("/due +0d", "bad_date"),
    ("/due +4000d", "bad_date"),
    ("/remind soon", "bad_time"),
    ("/remind +400d", "bad_time"),
    ('/raise rfi "unclosed', "unterminated_quote"),
    ("/link " + " ".join(f"K{i}" for i in range(MAX_DISPATCH_KEYS + 1)), "too_many_keys"),
    ("/notify " + " ".join(f"@p{i}" for i in range(MAX_MENTIONS + 1)), "too_many_mentions"),
    ("/status " + "x" * MAX_COMMAND_LINE_CHARS, "too_long"),
    ("/status Closed\nnote " + "y" * MAX_MESSAGE_CHARS, "too_long"),
    ("/status Closed\x07", "control_character"),
    ("/status Closed\nbad\x00note", "control_character"),
)

#: Plain messages: not a dispatch.
PLAIN_CASES = ("hello", "", "   ", "see /link in the docs", "#ISO-1234 /link A")


def check_parser_contract(parser: DispatchParser) -> None:
    """The parser keeps the grammar: every case, every problem code, no exception."""
    assert isinstance(parser, DispatchParser)
    for text, verb, fields in PARSE_CASES:
        parsed = parser.parse(text)
        assert isinstance(parsed, ParsedDispatch), (text, parsed)
        assert parsed.verb == verb, text
        assert parsed.line == text.strip().splitlines()[0].strip(), text
        dumped = parsed.args.model_dump()
        for name, value in fields.items():
            assert dumped[name] == value, (text, name, dumped[name])
    for text, code in PROBLEM_CASES:
        problem = parser.parse(text)
        assert isinstance(problem, ParseProblem), (text[:60], problem)
        assert problem.code == code, (text[:60], problem.code)
        assert len(problem.message) <= 500
    for text in PLAIN_CASES:
        assert parser.parse(text) is None, text


def check_preview_shape(preview: DispatchPreview) -> None:
    """A preview is consistent: ``can_dispatch`` means every planned command may run."""
    assert len(preview.planned) <= MAX_PLANNED_COMMANDS
    assert preview.side_effecting == (preview.parsed.verb in SIDE_EFFECTING_VERBS)
    runnable = all(p.permitted and p.problem is None for p in preview.planned)
    assert preview.can_dispatch == (runnable and not preview.problems)
    for planned in preview.planned:
        check_planned(planned)
    for link in preview.links:
        assert link.to_record_id == preview.record.id


def check_planned(planned: PlannedCommand) -> None:
    if planned.access is None:
        assert not planned.permitted
    assert "actor" not in planned.command


def test_the_verb_list_and_the_literal_agree() -> None:
    assert DISPATCH_VERBS == get_args(DispatchVerb)
    assert len(DISPATCH_VERBS) == 11
    assert SIDE_EFFECTING_VERBS < set(DISPATCH_VERBS)
    assert {"notify", "summarise"}.isdisjoint(SIDE_EFFECTING_VERBS)


def test_webhooks_carry_posted_and_dispatched_only() -> None:
    assert set(THREAD_WEBHOOK_EVENT_TYPES) < set(THREAD_EVENT_TYPES)
    assert THREAD_WEBHOOK_EVENT_TYPES == ("Thread.MessagePosted", "Thread.Dispatched")


def test_the_arguments_are_chosen_by_verb() -> None:
    parsed = ParsedDispatch.model_validate(
        {
            "line": "/link A as requires",
            "args": {"verb": "link", "keys": ["A"], "relation": "requires"},
        }
    )
    assert parsed.verb == "link"
    assert type(parsed.args).__name__ == "LinkArgs"


def test_the_cases_cover_every_verb() -> None:
    assert {verb for _, verb, _ in PARSE_CASES} == set(DISPATCH_VERBS)
