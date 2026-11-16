"""Plain pages of a public intake form: the form, the thank-you, and three fixed pages.

Pure: no request, no database, no clock. Every dynamic string goes through
``html.escape(..., quote=True)``. The pages work with no script: no script, no link,
no third-party resource, no inline style, one own stylesheet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import Any

STYLESHEET = "/web/static/intake.css"
REQUEST_LINE = "This sends a request to the site team. You will not get a reply here."
SIGN_ON_LINE = (
    "This is not a sign-in. It records that you say you are present; a supervisor confirms it."
)
_PURPOSE_LINES = {"request": REQUEST_LINE, "sign_on": SIGN_ON_LINE}
# Same value as tl_core.forms.types.INTAKE_TEXT_MAX (read, not imported: this module is a leaf).
_TEXT_MAX = 280
_KINDS = frozenset({"text", "choice", "number"})


def _e(value: Any) -> str:
    return escape(str(value), quote=True)


def _purpose_line(purpose: str) -> str:
    try:
        return _PURPOSE_LINES[purpose]
    except KeyError:
        raise ValueError("unknown intake purpose") from None


def _document(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex">\n'
        '<meta name="referrer" content="no-referrer">\n'
        f"<title>{_e(title)}</title>\n"
        f'<link rel="stylesheet" href="{STYLESHEET}">\n'
        "</head>\n"
        "<body>\n"
        f"<main>\n{body}\n</main>\n"
        "</body>\n"
        "</html>\n"
    )


def _control(field: Mapping[str, Any], values: Mapping[str, Any], error_ids: Sequence[str]) -> str:
    fid = str(field["id"])
    kind = field.get("kind")
    if kind not in _KINDS:
        raise ValueError("unsupported intake kind")
    name = _e(f"f_{fid}")
    req = " required" if field.get("required") else ""
    invalid = ' aria-invalid="true"' if fid in error_ids else ""
    value = values.get(fid) if fid in values else None
    if kind == "choice":
        options = []
        for choice in field.get("choices") or []:
            picked = " selected" if value is not None and str(value) == str(choice) else ""
            options.append(f"<option{picked}>{_e(choice)}</option>")
        opts = "".join(options)
        return f'<select name="{name}" id="{name}"{req}{invalid}>{opts}</select>'
    val = f' value="{_e(value)}"' if value is not None else ""
    if kind == "number":
        lo = f' min="{_e(field["min"])}"' if field.get("min") is not None else ""
        hi = f' max="{_e(field["max"])}"' if field.get("max") is not None else ""
        return (
            f'<input type="number" name="{name}" id="{name}"{lo}{hi} step="any"{req}{invalid}{val}>'
        )
    return (
        f'<input type="text" name="{name}" id="{name}" maxlength="{_TEXT_MAX}"{req}{invalid}{val}>'
    )


def _field(field: Mapping[str, Any], values: Mapping[str, Any], error_ids: Sequence[str]) -> str:
    name = _e(f"f_{field['id']}")
    label = _e(field.get("text") or field["id"])
    if field.get("required"):
        label += " (required)"
    parts = [f'<label for="{name}">{label}</label>', _control(field, values, error_ids)]
    if field.get("unit"):
        parts.append(f'<span class="unit">{_e(field["unit"])}</span>')
    if field.get("help"):
        parts.append(f'<p class="help">{_e(field["help"])}</p>')
    return '<div class="field">' + "".join(parts) + "</div>"


def render_form(
    *,
    title: str,
    heading: str,
    fields: Sequence[Mapping[str, Any]],
    purpose: str,
    form_key: str,
    error_ids: Sequence[str] = (),
    values: Mapping[str, Any] | None = None,
) -> str:
    """The intake form: one control per field, a key, a honeypot, and the purpose line."""
    given: Mapping[str, Any] = values or {}
    shown = [_field(f, given, error_ids) for f in fields]
    body = "\n".join(
        [
            f"<h1>{_e(heading)}</h1>",
            f'<p class="purpose">{_e(_purpose_line(purpose))}</p>',
            '<form method="post" action="">',
            f'<input type="hidden" name="k" value="{_e(form_key)}">',
            *shown,
            '<p class="hp" aria-hidden="true">'
            '<input type="text" name="website" tabindex="-1" autocomplete="off"></p>',
            '<p><button type="submit">Send</button></p>',
            "</form>",
        ]
    )
    return _document(title, body)


def render_thanks(receipt: str, purpose: str) -> str:
    """The one page after a submit: a receipt word and the purpose line."""
    body = "\n".join(
        [
            "<h1>Thank you</h1>",
            f"<p>Your receipt is <strong>{_e(receipt)}</strong>.</p>",
            f'<p class="purpose">{_e(_purpose_line(purpose))}</p>',
        ]
    )
    return _document("Thank you", body)


def render_not_found() -> str:
    """The one page for every dead code. Constant."""
    return _document(
        "Not found",
        "<h1>Not found</h1>\n<p>This page is not available. Check the address and try again.</p>",
    )


def render_full() -> str:
    """The page for a form that is not taking more entries. Constant."""
    return _document(
        "Closed for now",
        "<h1>Closed for now</h1>\n<p>This form is not taking more entries at the moment.</p>",
    )


def render_busy() -> str:
    """The page to try again later. Constant."""
    return _document(
        "Try again later",
        "<h1>Try again later</h1>\n"
        "<p>The form is busy right now. Please try again in a few minutes.</p>",
    )
