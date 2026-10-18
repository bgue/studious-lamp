"""Reading an email file (``.eml``) that a stranger sent: bounded, text only, nothing followed.

**The message is hostile.** It is parsed with the standard library (``email`` with
``policy.default``; no third-party parser), after the size is checked and inside the resource
envelope of ``eml_isolated`` (a child process with a clock and a memory limit). What this file
promises, and the tests of ``test_eml.py`` check against a corpus of hostile messages:

* **Every count and size is bounded** (``EmlLimits``): the message, the headers (their number and
  length), the parts, the nesting, the attachments (their number, each size and the total decoded
  size), the recipients, the text of the body and a file name. A message over any bound is
  **refused** (``EmlRefused`` with a fixed message), never cut short: a partial message would be a
  record that says something the sender did not.
* **No clock** is read: the dates are those of the message, and ``Date`` is only the day the
  sender wrote.
* **Text that becomes record text** (the subject, a name, a file name, the body) has its white
  space folded and is then checked with ``textcheck.clean_text`` / ``clean_body``: a control
  character, a line or paragraph separator or a text-direction mark refuses the message. Nothing is
  stripped silently.
* **No HTML is rendered or read.** A message with only an HTML part has no body text
  (``html_only``); the original is kept whole in the item's ``message`` slot. No link, image or
  remote content is fetched or followed, and no attachment is opened or run: attachments are
  bytes with a name and a declared type that the file service stores and scans like any upload.
* A nested message (``message/rfc822``) is one attachment; the parser does not descend into it.
* **Names are names, not paths:** a file name is cut to its last component, and ``.`` ``..`` and
  empty names become ``attachment-<n>``.

``parse_eml`` is pure (bytes in, a value out). Use ``eml_isolated.parse_eml_isolated`` from a
command: it runs this in the child process.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from email import policy
from email.errors import MessageError
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import Any, Final

from tl_mod_correspondence.limits import MAX_BODY, MAX_EMAIL, MAX_RECIPIENTS, MAX_TEXT
from tl_mod_correspondence.textcheck import clean_body, clean_text
from tl_mod_correspondence.threading import normalise_message_id, parse_references


class EmlRefused(ValueError):  # noqa: N818 - a refusal, named for what the caller does with it
    """The message is over a bound or holds something the module will not take. The text is fixed
    (no part of the message is repeated) and safe to show."""


@dataclass(frozen=True)
class EmlLimits:
    """The bounds of one message. The defaults are the module's; tests tighten them."""

    max_bytes: int = 10 * 1024 * 1024  # the whole file
    max_headers: int = 200  # per part
    max_headers_total: int = 1000  # over all parts
    max_header_chars: int = 2000  # one header value, raw
    max_parts: int = 50  # all parts, multipart containers included
    max_depth: int = 6  # nesting of multiparts
    max_attachments: int = 20
    max_attachment_bytes: int = 10 * 1024 * 1024  # one attachment, decoded
    max_total_bytes: int = 25 * 1024 * 1024  # all attachments, decoded
    max_recipients: int = MAX_RECIPIENTS  # to and cc, each
    max_body_chars: int = MAX_BODY
    max_filename_chars: int = 200
    max_references: int = 50

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(values: dict[str, Any]) -> EmlLimits:
        return EmlLimits(**{k: int(v) for k, v in values.items() if k in EmlLimits.__annotations__})


@dataclass(frozen=True)
class EmlAddress:
    name: str | None
    email: str | None


@dataclass(frozen=True)
class EmlAttachment:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class ParsedMessage:
    subject: str
    from_name: str | None
    from_email: str | None
    to: tuple[EmlAddress, ...]
    cc: tuple[EmlAddress, ...]
    sent_on: str | None  # ISO date written in the message, or None when it has none
    message_id: str | None  # normalised, without brackets
    in_reply_to: str | None
    references: tuple[str, ...]
    body: str | None  # the text/plain part; None when there is none
    html_only: bool  # the message has an HTML part and no plain text one
    attachments: tuple[EmlAttachment, ...] = field(default_factory=tuple)
    size: int = 0


_EMAIL: Final = re.compile(r"[^@\s<>()\[\]\\,;:\"]{1,64}@[A-Za-z0-9.-]{1,190}")
_TYPE: Final = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]{0,60}/[a-z0-9][a-z0-9!#$&^_.+-]{0,60}")
_SPACE: Final = re.compile(r"\s+")
_FIRST_DAY: Final = date(1990, 1, 1)
_LAST_DAY: Final = date(2100, 12, 31)
#: Why a message is refused: fixed texts, so that nothing of the message is repeated.
TOO_BIG: Final = "the message is larger than the limit"
UNREADABLE: Final = "the message could not be read"


def _refuse(reason: str) -> EmlRefused:
    return EmlRefused(reason)


def _one_line(value: str, what: str) -> str:
    """White space folded to single spaces, then checked: a hostile character refuses."""
    folded = _SPACE.sub(" ", value).strip()
    try:
        return clean_text(folded)
    except ValueError as exc:
        raise _refuse(f"{what} holds a control or text-direction character") from exc


def _raw_headers(part: Message, limits: EmlLimits) -> int:
    items = part.raw_items()
    count = 0
    for _name, value in items:
        count += 1
        if count > limits.max_headers:
            raise _refuse("a part has too many headers")
        if len(str(value)) > limits.max_header_chars:
            raise _refuse("a header is longer than the limit")
    return count


def _header_text(msg: Message, name: str, what: str) -> str | None:
    try:
        value = msg[name]
        if value is None:
            return None
        return _one_line(str(value), what)
    except EmlRefused:
        raise
    except (MessageError, ValueError, TypeError, IndexError, AttributeError, UnicodeError) as exc:
        raise _refuse(f"{what} could not be decoded") from exc


def _addresses(msg: Message, name: str, limits: EmlLimits) -> tuple[EmlAddress, ...]:
    try:
        header = msg[name]
        if header is None:
            return ()
        found = list(getattr(header, "addresses", ()))
    except (MessageError, ValueError, TypeError, IndexError, AttributeError, UnicodeError) as exc:
        raise _refuse(f"{name} could not be decoded") from exc
    if len(found) > limits.max_recipients:
        raise _refuse(f"{name} names too many people")
    out: list[EmlAddress] = []
    for address in found:
        display = _one_line(str(address.display_name or ""), f"a name in {name}") or None
        if display is not None and len(display) > MAX_TEXT:
            raise _refuse(f"a name in {name} is too long")
        spec = str(address.addr_spec or "").strip().lower()
        email = spec if _EMAIL.fullmatch(spec) and len(spec) <= MAX_EMAIL else None
        if display is None and email is None:
            continue  # a group marker or an empty address: nothing to record
        out.append(EmlAddress(display, email))
    return tuple(out)


def _sent_on(msg: Message) -> str | None:
    try:
        raw = msg["Date"]
        if raw is None:
            return None
        moment = parsedate_to_datetime(str(raw))
    except (MessageError, ValueError, TypeError, IndexError, AttributeError, OverflowError):
        return None  # a date nobody can read is no date; nothing else is lost
    day = moment.date()
    if not _FIRST_DAY <= day <= _LAST_DAY:
        raise _refuse("the date of the message is not a plausible date")
    return day.isoformat()


def _leaves(root: Message, limits: EmlLimits) -> list[Message]:
    """The leaf parts in document order, found without recursion; counts and depth are bounded."""
    leaves: list[Message] = []
    stack: list[tuple[Message, int]] = [(root, 0)]
    seen = 0
    headers_total = 0
    while stack:
        part, depth = stack.pop()
        seen += 1
        if seen > limits.max_parts:
            raise _refuse("the message has too many parts")
        if depth > limits.max_depth:
            raise _refuse("the message is nested too deeply")
        headers_total += _raw_headers(part, limits)
        if headers_total > limits.max_headers_total:
            raise _refuse("the message has too many headers")
        if part.is_multipart() and part.get_content_maintype() == "multipart":
            children = part.get_payload()
            if not isinstance(children, list):
                raise _refuse(UNREADABLE)
            for child in reversed(children):
                if not isinstance(child, Message):
                    raise _refuse(UNREADABLE)
                stack.append((child, depth + 1))
        else:
            leaves.append(part)  # including message/rfc822: one attachment, not descended into
    return leaves


def _text_of(part: Message, limits: EmlLimits) -> str:
    """The text of a text part, decoded with its charset (unknown: UTF-8), bounded and checked."""
    raw = part.get_payload()
    if isinstance(raw, str) and len(raw) > limits.max_body_chars * 8:
        raise _refuse("the text of the message is longer than the limit")
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        raise _refuse(UNREADABLE)
    if len(payload) > limits.max_body_chars * 4:
        raise _refuse("the text of the message is longer than the limit")
    charset = part.get_content_charset() or "utf-8"
    try:
        text = payload.decode(charset, errors="replace")
    except (LookupError, ValueError):
        text = payload.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > limits.max_body_chars:
        raise _refuse(f"the text of the message is longer than {limits.max_body_chars} characters")
    try:
        return clean_body(text)
    except ValueError as exc:
        raise _refuse("the text holds a control or text-direction character") from exc


def _file_name(part: Message, number: int, limits: EmlLimits) -> str:
    try:
        raw = part.get_filename()
    except (MessageError, ValueError, TypeError, UnicodeError, AttributeError):
        raw = None
    name = _one_line(str(raw), "a file name") if raw else ""
    name = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if name in ("", ".", ".."):
        name = f"attachment-{number}"
    if len(name) > limits.max_filename_chars:
        raise _refuse("a file name is longer than the limit")
    return name


def _is_attachment(part: Message) -> bool:
    if part.get_content_disposition() == "attachment":
        return True
    kind = part.get_content_type()
    if kind in ("text/plain", "text/html"):
        return part.get_filename() is not None
    return True  # a non-text leaf is carried, never read


def parse_eml(data: bytes, limits: EmlLimits | None = None) -> ParsedMessage:
    """Read a message. Raises ``EmlRefused`` (fixed text) for anything over a bound or unreadable.

    Nothing is fetched, rendered or run; no clock is read. See the module docstring for what each
    bound is.
    """
    bounds = limits or EmlLimits()
    if len(data) > bounds.max_bytes:
        raise _refuse(TOO_BIG)
    if not data.strip():
        raise _refuse("the message is empty")
    try:
        root = BytesParser(policy=policy.default).parsebytes(data)
    except RecursionError as exc:
        raise _refuse("the message is nested too deeply") from exc
    except (MessageError, ValueError, TypeError, UnicodeError, MemoryError) as exc:
        raise _refuse(UNREADABLE) from exc
    if not isinstance(root, Message):  # pragma: no cover - the parser always returns a Message
        raise _refuse(UNREADABLE)
    leaves = _leaves(root, bounds)

    plain: str | None = None
    saw_html = False
    attachments: list[EmlAttachment] = []
    total = 0
    for leaf in leaves:
        kind = leaf.get_content_type()
        if not _is_attachment(leaf):
            if kind == "text/plain" and plain is None:
                plain = _text_of(leaf, bounds)
            elif kind == "text/html":
                saw_html = True
            continue
        if len(attachments) >= bounds.max_attachments:
            raise _refuse("the message has too many attachments")
        if leaf.get_content_maintype() == "message":
            inner = leaf.get_payload()
            parts = inner if isinstance(inner, list) else [inner]
            content = b"".join(
                p.as_bytes() if isinstance(p, Message) else str(p).encode("utf-8", "replace")
                for p in parts
            )
        else:
            raw = leaf.get_payload()
            if isinstance(raw, str) and len(raw) > bounds.max_attachment_bytes * 4 // 3 + 4096:
                raise _refuse("an attachment is larger than the limit")
            decoded = leaf.get_payload(decode=True)
            content = decoded if isinstance(decoded, bytes) else b""
        if len(content) > bounds.max_attachment_bytes:
            raise _refuse("an attachment is larger than the limit")
        total += len(content)
        if total > bounds.max_total_bytes:
            raise _refuse("the attachments together are larger than the limit")
        declared = leaf.get_content_type().lower()
        attachments.append(
            EmlAttachment(
                filename=_file_name(leaf, len(attachments) + 1, bounds),
                content_type=declared if _TYPE.fullmatch(declared) else "application/octet-stream",
                data=content,
            )
        )

    sender = _addresses(root, "From", bounds)
    first = sender[0] if sender else EmlAddress(None, None)
    subject = _header_text(root, "Subject", "the subject") or ""
    if len(subject) > MAX_TEXT:
        raise _refuse(f"the subject is longer than {MAX_TEXT} characters")
    message_id = normalise_message_id(_header_text(root, "Message-ID", "the message id"))
    in_reply_to = normalise_message_id(_header_text(root, "In-Reply-To", "In-Reply-To"))
    references = tuple(
        parse_references(_header_text(root, "References", "References"))[: bounds.max_references]
    )
    return ParsedMessage(
        subject=subject,
        from_name=first.name,
        from_email=first.email,
        to=_addresses(root, "To", bounds),
        cc=_addresses(root, "Cc", bounds),
        sent_on=_sent_on(root),
        message_id=message_id,
        in_reply_to=in_reply_to,
        references=references,
        body=plain,
        html_only=plain is None and saw_html,
        attachments=tuple(attachments),
        size=len(data),
    )
