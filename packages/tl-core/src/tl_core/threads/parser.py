"""The dispatch command-line parser (brief 21.5; FANOUT D10; grammar in ``contract.py``).

Pure and total: no database, no clock, never raises. :class:`CommandLineParser` implements
:class:`~tl_core.threads.contract.DispatchParser`. It turns the first line of a message that starts
with ``/`` into a :class:`~tl_core.threads.contract.ParsedDispatch`, or says why it cannot
(:class:`~tl_core.threads.contract.ParseProblem`). Resolving mentions and keys, checking dates
against the clock and building commands are the planner's work.

Tokens: white space separates them. ``"double quoted"`` text, opened at the start of a token and
closed by the next quote, is one token and always a word (no escapes). ``@x`` is a mention, ``#x``
a record key, anything else a word. A mention or key left over where a verb takes free text stays
in the text with its sigil, so ``/notify @a see #K-1`` has the text ``see #K-1``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import ValidationError

from tl_core.threads.contract import (
    DUE_MAX_DAYS,
    MAX_COMMAND_LINE_CHARS,
    MAX_DISPATCH_KEYS,
    MAX_MENTIONS,
    MAX_MESSAGE_CHARS,
    MAX_PARAMETERS,
    REMIND_MAX_DAYS,
    AssignArgs,
    DispatchArgs,
    DispatchArguments,
    DispatchVerb,
    DueArgs,
    HoldArgs,
    LinkArgs,
    NotifyArgs,
    ParsedDispatch,
    ParseProblem,
    RaiseArgs,
    ReleaseArgs,
    RemindArgs,
    StatusArgs,
    SummariseArgs,
)

Kind = Literal["word", "quoted", "mention", "key"]

_VERBS: dict[str, DispatchVerb] = {
    "assign": "assign",
    "dispatch": "dispatch",
    "raise": "raise",
    "link": "link",
    "status": "status",
    "hold": "hold",
    "release": "release",
    "due": "due",
    "notify": "notify",
    "remind": "remind",
    "summarise": "summarise",
    "summarize": "summarise",
}
_PARAMETER = re.compile(r"([a-z][a-z0-9_]*)=(.*)", re.DOTALL)
_COUNT_DATE = re.compile(r"\+(\d{1,6})([dw])")
_COUNT_TIME = re.compile(r"\+(\d{1,7})([mhdw])")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ISO_MINUTE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_MINUTES = {"m": 1, "h": 60, "d": 24 * 60, "w": 7 * 24 * 60}


@dataclass(frozen=True)
class _Token:
    kind: Kind
    value: str  # without the sigil for a mention or key; without the quotes for a quoted word
    column: int  # 0-based offset of the token (its sigil or opening quote) in the line

    @property
    def is_word(self) -> bool:
        return self.kind in ("word", "quoted")

    @property
    def as_text(self) -> str:
        """The token as it reads in free text: a mention or key keeps its sigil."""
        if self.kind == "mention":
            return "@" + self.value
        if self.kind == "key":
            return "#" + self.value
        return self.value


class _Refusal(Exception):
    """Internal: a command line the grammar refuses (becomes a :class:`ParseProblem`)."""

    def __init__(self, code: str, message: str, column: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.column = column


def _tokenize(text: str, offset: int) -> list[_Token]:
    """Split ``text`` (the line after the verb; ``offset`` is where it starts in the line)."""
    tokens: list[_Token] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == '"':
            end = text.find('"', i + 1)
            if end < 0:
                raise _Refusal(
                    "unterminated_quote", "a quote is opened and never closed", offset + i
                )
            tokens.append(_Token("quoted", text[i + 1 : end], offset + i))
            i = end + 1
        else:
            j = i
            while j < n and not text[j].isspace():
                j += 1
            raw = text[i:j]
            if raw[0] == "@" and len(raw) > 1:
                tokens.append(_Token("mention", raw[1:], offset + i))
            elif raw[0] == "#" and len(raw) > 1:
                tokens.append(_Token("key", raw[1:], offset + i))
            else:
                tokens.append(_Token("word", raw, offset + i))
            i = j
    return tokens


def _text_of(tokens: list[_Token]) -> str | None:
    """The tokens joined by one space, or ``None`` when there are none."""
    joined = " ".join(token.as_text for token in tokens)
    return joined if joined else None


def _check_keys(count: int) -> None:
    if count > MAX_DISPATCH_KEYS:
        raise _Refusal("too_many_keys", f"at most {MAX_DISPATCH_KEYS} keys in one command")


def _check_mentions(count: int) -> None:
    if count > MAX_MENTIONS:
        raise _Refusal("too_many_mentions", f"at most {MAX_MENTIONS} mentions in one command")


def _first_word(verb: str, tokens: list[_Token], what: str) -> _Token:
    if not tokens or not tokens[0].is_word:
        raise _Refusal(
            "missing_argument", f"/{verb} needs {what}", tokens[0].column if tokens else None
        )
    return tokens[0]


def _valid_date(value: str) -> bool:
    if _ISO_DATE.fullmatch(value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_due(value: str, column: int) -> None:
    found = _COUNT_DATE.fullmatch(value)
    if found is not None:
        count = int(found.group(1))
        days = count * (7 if found.group(2) == "w" else 1)
        if count >= 1 and days <= DUE_MAX_DAYS:
            return
    elif _valid_date(value):
        return
    raise _Refusal(
        "bad_date",
        f"a due date is YYYY-MM-DD, +<n>d or +<n>w, at most {DUE_MAX_DAYS} days ahead",
        column,
    )


def _check_remind(value: str, column: int) -> None:
    found = _COUNT_TIME.fullmatch(value)
    if found is not None:
        count = int(found.group(1))
        if count >= 1 and count * _MINUTES[found.group(2)] <= REMIND_MAX_DAYS * 24 * 60:
            return
    elif _valid_date(value):
        return
    elif _ISO_MINUTE.fullmatch(value) is not None:
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M")
        except ValueError:
            pass
        else:
            return
    raise _Refusal(
        "bad_time",
        "a reminder time is +<n>m, +<n>h, +<n>d, +<n>w, YYYY-MM-DD or YYYY-MM-DDTHH:MM, "
        f"at most {REMIND_MAX_DAYS} days ahead",
        column,
    )


def _args_assign(tokens: list[_Token], note: str | None) -> DispatchArguments:
    mentions = [t.value for t in tokens if t.kind == "mention"]
    items = [t.value for t in tokens if t.kind != "mention"]
    if not mentions:
        raise _Refusal("missing_argument", "/assign needs at least one @person or @crew")
    _check_mentions(len(mentions))
    _check_keys(len(items))
    return AssignArgs(assignees=mentions, items=items, note=note)


def _args_dispatch(tokens: list[_Token], note: str | None) -> DispatchArguments:
    first = _first_word("dispatch", tokens, "a request type or action name")
    parameters: dict[str, str] = {}
    left: list[_Token] = []
    for token in tokens[1:]:
        found = _PARAMETER.fullmatch(token.value) if token.kind == "word" else None
        if found is None:
            left.append(token)
            continue
        name = found.group(1)
        if name in parameters:
            raise _Refusal("bad_parameter", f"parameter {name!r} is given twice", token.column)
        parameters[name] = found.group(2)
        if len(parameters) > MAX_PARAMETERS:
            raise _Refusal("bad_parameter", f"at most {MAX_PARAMETERS} parameters", token.column)
    return DispatchArgs(
        request_type=first.value, parameters=parameters, text=_text_of(left), note=note
    )


def _args_raise(tokens: list[_Token], note: str | None) -> DispatchArguments:
    first = _first_word("raise", tokens, "a record type (rfi, record)")
    against = [t.value for t in tokens[1:] if t.kind == "key"]
    _check_keys(len(against))
    left = [t for t in tokens[1:] if t.kind != "key"]
    return RaiseArgs(record_type=first.value, against=against, text=_text_of(left), note=note)


def _args_link(tokens: list[_Token], note: str | None) -> DispatchArguments:
    marker = next(
        (i for i, t in enumerate(tokens) if t.kind == "word" and t.value.lower() == "as"), None
    )
    keys = tokens if marker is None else tokens[:marker]
    if any(t.kind == "mention" for t in keys):
        raise _Refusal("unexpected_arguments", "/link takes keys, not mentions")
    relation: str | None = None
    if marker is not None:
        after = tokens[marker + 1 :]
        if not after and keys:
            raise _Refusal(
                "missing_argument", "/link ... as needs a relation", tokens[marker].column
            )
        if len(after) > 1 or (after and not after[0].is_word):
            raise _Refusal("unexpected_arguments", "/link takes one relation after 'as'")
        if after:
            relation = after[0].value
    if not keys:
        raise _Refusal("missing_argument", "/link needs at least one record key")
    _check_keys(len(keys))
    return LinkArgs(keys=[t.value for t in keys], relation=relation, note=note)


def _args_status(tokens: list[_Token], note: str | None) -> DispatchArguments:
    first = _first_word("status", tokens, "the target state")
    return StatusArgs(target=first.value, text=_text_of(tokens[1:]), note=note)


def _args_hold(tokens: list[_Token], note: str | None) -> DispatchArguments:
    return HoldArgs(text=_text_of(tokens), note=note)


def _args_release(tokens: list[_Token], note: str | None) -> DispatchArguments:
    return ReleaseArgs(text=_text_of(tokens), note=note)


def _args_due(tokens: list[_Token], note: str | None) -> DispatchArguments:
    if not tokens:
        raise _Refusal("missing_argument", "/due needs a date (YYYY-MM-DD, +3d, +2w)")
    if len(tokens) > 1:
        raise _Refusal("unexpected_arguments", "/due takes one date", tokens[1].column)
    token = tokens[0]
    _check_due(token.as_text if token.is_word else "?", token.column)
    return DueArgs(when=token.value, note=note)


def _args_notify(tokens: list[_Token], note: str | None) -> DispatchArguments:
    who = [t.value for t in tokens if t.kind == "mention"]
    if not who:
        raise _Refusal("missing_argument", "/notify needs at least one @person")
    _check_mentions(len(who))
    return NotifyArgs(who=who, text=_text_of([t for t in tokens if t.kind != "mention"]), note=note)


def _args_remind(tokens: list[_Token], note: str | None) -> DispatchArguments:
    who = [t.value for t in tokens if t.kind == "mention"]
    rest = [t for t in tokens if t.kind != "mention"]
    if not rest:
        raise _Refusal("missing_argument", "/remind needs a time (+2h, 2026-11-02T09:00)")
    _check_mentions(len(who))
    when = rest[0]
    _check_remind(when.as_text if when.is_word else "?", when.column)
    return RemindArgs(when=when.value, who=who, text=_text_of(rest[1:]), note=note)


def _args_summarise(tokens: list[_Token], note: str | None) -> DispatchArguments:
    if tokens:
        raise _Refusal("unexpected_arguments", "/summarise takes no arguments", tokens[0].column)
    return SummariseArgs(note=note)


_BUILDERS = {
    "assign": _args_assign,
    "dispatch": _args_dispatch,
    "raise": _args_raise,
    "link": _args_link,
    "status": _args_status,
    "hold": _args_hold,
    "release": _args_release,
    "due": _args_due,
    "notify": _args_notify,
    "remind": _args_remind,
    "summarise": _args_summarise,
}


def _bad_control(chars: str, allowed: str) -> bool:
    return any(ch == "\x7f" or (ch < " " and ch not in allowed) for ch in chars)


def _parse(text: str) -> ParsedDispatch | None:
    stripped = text.lstrip()
    if not stripped.startswith("/"):
        return None
    parts = stripped.splitlines(keepends=True)
    line = parts[0].strip()
    note = "".join(parts[1:]).strip() or None
    if len(line) > MAX_COMMAND_LINE_CHARS or len(text) > MAX_MESSAGE_CHARS:
        raise _Refusal(
            "too_long",
            f"a command line is at most {MAX_COMMAND_LINE_CHARS} characters and a message "
            f"{MAX_MESSAGE_CHARS}",
        )
    if _bad_control(line, "\t") or (note is not None and _bad_control(note, "\t\r\n")):
        raise _Refusal("control_character", "the message holds a control character")
    word = line[1:].split(None, 1)
    verb_text = word[0] if word and not line[1:2].isspace() else ""
    verb = _VERBS.get(verb_text.lower()) if verb_text.isascii() else None
    if verb is None:
        shown = verb_text[:40].encode("ascii", "replace").decode("ascii")
        raise _Refusal(
            "unknown_verb", f"unknown command /{shown}" if shown else "no command after /", 1
        )
    tokens = _tokenize(line[1 + len(verb_text) :], 1 + len(verb_text))
    args = _BUILDERS[verb](tokens, note)
    return ParsedDispatch(line=line, args=args)


class CommandLineParser:
    """The :class:`~tl_core.threads.contract.DispatchParser` of the thread composer."""

    def parse(self, text: str) -> ParsedDispatch | ParseProblem | None:
        try:
            return _parse(text)
        except _Refusal as refusal:
            return ParseProblem(code=refusal.code, message=refusal.message, column=refusal.column)
        except (ValidationError, ValueError, TypeError):
            return ParseProblem(code="unparsable", message="the command line cannot be read")
