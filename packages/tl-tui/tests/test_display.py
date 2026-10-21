"""Shared display helper: plain words, the technical toggle, and the leak finder (P1-UX-T00)."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from textual.app import App
from tl_core.util import new_ulid
from tl_schema.forms import FieldMeta, PsetGroupMeta
from tl_tui.display import (
    CALENDAR_ID_PATTERN,
    CALENDAR_REF_PATTERN,
    CALENDAR_VERSION_PATTERN,
    DIGEST_PATTERN,
    DOMAIN_KEY_PATTERN,
    PACKAGE_PATTERN,
    REFUSAL,
    REQUIRED_RULE_PATTERN,
    SERVICE_PATTERN,
    SHA256_PATTERN,
    SHORT_HASH_PATTERN,
    TECHNICAL_PATTERNS,
    ULID_PATTERN,
    DisplayMode,
    Labels,
    actor_label,
    code_label,
    domain_label,
    find_technical,
    humanize,
    mode_of,
    pset_label,
    quantity,
    rule_phrase,
    type_label,
)
from tl_tui.text import short_hash

HEX64 = hashlib.sha256(b"valve data sheet").hexdigest()
ULID = new_ulid()


def _field(**extra: Any) -> FieldMeta:
    base: dict[str, Any] = {
        "path": "psets.valve_data.size_in",
        "label": "Size",
        "description": "d",
        "kind": "decimal",
        "layer": "standard",
        "group": "valve_data",
        "order": 1,
    }
    base.update(extra)
    return FieldMeta.model_validate(base)


def test_humanize_splits_camel_case_and_drops_the_module_prefix() -> None:
    assert humanize("ControlValve") == "Control valve"
    assert humanize("engineering.Tag") == "Tag"
    assert humanize("engineering.ControlValve") == "Control valve"
    assert humanize("HTTPServer") == "HTTP server"


def test_type_label_prefers_the_title_and_falls_back_to_humanize() -> None:
    labels = Labels(type_titles={"engineering.Tag": "Tag"})
    assert type_label(labels, "engineering.Tag") == "Tag"
    assert type_label(Labels(), "engineering.ControlValve") == "Control valve"


def test_code_label_returns_the_label_then_the_code_then_a_dash() -> None:
    labels = Labels(code_labels={"piping_class": {"PIP": "Piping"}})
    assert code_label(labels, "piping_class", "PIP") == "Piping"
    assert code_label(labels, "piping_class", "XX") == "XX"
    assert code_label(labels, "piping_class", None) == "—"


def test_domain_label_names_the_subtype_without_the_internal_key() -> None:
    labels = Labels(domains={"general": "General"}, subtypes={("general", "letter"): "Letter"})
    assert domain_label(labels, "general", "letter") == "Letter"
    assert domain_label(labels, "general") == "General"
    assert domain_label(Labels(), "general", "letter") == "Letter"
    assert "/" not in domain_label(Labels(), "general", "letter")
    assert domain_label(labels, None) == "—"


def test_actor_label_shows_a_service_by_label_and_never_its_id() -> None:
    labels = Labels(services={"svc:intake": "Email intake"})
    assert actor_label(labels, "svc:intake") == "Email intake"
    assert "svc:" not in actor_label(labels, "svc:unknown")
    assert actor_label(labels, "svc:unknown") == "a service"
    assert actor_label(labels, "user:amy") == "amy"


def test_rule_phrase_says_required_at_states_in_words() -> None:
    phrase = rule_phrase(_field(enforcement="required", required_in_states=["Design", "Installed"]))
    assert phrase == "required at Design or Installed"
    assert "@" not in phrase and "/" not in phrase
    assert rule_phrase(_field(enforcement="required", required_in_states=["Design"])) == (
        "required at Design"
    )
    assert rule_phrase(_field(enforcement="advisory")) == "advisory"
    assert rule_phrase(_field(enforcement="locked")) == "locked"
    assert rule_phrase(_field()) == "optional"
    assert rule_phrase(_field(readonly=True, layer="enrichment")) == "optional (read-only)"


def test_pset_label_has_no_package_or_version() -> None:
    group = PsetGroupMeta(
        name="valve_data",
        label="Valve data",
        package="co.acme.engineering",
        version="3.2.0",
        enforcement="required",
        layer="standard",
        fields=[],
    )
    label = pset_label(group)
    assert label == "Valve data"
    assert "@" not in label and "3.2.0" not in label and "co.acme" not in label


def test_quantity_joins_value_and_unit() -> None:
    assert quantity(2.5, "[in_i]") == "2.5 in"
    assert quantity(6, None) == "6"
    assert quantity(None, "[in_i]") == "—"


def test_toggle_switches_for_an_admin_and_refuses_a_plain_user_with_the_exact_line() -> None:
    mode = DisplayMode()
    assert mode.toggle(is_admin=False) == "Technical details are for admins"
    assert REFUSAL == "Technical details are for admins"
    assert mode.technical is False
    assert mode.toggle(is_admin=True) == ""
    assert mode.technical is True


def test_toggle_twice_returns_to_plain() -> None:
    mode = DisplayMode()
    mode.toggle(is_admin=True)
    mode.toggle(is_admin=True)
    assert mode.technical is False


def test_mode_of_defaults_to_plain_without_an_app() -> None:
    mode = mode_of(object())
    assert isinstance(mode, DisplayMode)
    assert mode.technical is False


def test_display_mode_lives_on_display_mode_and_not_on_textuals_display() -> None:
    app = App()
    display_before = app.display  # Textual's own CSS property
    assert mode_of(app).technical is False  # no mode set yet: a plain default
    mode = DisplayMode()
    app.display_mode = mode  # pyright: ignore[reportAttributeAccessIssue]  # App does not declare it
    assert mode_of(app) is mode
    assert mode_of(app).toggle(is_admin=True) == ""
    assert mode.technical is True
    assert app.display_mode is mode  # pyright: ignore[reportAttributeAccessIssue]
    assert app.display == display_before


@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        pytest.param(ULID_PATTERN, f"record {ULID}", [ULID], id="ulid"),
        pytest.param(DIGEST_PATTERN, f"content {HEX64}", [HEX64], id="digest"),
        pytest.param(
            SHORT_HASH_PATTERN, f"hash {short_hash(HEX64)}", [short_hash(HEX64)], id="short-hash"
        ),
        pytest.param(
            PACKAGE_PATTERN,
            "installed co.acme.engineering@3.2.0 here",
            ["co.acme.engineering@3.2.0"],
            id="package",
        ),
        pytest.param(SERVICE_PATTERN, "from svc:intake now", ["svc:intake"], id="service"),
        pytest.param(
            REQUIRED_RULE_PATTERN,
            "● required@Design/Inst",
            ["required@Design/Inst"],
            id="required-rule",
        ),
        pytest.param(SHA256_PATTERN, "sha256:9f2c", ["sha256:9f2c"], id="sha256"),
        pytest.param(
            CALENDAR_ID_PATTERN, "calendar C-2026-A", ["calendar C-2026-A"], id="calendar-c"
        ),
        pytest.param(CALENDAR_ID_PATTERN, "cal:P123", ["cal:P123"], id="calendar-cal"),
        pytest.param(CALENDAR_VERSION_PATTERN, "clock uses @v3 rules", ["@v3"], id="version"),
        pytest.param(
            CALENDAR_REF_PATTERN,
            "clock uses calendar P123-default@1 today",
            ["P123-default@1"],
            id="calendar-ref",
        ),
    ],
)
def test_find_technical_matches_each_pattern(
    pattern: object, text: str, expected: list[str]
) -> None:
    assert pattern in TECHNICAL_PATTERNS
    assert find_technical(text) == expected


def test_calendar_ref_matches_code_at_version_and_not_an_email() -> None:
    assert find_technical("clock uses calendar P123-default@1") == ["P123-default@1"]
    assert find_technical("on co.acme.engineering@3.2.0 rules") == ["co.acme.engineering@3.2.0"]
    # the package form is one token, reported once (the calendar pattern does not split it)
    assert CALENDAR_REF_PATTERN.search("co.acme.engineering@3.2.0") is None
    assert CALENDAR_REF_PATTERN.search("Ask amy@acme.com") is None
    assert find_technical("Ask amy@acme.com") == []


def test_find_technical_matches_a_domain_key_only_when_the_labels_know_the_domain() -> None:
    labels = Labels(domains={"general": "General"})
    assert DOMAIN_KEY_PATTERN.search("general/letter") is not None
    assert find_technical("general/letter", labels) == ["general/letter"]
    assert find_technical("general/letter") == []
    assert find_technical("m/s", labels) == []
    assert find_technical("m/s") == []


def test_find_technical_ignores_plain_sentences() -> None:
    labels = Labels(domains={"general": "General"})
    not_crockford = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"  # 26 letters with I, L, O and U: not a ULID
    plain = [
        "Ask amy@acme.com about the valve",
        f"part number {not_crockford}",
        "Letter",
        "Control valve",
        "m/s",
        "kg/m3",
        "N/A",
        "2026/10/21",
        "P123-RFI-0001",
    ]
    for text in plain:
        assert find_technical(text, labels) == [], text
        assert find_technical(text) == [], text
