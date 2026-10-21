"""Plain words for stored values, the technical-details toggle, and the leak finder (P1-UX-T00).

Every screen turns stored values into text through these functions, so no screen keeps its own
label table. Nothing here talks to a client; the labels come in as a ``Labels`` value.
``find_technical`` only reports technical tokens; it never edits text.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tl_schema.forms import FieldMeta, PsetGroupMeta

from tl_tui.text import EMPTY, format_value, unit_label

REFUSAL = "Technical details are for admins"

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# The leak-finder patterns. Each is a named constant with one test; the walking test (T11) greps
# this list, so a new pattern is added here and in TECHNICAL_PATTERNS.
ULID_PATTERN = re.compile(r"(?<![0-9A-Za-z])[0-9A-HJKMNP-TV-Z]{26}(?![0-9A-Za-z])")
DIGEST_PATTERN = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{64}(?![0-9A-Za-z])")
SHORT_HASH_PATTERN = re.compile(r"#[0-9a-f]{4}…[0-9a-f]{2}(?![0-9A-Za-z])")
PACKAGE_PATTERN = re.compile(r"(?<![\w.@-])[A-Za-z][\w.-]*@\d+\.\d+\.\d+(?![\w]|\.\d)")
SERVICE_PATTERN = re.compile(r"(?<!\w)svc:\w+")
REQUIRED_RULE_PATTERN = re.compile(r"(?<!\w)required@\w[\w/]*")
SHA256_PATTERN = re.compile(r"(?<!\w)sha256:\w+")
CALENDAR_ID_PATTERN = re.compile(r"(?<!\w)cal:[\w.-]+|(?<!\w)calendar C-[\w-]+")
CALENDAR_VERSION_PATTERN = re.compile(r"(?<![\w@])@v\d+(?!\w)")
# The code@version form clock text writes (calendars.py: Calendar.ref), for example P123-default@1.
# The lookbehind keeps the tail of a package name (co.acme.engineering@3.2.0) from matching here.
CALENDAR_REF_PATTERN = re.compile(r"(?<![A-Za-z0-9_.@-])[A-Za-z0-9][A-Za-z0-9_-]*@\d+(\.\d+)*\b")
DOMAIN_KEY_PATTERN = re.compile(r"(?<![\w/])([a-z][a-z0-9_]*)/([a-z][a-z0-9_]*)(?![\w/])")

# Patterns that match on their own. DOMAIN_KEY_PATTERN needs a Labels value and is checked apart.
TECHNICAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    ULID_PATTERN,
    DIGEST_PATTERN,
    SHORT_HASH_PATTERN,
    PACKAGE_PATTERN,
    SERVICE_PATTERN,
    REQUIRED_RULE_PATTERN,
    SHA256_PATTERN,
    CALENDAR_ID_PATTERN,
    CALENDAR_VERSION_PATTERN,
    CALENDAR_REF_PATTERN,
)


@dataclass(frozen=True)
class Labels:
    """The human labels a screen needs, loaded once by the caller. Empty means no label known."""

    type_titles: Mapping[str, str] = dataclasses.field(default_factory=dict)
    code_labels: Mapping[str, Mapping[str, str]] = dataclasses.field(default_factory=dict)
    domains: Mapping[str, str] = dataclasses.field(default_factory=dict)
    subtypes: Mapping[tuple[str, str], str] = dataclasses.field(default_factory=dict)
    services: Mapping[str, str] = dataclasses.field(default_factory=dict)


def humanize(name: str) -> str:
    """``ControlValve`` becomes ``Control valve``; ``engineering.Tag`` becomes ``Tag``."""
    base = name.rsplit(".", 1)[-1].replace("_", " ")
    words: list[str] = []
    for part in base.split():
        for piece in _CAMEL_BOUNDARY.sub(" ", part).split():
            words.append(piece if piece.isupper() and len(piece) > 1 else piece.lower())
    if not words:
        return ""
    words[0] = words[0][0].upper() + words[0][1:]
    return " ".join(words)


def type_label(labels: Labels, record_type: str) -> str:
    """The record type's title, else its humanized name."""
    title = labels.type_titles.get(record_type)
    return title if title else humanize(record_type)


def code_label(labels: Labels, list_name: str, code: str | None) -> str:
    """The code's label, else the code itself, else a dash when there is no code."""
    if not code:
        return EMPTY
    return labels.code_labels.get(list_name, {}).get(code) or code


def domain_label(labels: Labels, domain: str | None, subtype: str | None = None) -> str:
    """The subtype's label (``Letter``), else the domain's label; the internal key never shows."""
    if not domain:
        return EMPTY
    if subtype:
        return labels.subtypes.get((domain, subtype)) or humanize(subtype)
    return labels.domains.get(domain) or humanize(domain)


def actor_label(labels: Labels, actor: str) -> str:
    """A service by its label, a user by name; an unknown service is ``a service``, never its id."""
    if actor.startswith("svc:"):
        return labels.services.get(actor) or "a service"
    if actor.startswith("user:"):
        return actor[len("user:") :]
    return actor


def _or_list(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " or " + words[-1]


def rule_phrase(field: FieldMeta) -> str:
    """The enforcement in words: ``required at Design or Installed``, ``advisory``, ``locked``."""
    text = field.enforcement or "optional"
    if field.required_in_states:
        text += " at " + _or_list(list(field.required_in_states))
    if field.readonly:
        text += " (read-only)"
    return text


def pset_label(group: PsetGroupMeta) -> str:
    """The pset group's label; never its package or version."""
    return group.label or humanize(group.name)


def quantity(value: Any, unit: str | None) -> str:
    """The value with its unit label, for example ``2.5 in``; a dash when there is no value."""
    text = format_value(value)
    if text == EMPTY:
        return EMPTY
    label = unit_label(unit)
    return f"{text} {label}" if label else text


class DisplayMode:
    """Whether technical details show on one app. Off by default, per viewer, not remembered."""

    technical: bool = False

    def toggle(self, *, is_admin: bool) -> str:
        """Switch the mode for an admin and return ``""``; a plain user gets the refusal line."""
        if not is_admin:
            return REFUSAL
        self.technical = not self.technical
        return ""


def mode_of(widget_or_app: object) -> DisplayMode:
    """The app's ``display_mode`` when it has one, else a plain-mode default.

    The attribute is ``display_mode``, not ``display``: Textual's App and Widget own ``display``.
    """
    mode = getattr(widget_or_app, "display_mode", None)
    if isinstance(mode, DisplayMode):
        return mode
    return DisplayMode()


def find_technical(text: str, labels: Labels | None = None) -> list[str]:
    """Every technical token in ``text``, in order. Domain keys count only when labels are given."""
    hits: list[tuple[int, str]] = []
    for pattern in TECHNICAL_PATTERNS:
        hits.extend((match.start(), match.group(0)) for match in pattern.finditer(text))
    if labels is not None:
        for match in DOMAIN_KEY_PATTERN.finditer(text):
            if match.group(1) in labels.domains:
                hits.append((match.start(), match.group(0)))
    return [token for _, token in sorted(hits)]
